#!/usr/bin/env python3
"""
One-off diagnostic, like dump_blocks.py but for the Brief Tasks table.
Prints the raw column names, types, and values Notion returns for the
first few rows, so a parsing problem can be fixed against what Notion
actually sends instead of a guess.

Usage:
  python dump_database.py                  (uses TASKS_DATABASE_ID from config.py)
  python dump_database.py "<id or URL>"
"""

import re
import sys

import requests

from morning_brief import notion_headers, tasks_database_id, FetchError


def extract_id(raw):
    last = raw.strip().split("?")[0].rstrip("/").split("/")[-1]
    tail = last.replace("-", "")[-32:]
    if re.fullmatch(r"[0-9a-fA-F]{32}", tail):
        return tail
    raise SystemExit(f"Could not find a Notion ID in: {raw}")


def main():
    raw = sys.argv[1] if len(sys.argv) > 1 else tasks_database_id()
    if not raw:
        raise SystemExit("No table given and TASKS_DATABASE_ID is not set in config.py.")
    db_id = extract_id(raw)

    resp = requests.post(
        f"https://api.notion.com/v1/databases/{db_id}/query",
        headers=notion_headers(), json={"page_size": 5}, timeout=20,
    )
    print(f"HTTP {resp.status_code}")
    if not resp.ok:
        print(resp.text[:800])
        return

    results = resp.json().get("results", [])
    print(f"{len(results)} row(s) returned (first 5 shown)\n")
    for n, row in enumerate(results, 1):
        print(f"--- row {n} ---")
        for name, prop in row.get("properties", {}).items():
            ptype = prop.get("type")
            print(f"  {name!r}: type={ptype} value={prop.get(ptype)!r}")


if __name__ == "__main__":
    try:
        main()
    except FetchError as e:
        print(str(e))
