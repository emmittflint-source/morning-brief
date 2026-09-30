#!/usr/bin/env python3
"""
One-off diagnostic. Prints the raw block structure Notion returns for
one page, so we fix parsing logic against real data, not a guess.

Usage:
  python dump_blocks.py "<page id or full Notion URL>"
"""

import re
import sys

import requests

from morning_brief import notion_headers, FetchError


def extract_id(raw: str) -> str:
    raw = raw.strip()
    last = raw.split("?")[0].rstrip("/").split("/")[-1]
    tail = last.replace("-", "")[-32:]
    if len(tail) == 32 and re.fullmatch(r"[0-9a-fA-F]{32}", tail):
        return tail
    raise SystemExit(f"Could not find a Notion page ID in: {raw}")


def dump_children(block_id, depth=0):
    url = f"https://api.notion.com/v1/blocks/{block_id}/children"
    resp = requests.get(url, headers=notion_headers(), params={"page_size": 100}, timeout=15)
    if not resp.ok:
        print("  " * depth + f"[error fetching children: {resp.status_code}]")
        return

    for block in resp.json().get("results", []):
        btype = block.get("type")
        has_children = block.get("has_children", False)
        indent = "  " * depth

        if btype == "table_row":
            cells = block.get("table_row", {}).get("cells", [])
            cell_texts = ["".join(t.get("plain_text", "") for t in cell) for cell in cells]
            print(f"{indent}[table_row] cells: {cell_texts}")
        else:
            rich = block.get(btype, {}).get("rich_text", [])
            text = "".join(t.get("plain_text", "") for t in rich)
            print(f"{indent}[{btype}] has_children={has_children} text={text!r}")
            # print each rich_text run's raw type/mention info too, this is
            # the part plain-text summaries hide and where a wrong parsing
            # assumption tends to come from
            for run in rich:
                run_type = run.get("type")
                if run_type == "mention":
                    print(f"{indent}    run: type=mention mention={run.get('mention')!r}")
                elif run_type == "text":
                    link = run.get("text", {}).get("link")
                    if link:
                        print(f"{indent}    run: type=text (with link) href={link}")

        if has_children and depth < 3:
            dump_children(block["id"], depth + 1)


def main():
    if len(sys.argv) < 2:
        print('Usage: python dump_blocks.py "<page id or full Notion URL>"')
        sys.exit(1)

    page_id = extract_id(sys.argv[1])
    print(f"Dumping raw blocks for page id: {page_id}\n")
    try:
        dump_children(page_id)
    except FetchError as e:
        print(str(e))


if __name__ == "__main__":
    main()
