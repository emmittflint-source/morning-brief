"""
Config template. Copy this file to config.py and fill in your own
values, config.py itself is gitignored so your personal Notion page ID
and deadlines never get committed, whether you're the original author
or someone who forked this template.

    cp config.example.py config.py    (Mac/Linux)
    copy config.example.py config.py  (Windows)

Which projects exist lives in Notion itself (see INDEX_PAGE_ID below),
not in this file. Adding a project means adding a "Name - <page link>"
line to that Notion page, not editing any code.
"""

TIMEZONE = "Pacific/Honolulu"  # your own IANA timezone name

# The one thing this script needs a hardcoded pointer to: a Notion page
# with one "Project Name - <link to that project's page>" line per
# project you want the brief to read from. See README.md for exactly
# what that page needs to look like.
INDEX_PAGE_ID = "PASTE_YOUR_NOTION_PAGE_ID_HERE"

# Standing deadlines shown at the bottom of every brief. Not tied to
# any single project page, so they live here instead. Add, remove, or
# change these freely, any number of entries works.
DEADLINES = [
    {"label": "Example deadline", "date": "2026-12-31"},
]
