#!/usr/bin/env python3
"""
Run this once after setting NOTION_API_KEY, before trusting a full
morning_brief.py run, and again any time the project index page
changes in a way you want to double-check.

First reads the project index page itself (config.INDEX_PAGE_ID), then
checks each listed project's page one at a time. A single bad project
page won't kill the whole thing here, unlike a full run, and the index
page itself gets checked first since everything else depends on it.

Usage:
  python check_notion_access.py
"""

import os
import sys

import config
from morning_brief import (
    fetch_next_actions, fetch_page_title, fetch_project_index,
    validate_project_list, FetchError, ConfigError,
)


def main():
    if not os.environ.get("NOTION_API_KEY"):
        print("NOTION_API_KEY is not set. Set it before running this.")
        sys.exit(1)

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


if __name__ == "__main__":
    main()
