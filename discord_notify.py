"""
Optional: post the morning brief to a Discord channel and @mention you, so
it reaches your phone as a notification. Off by default.

How it is switched on (see README.md for the full walkthrough):
  - config.py:         DISCORD_ENABLED = True
  - environment:       DISCORD_WEBHOOK_URL (a secret, treat it like a
                       password) and DISCORD_USER_ID (digits, not secret)
  - command:           python morning_brief.py --discord
                       python morning_brief.py --discord-test   (one short test message)

Safety choices worth knowing about:
  - The webhook link is a secret: anyone holding it can post to your channel.
    No error message or log line here ever contains it. Python's own network
    errors normally include the full URL, so only the error's type is reported.
  - Messages may @mention only the one user ID you configured. A task that
    happens to contain "@everyone" cannot ping anyone.
  - The link must look like a real Discord webhook, so a typo can't send your
    task list to some other website.
  - This module only posts. It never reads anything from Discord.
"""

import os
import re
import time

import requests

import config
from morning_brief import (
    days_left, describe_days, describe_deadline_days,
    format_event_time, format_month_day, try_parse_date,
)

MESSAGE_LIMIT = 2000   # Discord's hard limit for one message
SAFE_LIMIT = 1900      # stay comfortably under it

WEBHOOK_RE = re.compile(
    r"^https://(?:(?:canary|ptb)\.)?discord(?:app)?\.com/api/webhooks/\d+/[A-Za-z0-9_\-]+/?$"
)
USER_ID_RE = re.compile(r"^\d{15,25}$")


class NotifyError(Exception):
    """A problem sending to Discord. The message never contains the webhook link."""


def discord_enabled() -> bool:
    """The master switch, DISCORD_ENABLED in config.py. A missing setting means off.
    Written so the text "False" in quotes can't accidentally count as on."""
    value = getattr(config, "DISCORD_ENABLED", False)
    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "on", "1")
    return bool(value)


def get_settings():
    """(webhook_url, user_id_or_None) from the environment, or a NotifyError."""
    webhook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    user_id = os.environ.get("DISCORD_USER_ID", "").strip()
    if not webhook:
        raise NotifyError("DISCORD_WEBHOOK_URL is not set. Add it as an environment variable (see README.md).")
    if not WEBHOOK_RE.match(webhook):
        raise NotifyError(
            "DISCORD_WEBHOOK_URL doesn't look like a Discord webhook link "
            "(it should start with https://discord.com/api/webhooks/). Copy it again from Discord."
        )
    if user_id and not USER_ID_RE.match(user_id):
        raise NotifyError(
            "DISCORD_USER_ID should be only digits. In Discord, turn on Developer Mode, "
            "right-click your own name, and choose Copy User ID."
        )
    return webhook, (user_id or None)


# ---------- message text ----------

def _item_lines(n, name, item, today, rotation=False, done_when_max=None):
    tag = ""
    if item.get("urgent"):
        tag += "**URGENT** "
    if rotation:
        tag += "*rotation* "
    lines = [f"**{n}.** {tag}{item['next_action']}"]

    done_when = item.get("done_when")
    if done_when and done_when_max != 0:
        if done_when_max and len(done_when) > done_when_max:
            done_when = done_when[: done_when_max - 1].rstrip() + "\u2026"
        lines.append(f"> done when {done_when}")

    meta = name
    if item.get("due"):
        if rotation:
            meta += f" \u00b7 due {format_month_day(item['due'])}"
        else:
            meta += f" \u00b7 **{describe_days(days_left(item['due'], today))}**"
    lines.append(meta)
    return lines


def _compose(today, data, user_id, done_when_max):
    mention = f"<@{user_id}> " if user_id else ""
    lines = [f"{mention}**Morning brief \u00b7 {today.strftime('%a')} {format_month_day(today)}**"]

    events = data["events"]
    if events:
        lines.append(", ".join(f"{e['summary']} {format_event_time(e['start'])}" for e in events[:4]))
    else:
        lines.append("Nothing on the calendar")
    lines.append("")

    n = 1
    for name, item in data["top3"]:
        lines.extend(_item_lines(n, name, item, today, done_when_max=done_when_max))
        lines.append("")
        n += 1
    if data["rotation_entry"]:
        name, item = data["rotation_entry"]
        lines.extend(_item_lines(n, name, item, today, rotation=True, done_when_max=done_when_max))
        lines.append("")
    if not data["top3"] and not data["rotation_entry"]:
        lines.append("No open tasks right now.")
        lines.append("")

    parts = []
    for d in config.DEADLINES:
        target = try_parse_date(d["date"])
        parts.append(f"{d['label']} {describe_deadline_days(days_left(target, today))}")
    if parts:
        lines.append("**Deadlines:** " + " \u00b7 ".join(parts))

    if data.get("empty_projects"):
        lines.append("No Next actions block: " + ", ".join(data["empty_projects"]))
    if data.get("failed_projects"):
        lines.append("Couldn't read: " + ", ".join(data["failed_projects"]))
    return "\n".join(lines).strip()


def format_discord(today, data, user_id=None) -> str:
    """The brief as one Discord message, guaranteed to fit under the limit.
    If the full version is too long it is shortened in steps: first the
    'done when' lines are trimmed, then dropped, and only as a last resort
    is the message cut off."""
    for done_when_max in (None, 100, 60, 0):
        text = _compose(today, data, user_id, done_when_max)
        if len(text) <= SAFE_LIMIT:
            return text
    return text[: SAFE_LIMIT - 40].rstrip() + "\n\u2026 (message trimmed to fit Discord)"


# ---------- sending ----------

def post(content, webhook, user_id=None, sleep=time.sleep, attempts=3, wait=5):
    """Send one message. Retries only for network trouble and Discord server
    errors, never for a rejected link or a rate limit."""
    payload = {
        "content": content,
        # Only the configured user may be pinged, whatever the task text says.
        "allowed_mentions": {"parse": [], "users": [user_id] if user_id else []},
    }
    problem = "unknown problem"
    for attempt in range(1, attempts + 1):
        try:
            resp = requests.post(webhook, json=payload, timeout=15)
        except requests.RequestException as e:
            # Never str(e): it usually contains the full webhook link.
            problem = f"could not reach Discord ({type(e).__name__})"
        else:
            code = resp.status_code
            if code in (200, 204):
                return
            if code == 429:
                raise NotifyError("Discord says too many messages too quickly (rate limited). Try again in a minute.")
            if code in (401, 403, 404):
                raise NotifyError(
                    "Discord rejected the webhook. It may have been deleted or regenerated. "
                    "Make a new one and update DISCORD_WEBHOOK_URL."
                )
            if 500 <= code < 600:
                problem = f"Discord had a server error ({code})"
            else:
                detail = ""
                try:
                    detail = ": " + str(resp.json().get("message", ""))[:120]
                except Exception:
                    pass
                raise NotifyError(f"Discord refused the message ({code}){detail}")
        if attempt < attempts:
            sleep(wait)
    raise NotifyError(f"{problem}, after {attempts} tries")


def send_brief(today, data):
    webhook, user_id = get_settings()
    post(format_discord(today, data, user_id), webhook, user_id)


def send_error(text):
    webhook, user_id = get_settings()
    mention = f"<@{user_id}> " if user_id else ""
    body = f"{mention}**Morning brief could not run**\n{text}"
    post(body[:SAFE_LIMIT], webhook, user_id)


def send_test():
    webhook, user_id = get_settings()
    mention = f"<@{user_id}> " if user_id else ""
    post(f"{mention}**Morning brief test.** If your phone just buzzed, Discord notifications are working.",
         webhook, user_id)


# ---------- command line wrappers ----------
# Each returns True when nothing went wrong, including the harmless case where
# the feature is switched off, and prints one plain sentence about what happened.

def _run(action, success_message):
    if not discord_enabled():
        print("Discord is switched off (DISCORD_ENABLED is False in config.py), so nothing was sent.")
        return True
    try:
        action()
    except NotifyError as e:
        print(f"Discord: {e}")
        return False
    print(success_message)
    return True


def cli_send_brief(today, data):
    return _run(lambda: send_brief(today, data), "Brief sent to Discord.")


def cli_send_error(text):
    return _run(lambda: send_error(text), "Error notice sent to Discord.")


def cli_send_test():
    return _run(send_test, "Test message sent to Discord. Check your phone.")


def status_lines():
    """A few lines for check_notion_access.py. Never sends anything and never shows the link."""
    if not discord_enabled():
        return ["Discord: switched off (DISCORD_ENABLED is False in config.py). Optional, see README.md."]
    try:
        _, user_id = get_settings()
    except NotifyError as e:
        return [f"Discord: switched ON, but not ready. {e}"]
    lines = ["Discord: switched ON. The webhook link is set and looks valid."]
    if user_id:
        lines.append("   Your @ ping is set up (DISCORD_USER_ID).")
    else:
        lines.append("   [WARN] DISCORD_USER_ID is not set, so messages will not @ you.")
    lines.append("   To send a test message:  python morning_brief.py --discord-test")
    return lines
