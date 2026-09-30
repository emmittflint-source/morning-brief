#!/usr/bin/env python3
"""
Emmitt's morning brief. Read-only. Never writes to Notion or Calendar.

Requires these env vars (names only, never hardcode values):
  NOTION_API_KEY
  GOOGLE_CALENDAR_REFRESH_TOKEN
  GOOGLE_OAUTH_CLIENT_ID
  GOOGLE_OAUTH_CLIENT_SECRET

Usage:
  python morning_brief.py                  # real run, uses today's date
  python morning_brief.py --date 2026-10-05 # pretend it's a different day
  python morning_brief.py --mock            # no network calls, uses mock_data.py

Cost note: this script makes zero calls to any LLM. The ranking rule
below is fully deterministic (soonest due date, one project per slot,
day-of-year rotation), so there is nothing for a model to decide.
That means the $0.20/run cost cap in the spec is currently unused;
real cost is just the Notion + Calendar API calls, which are free.
"""

import argparse
import os
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from dateutil import parser as dateparser

import config

NOTION_VERSION = "2022-06-28"


class FetchError(Exception):
    """Raised when a required source can't be read. Message names the source."""


class ConfigError(Exception):
    """Raised when config.py itself is inconsistent, e.g. a typo'd name."""


# ---------- Notion ----------

def notion_headers():
    key = os.environ.get("NOTION_API_KEY")
    if not key:
        raise FetchError("Notion: NOTION_API_KEY is not set")
    return {
        "Authorization": f"Bearer {key}",
        "Notion-Version": NOTION_VERSION,
    }


def get_block_children(block_id: str) -> list:
    """
    Raw children blocks of a page OR a block, one level deep. Notion's API
    treats a page ID as a block ID for this endpoint, so this one function
    covers both "get the page's top-level blocks" and "get one block's
    nested children" (used for a list item's Done when / Due / Time).
    """
    url = f"https://api.notion.com/v1/blocks/{block_id}/children"
    try:
        resp = requests.get(url, headers=notion_headers(), params={"page_size": 100}, timeout=15)
    except requests.RequestException as e:
        raise FetchError(f"Notion: could not reach api.notion.com ({e})")

    if resp.status_code == 404:
        raise FetchError(
            f"Notion: page or block {block_id} not found (check the page ID, or if using "
            "an internal connection instead of a personal access token, confirm the page "
            "was shared with it under Connections)"
        )
    if resp.status_code == 401:
        raise FetchError("Notion: NOTION_API_KEY was rejected (check the token)")
    if not resp.ok:
        raise FetchError(f"Notion: request failed ({resp.status_code})")

    return resp.json().get("results", [])


def fetch_page_title(page_id: str) -> str:
    """Pull the page's actual title from Notion, to check against config.py's label."""
    url = f"https://api.notion.com/v1/pages/{page_id}"
    try:
        resp = requests.get(url, headers=notion_headers(), timeout=15)
    except requests.RequestException as e:
        raise FetchError(f"Notion: could not reach api.notion.com ({e})")
    if not resp.ok:
        raise FetchError(f"Notion: could not read page title ({resp.status_code})")

    for prop in resp.json().get("properties", {}).values():
        if prop.get("type") == "title":
            rich = prop.get("title", [])
            text = "".join(t.get("plain_text", "") for t in rich)
            return text.strip() or "(blank title)"
    return "(no title property found)"


import re

HEADING_TYPES = {"heading_1", "heading_2", "heading_3"}
LIST_TYPES = {"numbered_list_item", "bulleted_list_item"}
FIELD_RE_TEMPLATE = r"^\s*{field}\s*:\s*(.*)$"


def block_plain_text(block: dict) -> str:
    btype = block.get("type")
    rich = block.get(btype, {}).get("rich_text", [])
    return "".join(t.get("plain_text", "") for t in rich).strip()


SECTION_MARKER_RE = re.compile(r"^next actions?\s*:?\s*$", re.IGNORECASE)


def find_action_item_blocks(top_blocks: list) -> list:
    """
    The section marker is sometimes a heading, sometimes a plain
    paragraph whose entire text is just 'Next actions' (confirmed both
    ways against live pages, not assumed). Either way it's followed by
    numbered or bulleted list items, each item's own text IS the action.
    Stops at the first non-list block after the run starts, or a second
    marker. Returns [] if there's no marker at all, that's the
    documented 'no Next actions block' case, not an error.

    Deliberately strict: a marker must be ONLY 'next actions' (plus an
    optional colon), not any paragraph that happens to mention the
    phrase inside a longer sentence, of which these pages have several.
    """
    items = []
    in_section = False
    for block in top_blocks:
        btype = block.get("type")
        text = block_plain_text(block)

        if btype in HEADING_TYPES or btype == "paragraph":
            if SECTION_MARKER_RE.match(text.strip()):
                if in_section:
                    break
                in_section = True
                continue

        if in_section:
            if btype in LIST_TYPES:
                items.append(block)
            else:
                break
    return items


def parse_item_fields(child_blocks: list) -> dict:
    """
    child_blocks: the nested children of one list-item block (its Done
    when / Due / Time paragraphs). Missing fields stay None rather than
    guessed.
    """
    result = {"done_when": None, "due": None, "raw_due": None, "time": None}
    field_map = {"Done when": "done_when", "Due": "raw_due", "Time": "time"}
    for block in child_blocks:
        text = block_plain_text(block)
        for field, key in field_map.items():
            m = re.match(FIELD_RE_TEMPLATE.format(field=re.escape(field)), text, re.IGNORECASE)
            if m:
                val = m.group(1).strip()
                if key == "raw_due":
                    result["raw_due"] = val
                    result["due"] = try_parse_date(val)
                else:
                    result[key] = val
                break
    return result


def build_action_items(top_blocks: list, get_children_fn) -> list:
    """
    Pure-ish orchestrator: get_children_fn(block_id) -> raw block list,
    injectable so this can be tested against a hand-built block tree
    without hitting the real API. Returns items in the shape the rest
    of the app expects: {next_action, done_when, due, raw_due, time}.
    """
    items = []
    for block in find_action_item_blocks(top_blocks):
        fields = {"done_when": None, "due": None, "raw_due": None, "time": None}
        if block.get("has_children"):
            fields = parse_item_fields(get_children_fn(block["id"]))
        items.append({"next_action": block_plain_text(block), **fields})
    return items


def fetch_next_actions(page_id: str) -> list:
    """Live entry point: fetch a page's Next actions items from real Notion."""
    top_blocks = get_block_children(page_id)
    return build_action_items(top_blocks, get_block_children)


# ---------- Project index (replaces the old hardcoded PROJECTS list) ----------

def extract_project_line(block: dict):
    """
    Confirmed against a real page (dump_blocks.py), not assumed: each
    project line is a paragraph with a plain-text run ('Name - ') then a
    page-mention run. The mention carries the real target page ID
    directly, no URL parsing needed. Lines with no mention (instructions,
    blank lines) return None and are skipped.
    """
    btype = block.get("type")
    rich = block.get(btype, {}).get("rich_text", [])

    name_parts = []
    page_id = None
    for run in rich:
        if run.get("type") == "mention" and run.get("mention", {}).get("type") == "page":
            page_id = run["mention"]["page"]["id"].replace("-", "")
            break
        name_parts.append(run.get("plain_text", ""))

    if page_id is None:
        return None

    name = "".join(name_parts).strip()
    name = re.sub(r"[\s\-:]+$", "", name).strip()  # drop a trailing '-' or ':' delimiter
    if not name:
        return None
    return {"name": name, "page_id": page_id}


def fetch_project_index(index_page_id: str) -> list:
    """
    Live entry point: read the project list from the index page itself,
    instead of a hardcoded list in config.py. Adding a project means
    adding a line there, not editing this script.
    """
    top_blocks = get_block_children(index_page_id)
    projects = []
    for block in top_blocks:
        item = extract_project_line(block)
        if item:
            projects.append(item)
    return projects


def validate_project_list(projects: list):
    """Catches a broken index page with a clear message, before anything
    downstream tries to rank or display something malformed."""
    if not projects:
        raise ConfigError(
            "The project index page returned zero projects. Check it still has "
            "'Name - <mention>' lines, or that config.INDEX_PAGE_ID still points "
            "at the right page."
        )
    names = [p["name"] for p in projects]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise ConfigError(
            f"The project index has duplicate name(s): {', '.join(dupes)}. "
            "Names must be unique, since the brief displays by name."
        )


def try_parse_date(raw: str):
    raw = raw.strip()
    if not raw or raw.lower() in ("tbd", "none", "-", "n/a"):
        return None
    try:
        parsed = dateparser.parse(raw, default=datetime(date.today().year, 1, 1))
        return parsed.date()
    except (ValueError, OverflowError):
        return None


# ---------- Google Calendar ----------

def get_calendar_access_token():
    client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
    refresh_token = os.environ.get("GOOGLE_CALENDAR_REFRESH_TOKEN")
    missing = [n for n, v in [
        ("GOOGLE_OAUTH_CLIENT_ID", client_id),
        ("GOOGLE_OAUTH_CLIENT_SECRET", client_secret),
        ("GOOGLE_CALENDAR_REFRESH_TOKEN", refresh_token),
    ] if not v]
    if missing:
        raise FetchError(f"Calendar: missing env var(s) {', '.join(missing)}")

    try:
        resp = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=15,
        )
    except requests.RequestException as e:
        raise FetchError(f"Calendar: could not reach oauth2.googleapis.com ({e})")

    if not resp.ok:
        raise FetchError("Calendar: refresh token was rejected, reconnect Google Calendar")
    return resp.json()["access_token"]


def fetch_today_events(today: date):
    token = get_calendar_access_token()
    tz = ZoneInfo(config.TIMEZONE)
    start = datetime.combine(today, datetime.min.time(), tzinfo=tz)
    end = start + timedelta(days=1)

    try:
        resp = requests.get(
            "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "timeMin": start.isoformat(),
                "timeMax": end.isoformat(),
                "singleEvents": "true",
                "orderBy": "startTime",
            },
            timeout=15,
        )
    except requests.RequestException as e:
        raise FetchError(f"Calendar: could not reach googleapis.com ({e})")

    if not resp.ok:
        raise FetchError(f"Calendar: request failed ({resp.status_code})")

    events = []
    for item in resp.json().get("items", []):
        start_info = item.get("start", {})
        t = start_info.get("dateTime") or start_info.get("date")
        events.append({"summary": item.get("summary", "(untitled)"), "start": t})
    return events


def format_event_time(raw_start: str) -> str:
    """
    Plain integer math instead of %-I, which is a Linux/Mac-only strftime
    extension. Windows has no equivalent flag at all (it uses %#I instead,
    which would just break the other two platforms the same way %-I broke
    Windows). This works identically everywhere.
    """
    try:
        dt = dateparser.parse(raw_start)
        hour_12 = dt.hour % 12 or 12
        return f"{hour_12}:{dt.minute:02d}"
    except (ValueError, TypeError):
        return raw_start


# ---------- Ranking ----------

def soonest_item_for_project(items):
    """Given a project's items, return the one with the soonest due date,
    or the first item if none have a due date."""
    if not items:
        return None
    dated = [i for i in items if i["due"] is not None]
    if dated:
        return min(dated, key=lambda i: i["due"])
    return items[0]


def build_top_slots(project_items: dict, today: date):
    """
    project_items: {project_name: [items]}, in the order they were
    fetched (the project index's own order, or mock_data's order).
    Returns (top3, rotation_entry) where top3 is a list of up to 3
    (project_name, item) tuples and rotation_entry is (project_name, item) or None.

    No ROTATION_ORDER list anymore. Which projects are rotation-eligible
    (their soonest item has no due date at all) is observed live from
    project_items itself, every run, rather than asserted in advance in
    a list that could drift out of sync with reality.
    """
    candidates = []
    no_due_names = []
    reps = {}
    for name, items in project_items.items():
        rep = soonest_item_for_project(items)
        if not rep:
            continue
        reps[name] = rep
        if rep["due"] is not None:
            candidates.append((name, rep))
        else:
            no_due_names.append(name)
    candidates.sort(key=lambda pair: pair[1]["due"])

    top3 = []
    used_projects = set()
    for name, item in candidates:
        if name in used_projects:
            continue
        top3.append((name, item))
        used_projects.add(name)
        if len(top3) == 3:
            break

    # A project can only land in no_due_names if it truly has no due date,
    # so it can never also be in used_projects, but the filter is kept for
    # safety in case that assumption ever changes.
    no_due_eligible = [n for n in no_due_names if n not in used_projects]
    rotation_entry = None
    if no_due_eligible:
        idx = today.timetuple().tm_yday % len(no_due_eligible)
        pick = no_due_eligible[idx]
        rotation_entry = (pick, reps[pick])

    return top3, rotation_entry


def days_left(target: date, today: date) -> int:
    return (target - today).days


# ---------- Formatting ----------

def format_month_day(d: date) -> str:
    """'%b %-d' without the Linux/Mac-only flag: d.day is already a plain
    int with no leading zero, so no strftime flag is needed at all."""
    return f"{d.strftime('%b')} {d.day}"


def format_brief(today: date, events, top3, rotation_entry, empty_projects, failed_projects):
    lines = []
    day_str = f"{today.strftime('%a')} {format_month_day(today)}"
    if events:
        ev_str = ", ".join(f"{e['summary']} {format_event_time(e['start'])}" for e in events[:4])
    else:
        ev_str = "nothing on the calendar"
    lines.append(f"**Today ({day_str}):** {ev_str}")
    lines.append("")

    def done_when_suffix(item):
        # Shown in full, on purpose. Keeping it short is a writing habit
        # for the Notion page itself, not something code should truncate.
        return f" — done when {item['done_when']}" if item.get("done_when") else ""

    n = 1
    for name, item in top3:
        dl = f" — {days_left(item['due'], today)} days left"
        lines.append(f"{n}. {item['next_action']}{done_when_suffix(item)} ({name}){dl}")
        n += 1
    if rotation_entry:
        name, item = rotation_entry
        due_str = f" — due {format_month_day(item['due'])}" if item["due"] else ""
        lines.append(f"{n}. *(rotation)* {item['next_action']}{done_when_suffix(item)} ({name}){due_str}")

    lines.append("")
    dl_parts = []
    for d in config.DEADLINES:
        target = try_parse_date(d["date"])
        dl_parts.append(f"{d['label']} {days_left(target, today)}d")
    lines.append("**Deadlines:** " + ", ".join(dl_parts))

    # Both of these are detected live, every run, never from a hand-maintained
    # list, so they can't go stale the way a static config list would.
    if empty_projects:
        lines.append("")
        lines.append("No Next actions block: " + ", ".join(empty_projects))
    if failed_projects:
        lines.append("")
        reasons = ", ".join(f"{name} ({msg})" for name, msg in failed_projects.items())
        lines.append("Couldn't read (fix this, it's silently missing from ranking): " + reasons)

    return "\n".join(lines)


def word_count(text: str) -> int:
    return len(text.split())


# ---------- Main ----------

def gather_brief_data(today: date, mock: bool, skip_calendar: bool = False) -> dict:
    """
    All the real work, with no text formatting baked in. Returns the raw
    pieces (events, top3, rotation_entry, empty_projects, failed_projects)
    so a caller can render them however it wants, a plain string for the
    terminal, or real widgets for the popup, rather than one format being
    forced to re-parse the other's output.
    """
    if mock:
        import mock_data
        events = mock_data.EVENTS
        project_items = mock_data.PROJECT_ITEMS
        empty_projects, failed_projects = [], {}
    else:
        # skip_calendar is a manual-testing escape hatch, for while Calendar
        # OAuth isn't wired up yet: it lets the real Notion pipeline (index
        # page, all project pages, ranking) be tested live without Calendar
        # blocking the whole run. Not used by run_daily.pyw, the real daily
        # entry point always wants the real calendar.
        events = [] if skip_calendar else fetch_today_events(today)

        projects = fetch_project_index(config.INDEX_PAGE_ID)
        validate_project_list(projects)

        project_items, empty_projects, failed_projects = {}, [], {}
        for proj in projects:
            name, page_id = proj["name"], proj["page_id"]
            try:
                items = fetch_next_actions(page_id)
            except FetchError as e:
                # One bad page (typo'd ID, deleted page, unshared) does not
                # take the whole brief down. It's reported, not silenced,
                # but the other projects still run normally.
                failed_projects[name] = str(e)
                continue
            if not items:
                empty_projects.append(name)
            else:
                project_items[name] = items

    top3, rotation_entry = build_top_slots(project_items, today)
    return {
        "events": events,
        "top3": top3,
        "rotation_entry": rotation_entry,
        "empty_projects": empty_projects,
        "failed_projects": failed_projects,
    }


def run(today: date, mock: bool, skip_calendar: bool = False):
    data = gather_brief_data(today, mock, skip_calendar)
    brief = format_brief(
        today, data["events"], data["top3"], data["rotation_entry"],
        data["empty_projects"], data["failed_projects"],
    )

    # No hard word-count cap anymore: showing each item's real Done-when
    # text and a fixed length target don't both survive contact with
    # real content. Length is now whatever the Notion pages actually
    # say, kept informational here rather than enforced.
    #
    # sys.stderr is None (not just redirected, literally None) when run
    # via pythonw.exe with no console attached, which is exactly how
    # run_daily.pyw runs. Writing to it unconditionally crashed the
    # popup on a successful brief, this only ever got tested through a
    # real console before, which is why it didn't show up sooner.
    if sys.stderr is not None:
        sys.stderr.write(f"(brief is {word_count(brief)} words)\n")

    return brief


def main():
    parser = argparse.ArgumentParser(description="Emmitt's morning brief")
    parser.add_argument("--date", type=str, default=None, help="YYYY-MM-DD, defaults to today")
    parser.add_argument("--mock", action="store_true", help="use mock_data.py, no network calls")
    parser.add_argument("--skip-calendar", action="store_true",
                         help="real Notion, but skip Calendar (for testing before Calendar OAuth is set up)")
    args = parser.parse_args()

    tz = ZoneInfo(config.TIMEZONE)
    today = dateparser.parse(args.date).date() if args.date else datetime.now(tz).date()

    try:
        brief = run(today, args.mock, skip_calendar=args.skip_calendar)
    except (FetchError, ConfigError) as e:
        print(str(e))
        sys.exit(1)

    print(brief)


if __name__ == "__main__":
    main()
