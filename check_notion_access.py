#!/usr/bin/env python3
"""
Run this once after setting NOTION_API_KEY, before trusting a full
morning_brief.py run, and again any time you change how your tasks are
set up in Notion.

If config.TASKS_DATABASE_ID is set, it checks the Brief Tasks table:
that it can be read, which columns are missing, and what each project
has open. Otherwise it checks the older setup, reading the project index
page (config.INDEX_PAGE_ID) and then each listed project's page one at a
time, so one bad page can't hide behind the others.

Usage:
  python check_notion_access.py
  python check_notion_access.py <table id>   (try a table without editing config.py)
"""

import os
import sys

import config
from morning_brief import (
    fetch_next_actions, fetch_page_title, fetch_project_index,
    validate_project_list, FetchError, ConfigError,
    tasks_database_id, query_task_rows, parse_task_row, NO_PROJECT_LABEL,
)

EXPECTED_COLUMNS = ["Project", "Due", "Done when", "Urgent", "Done", "Time"]


def check_tasks_table(table_id):
    print("Reading the Brief Tasks table...")
    try:
        rows = query_task_rows(table_id)
    except FetchError as e:
        print(f"[FAIL] {e}")
        sys.exit(1)

    if not rows:
        print("[OK] The table is readable, but it has no open rows (nothing with Done unticked).")
        print("     Add a row, or untick Done on one, to see it in the brief.")
        return

    warnings = []
    present = set(rows[0].get("properties", {}).keys())
    for col in EXPECTED_COLUMNS:
        if col not in present:
            warnings.append(f"Column '{col}' was not found. It may have been renamed or deleted, "
                            f"and the brief will behave as if it were empty.")

    by_project, nameless = {}, 0
    for row in rows:
        parsed = parse_task_row(row)
        if parsed is None:
            nameless += 1
            continue
        project, item = parsed
        by_project.setdefault(project, []).append(item)
        if project == NO_PROJECT_LABEL:
            warnings.append(f"'{item['next_action']}' has no Project, so it shows as {NO_PROJECT_LABEL}.")
        if item["raw_due"] and item["due"] is None:
            warnings.append(f"'{item['next_action']}': the Due value '{item['raw_due']}' could not be read as a date.")
    if nameless:
        warnings.append(f"{nameless} open row(s) have no Task name and are ignored.")

    total = sum(len(v) for v in by_project.values())
    urgent = sum(1 for v in by_project.values() for i in v if i["urgent"])
    print(f"[OK] {total} open task(s) across {len(by_project)} project(s), {urgent} marked urgent\n")
    for project, items in by_project.items():
        print(f"   {project}: {len(items)} open, "
              f"{sum(1 for i in items if i['urgent'])} urgent, "
              f"{sum(1 for i in items if i['due'])} with a due date")

    if warnings:
        print("\nWorth a look:")
        for w in warnings:
            print(f"   [WARN] {w}")
    print("\nTo see exactly what the brief would show, run:  python morning_brief.py --skip-calendar")


def check_legacy_pages():
    print("Reading the project index page...")
    try:
        projects = fetch_project_index(config.INDEX_PAGE_ID)
    except FetchError as e:
        print(f"[FAIL] Could not read the index page itself: {e}")
        sys.exit(1)

    try:
        validate_project_list(projects)
    except ConfigError as e:
        print(f"[FAIL] {e}")
        sys.exit(1)

    print(f"Index OK, found {len(projects)} project(s): {', '.join(p['name'] for p in projects)}\n")

    print(f"Checking {len(projects)} pages...\n")
    ok, failed, empty = 0, [], []

    for proj in projects:
        name, page_id = proj["name"], proj["page_id"]
        try:
            items = fetch_next_actions(page_id)
        except FetchError as e:
            print(f"[FAIL]  {name}: {e}")
            failed.append(name)
            continue

        if not items:
            print(f"[EMPTY] {name}: page reachable, but no list items found under a 'Next actions' heading")
            empty.append(name)
            continue

        due_count = sum(1 for i in items if i["due"] is not None)
        try:
            real_title = fetch_page_title(page_id)
        except FetchError:
            real_title = "(could not fetch title)"
        match_flag = "" if name.lower() in real_title.lower() or real_title.lower() in name.lower() else "  <-- CHECK THIS, titles don't obviously match"
        print(f"[OK]    {name}: {len(items)} item(s), {due_count} with a due date")
        print(f"        Notion's actual title for this page: \"{real_title}\"{match_flag}")
        ok += 1

    print(f"\n{ok}/{len(projects)} pages OK.")
    if failed:
        print(f"Failed (share these with your integration, or check the page ID): {', '.join(failed)}")
    if empty:
        print(f"Reachable but no items parsed, check formatting against README: {', '.join(empty)}")


def main():
    if not os.environ.get("NOTION_API_KEY"):
        print("NOTION_API_KEY is not set. Set it before running this.")
        sys.exit(1)

    if len(sys.argv) > 1:
        config.TASKS_DATABASE_ID = sys.argv[1]   # try a table without editing config.py

    table_id = tasks_database_id()
    if table_id:
        check_tasks_table(table_id)
        print("\n(The older per-project pages are not read while TASKS_DATABASE_ID is set.)")
    else:
        check_legacy_pages()

    import discord_notify
    print()
    for line in discord_notify.status_lines():
        print(line)


if __name__ == "__main__":
    main()
