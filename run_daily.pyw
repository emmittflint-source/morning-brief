"""
Launcher that Task Scheduler runs (via pythonw.exe, so there is no console).

Two ways to run it:
  - Double-click: always shows the brief right away.
  - Task Scheduler passes --scheduled: then it shows the brief at most
    once per day, never before 6 AM, and waits for the network to come
    back if it was launched right after wake or logon. That lets the
    task use several triggers (7:00 AM, log on, workstation unlock)
    without popping up repeatedly, so a laptop that was asleep at 7:00
    still gets its brief the first time you sit down.

Optional Discord: when DISCORD_ENABLED is True in config.py, a run also posts
the brief to your Discord channel (see README.md), at most once per day, in the
background so the popup never waits for it. A scheduled run that fails sends one
error notice per day, since nobody is watching it. A manual run that fails does
not, you are looking right at it.

Because there is no console, everything is written to morning_brief.log
next to this script, and a native Windows message box is the fallback if
even the popup can't start, so a failure always leaves evidence.
"""

import os
import sys
import threading
import time
import traceback
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(HERE, "morning_brief.log")
STATE_PATH = os.path.join(HERE, "last_shown.txt")
MAX_LOG_BYTES = 200_000

EARLIEST_SCHEDULED_HOUR = 6      # scheduled runs stay quiet before this local hour
NETWORK_RETRY_ATTEMPTS = 6       # scheduled runs only
NETWORK_RETRY_WAIT_SECONDS = 15  # so about 90 seconds of patience after wake or logon
DISCORD_JOIN_SECONDS = 40        # after the popup closes, wait this long for a send still in flight

STATE_LOCK = threading.Lock()    # the state file is touched by the main thread and the Discord thread


def log(message):
    """Append a timestamped line. Must never be the reason the brief fails."""
    try:
        if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > MAX_LOG_BYTES:
            os.replace(LOG_PATH, LOG_PATH + ".old")
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')}  {message}\n")
    except Exception:
        pass


def native_alert(title, text):
    """Last-resort visible error that does not depend on Tkinter working."""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, text, title, 0x40010)  # error icon, topmost
        except Exception:
            pass


def get_now(tz_name):
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo(tz_name))


def read_state():
    """The little state file as a dict. An older file holds just one date on one
    line, which is read as the 'shown' date, so nothing breaks on upgrade."""
    state = {}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            for line in f.read().splitlines():
                line = line.strip()
                if not line:
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    state[key.strip()] = value.strip()
                else:
                    state["shown"] = line
    except Exception:
        pass
    return state


def write_state(state):
    try:
        if not any(state.values()):
            if os.path.exists(STATE_PATH):
                os.remove(STATE_PATH)
            return
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            for key, value in state.items():
                if value:
                    f.write(f"{key}={value}\n")
    except Exception as e:
        log(f"could not write {STATE_PATH}: {e}")


def _set_state(key, value):
    with STATE_LOCK:
        state = read_state()
        state[key] = value
        write_state(state)


def read_last_shown():
    return read_state().get("shown", "")


def mark_shown(today):
    _set_state("shown", today.isoformat())


def clear_last_shown():
    _set_state("shown", "")  # nothing was actually shown, let the next trigger retry


def discord_done(kind, day):
    """Has this kind of Discord message ('discord' or 'discord_error') gone out for this day?"""
    return read_state().get(kind, "") == day.isoformat()


def mark_discord(kind, day):
    _set_state(kind, day.isoformat())


def load_discord():
    """The optional Discord module, or None when it is switched off or unavailable.
    Nothing about Discord is allowed to stop the brief from appearing."""
    try:
        import discord_notify
        return discord_notify if discord_notify.discord_enabled() else None
    except ImportError:
        log("Discord: discord_notify.py was not found, skipping (the brief is unaffected)")
        return None
    except Exception:
        log("Discord: could not load, skipping (the brief is unaffected)\n" + traceback.format_exc())
        return None


def start_discord_job(discord, label, kind, day, action):
    """Run one Discord send in a background thread so the popup appears at
    once even if Discord is slow or down. Marked as sent only on success, so
    a failure gets another try on a later run."""
    def worker():
        try:
            action()
        except discord.NotifyError as e:
            log(f"Discord ({label}) failed: {e}")
        except Exception:
            log(f"Discord ({label}) unexpected problem\n" + traceback.format_exc())
        else:
            mark_discord(kind, day)
            log(f"Discord ({label}) sent")

    thread = threading.Thread(target=worker, name="discord-send")
    thread.start()
    return thread


def gather_with_retry(gather, fetch_error, today, scheduled):
    """Scheduled runs often start right after wake or logon, before Wi-Fi is
    back. Only 'could not reach' failures are retried, a rejected token or a
    config problem is reported immediately."""
    attempts = NETWORK_RETRY_ATTEMPTS if scheduled else 1
    for attempt in range(1, attempts + 1):
        try:
            return gather(today, mock=False)
        except fetch_error as e:
            offline = "could not reach" in str(e).lower()
            if attempt == attempts or not offline:
                raise
            log(f"network not ready (attempt {attempt}/{attempts}), retrying in "
                f"{NETWORK_RETRY_WAIT_SECONDS}s: {e}")
            time.sleep(NETWORK_RETRY_WAIT_SECONDS)


def main():
    scheduled = "--scheduled" in sys.argv[1:]
    os.chdir(HERE)
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    log(f"started ({'scheduled' if scheduled else 'manual'}, python "
        f"{sys.version.split()[0]}, {sys.executable})")

    # Imports live inside the error handling on purpose: under pythonw.exe
    # an ImportError at the top of the file would kill the process silently.
    try:
        import config
        from morning_brief import gather_brief_data, FetchError, ConfigError
        from popup import show_popup
    except Exception:
        err = traceback.format_exc()
        log("IMPORT FAILURE\n" + err)
        native_alert("Morning Brief could not start", err[-1500:])
        return

    discord = load_discord()
    discord_job = None   # (label, state key, day, action) or None

    today = None
    skip_reason = None
    title = payload = None
    is_error = False
    try:
        now = get_now(config.TIMEZONE)
        today = now.date()
        if scheduled and now.hour < EARLIEST_SCHEDULED_HOUR:
            skip_reason = f"scheduled run before {EARLIEST_SCHEDULED_HOUR}:00 local time"
        elif scheduled and read_last_shown() == today.isoformat():
            skip_reason = "brief already shown today"
        else:
            data = gather_with_retry(gather_brief_data, FetchError, today, scheduled)
            log(
                f"data gathered: {len(data['events'])} events, "
                f"{len(data['top3'])} deadline items, "
                f"rotation={'yes' if data['rotation_entry'] else 'no'}"
            )
            title, payload = "Morning Brief", data
            if discord and not discord_done("discord", today):
                discord_job = ("brief", "discord", today, lambda: discord.send_brief(today, data))
    except FetchError as e:
        log(f"FetchError: {e}")
        title, payload, is_error = "Morning Brief: Could Not Run", str(e), True
    except ConfigError as e:
        log(f"ConfigError: {e}")
        title, payload, is_error = "Morning Brief: Config Problem", str(e), True
    except Exception:
        err = traceback.format_exc()
        log("UNEXPECTED ERROR\n" + err)
        title, payload, is_error = "Morning Brief: Unexpected Error", err[-1500:], True

    if is_error and discord and scheduled:
        # Nobody is watching a scheduled run, so a failure should reach the phone.
        # One notice per day, not one per wake-up.
        error_day = today or datetime.now().date()
        if not discord_done("discord_error", error_day):
            notice = payload
            discord_job = ("error notice", "discord_error", error_day, lambda: discord.send_error(notice))

    if skip_reason:
        log(f"skipped: {skip_reason}")
        return

    discord_thread = None
    if discord_job:
        label, kind, day, action = discord_job
        discord_thread = start_discord_job(discord, label, kind, day, action)

    try:
        if not is_error:
            # Marked before showing so two triggers firing together can't
            # both pop up. Error popups never count as "shown", so the next
            # trigger gets another try.
            mark_shown(today)
        log("showing popup")
        show_popup(title, payload, is_error=is_error, today=today)
        log("popup closed")
    except Exception:
        err = traceback.format_exc()
        log("POPUP FAILURE\n" + err)
        if not is_error:
            clear_last_shown()  # nothing was actually shown, let the next trigger retry
        native_alert("Morning Brief: popup failed", err[-1500:])
    finally:
        if discord_thread:
            # If the popup was closed quickly, give a send still in flight a moment to finish.
            discord_thread.join(timeout=DISCORD_JOIN_SECONDS)


if __name__ == "__main__":
    main()
