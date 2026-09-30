"""
This is what Task Scheduler points at, not morning_brief.py directly.

Saved as .pyw (not .py) so Windows runs it with pythonw.exe, no black
console window flashing behind the popup. Double-clicking this file
also works, for testing without Task Scheduler at all.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import config
from morning_brief import gather_brief_data, FetchError, ConfigError
from popup import show_popup


def main():
    tz = ZoneInfo(config.TIMEZONE)
    today = datetime.now(tz).date()

    try:
        # gather_brief_data instead of run(): the popup renders structured
        # data directly now, not the plain-text version meant for a
        # terminal, and this path never touches sys.stderr at all, so
        # there's no console-less pythonw.exe edge case to worry about
        # here either.
        data = gather_brief_data(today, mock=False)
        show_popup("Morning Brief", data, today=today)
    except FetchError as e:
        show_popup("Morning Brief — Could Not Run", str(e), is_error=True)
    except ConfigError as e:
        show_popup("Morning Brief — Config Problem", str(e), is_error=True)
    except Exception as e:
        # anything unexpected still gets shown, rather than failing silently
        # with no window and no clue why nothing happened
        show_popup("Morning Brief — Unexpected Error", f"{type(e).__name__}: {e}", is_error=True)


if __name__ == "__main__":
    main()
