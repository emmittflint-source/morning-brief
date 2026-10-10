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

# The "Brief Tasks" Notion table: one row per task, with the columns
# Task, Project, Due, Done when, Urgent, Done, and Time (see README.md).
# Paste the table's ID here (the 32-character code in its page URL).
# When this is set it is the ONLY source of tasks. Leave it as the
# placeholder to keep using the older per-project pages (INDEX_PAGE_ID
# below) instead.
TASKS_DATABASE_ID = "PASTE_YOUR_TASKS_TABLE_ID_HERE"

# How calendar times are shown: "12h" gives 2:30 PM, "24h" gives 14:30.
TIME_FORMAT = "12h"

# OPTIONAL: also post the brief to a private Discord channel and @mention you,
# so it reaches your phone. OFF by default. This is the master switch: while
# it is False, nothing is ever sent, even if a scheduled task passes
# --discord. To use it, see "Optional: get the brief on your phone" in
# README.md, then change this to True. Turn it on for ONE machine only (one
# that stays on), or you will get duplicates.
DISCORD_ENABLED = False

# How many normal (non-urgent) tasks a single project may fill in the
# top three, so one busy project can't take every slot. Urgent tasks
# ignore this limit entirely.
PER_PROJECT_LIMIT = 1

# OLDER WAY, only used when TASKS_DATABASE_ID is not set:
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
