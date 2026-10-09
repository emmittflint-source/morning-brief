# Morning brief

A personal daily agent that reads your open tasks from one Notion
table, checks your Google Calendar, and shows you a short summary each
morning: today's events, your most urgent tasks, and one more picked in
rotation so nothing gets permanently buried.

**Read-only.** It never writes to Notion or your calendar, only reads.

## How it decides what to show you

Your tasks live in one Notion table called **Brief Tasks**, one row per
task:

| Column | What it is |
|---|---|
| Task | What to do (the title) |
| Project | Which project it belongs to. Pick one, or type a new name to create it |
| Due | Optional date |
| Done when | How you'll know it's finished. Shown in the brief |
| Urgent | Tick to make it jump the line |
| Done | Tick when finished. The brief ignores ticked rows |
| Time | Optional estimate, e.g. `30 min` |

Every run, in this order:

1. **Urgent tasks** come first, soonest due date first, undated ones
   last. They ignore both the one-per-project limit and the three-line
   limit, so six urgent tasks means six lines. They count toward the
   three, so one urgent task leaves two normal lines.
2. **Normal tasks with a due date** fill the rest of the three lines,
   soonest first, at most one per project (so one busy project can't
   take every line). Raise that with `PER_PROJECT_LIMIT` in `config.py`.
3. **One rotation line**, always last: a task from a project that has
   nothing with a due date, chosen by day of year so each gets a turn.

Adding a task is adding a row. Adding a project is typing a new name in
the Project column. Retiring a task is ticking Done. No code changes.

## Setup

```
pip install -r requirements.txt
```

Copy the config template and fill in your own values:

```
cp config.example.py config.py       # Mac/Linux
copy config.example.py config.py     # Windows
```

`config.py` is gitignored on purpose, your personal Notion table ID
never gets committed, whether you're the original author or someone
who forked this.

### 1. Create your Brief Tasks table in Notion

Make a new Notion page and add a table (a database) to it, called
**Brief Tasks**, with exactly these columns and types. The names and
types matter, the brief finds columns by name:

- `Task` (the title column that every table starts with)
- `Project` (type: Select)
- `Due` (type: Date)
- `Done when` (type: Text)
- `Urgent` (type: Checkbox)
- `Done` (type: Checkbox)
- `Time` (type: Text)

Then copy the table's ID, the 32-character code in its page URL, into
`TASKS_DATABASE_ID` in your `config.py`.

**Quick check:** `python check_notion_access.py` reads the table and
warns about a missing column, a row with no Project, or a Due value it
can't read as a date.

*Older way, still supported:* if `TASKS_DATABASE_ID` is left as the
placeholder, the brief instead reads a project index page
(`INDEX_PAGE_ID`) where each project links to a page with a "Next
actions" list. The table is simpler and is what to use for anything new.

### 2. Get a Notion token

Go to your Notion integrations settings and create a **Personal
access token** (simplest option, it automatically sees everything
your account can see, no per-page sharing step needed). Set it as:

```
NOTION_API_KEY=...
```

### 3. Get Google Calendar access

This one needs an actual OAuth flow, not just a copy-pasted key,
since Google doesn't offer simple API keys for reading a personal
calendar. Short version:

1. Create a project at console.cloud.google.com, enable the Google
   Calendar API.
2. Set up the OAuth consent screen (add yourself as a test user).
3. Create an OAuth Client ID, type **Desktop app**. This gives you a
   Client ID and Client Secret.
4. Set those as `GOOGLE_OAUTH_CLIENT_ID` and
   `GOOGLE_OAUTH_CLIENT_SECRET`, then run:

```
python authorize_calendar.py
```

This opens your browser, has you approve read-only access to your
own calendar, and prints a refresh token once. Set that as
`GOOGLE_CALENDAR_REFRESH_TOKEN`.

**One thing worth doing once everything works:** an app left in
Google's "Testing" publishing status has refresh tokens that expire
every 7 days. Publishing the app (Google Cloud Console → your project
→ Audience → Publish app) removes that limit. For a personal app with
one user and a non-restricted scope like `calendar.readonly`, this
doesn't require Google's full verification review, but it does ask
for a homepage URL and a privacy policy URL. Two public Notion pages
work fine for this, they don't need to be fancy, just real and
reachable. After publishing, re-run `authorize_calendar.py` once more
to get a fresh token, the one issued while still in Testing keeps its
7-day limit even after you publish.

## Testing before you trust it

```
python check_notion_access.py     # confirms your Brief Tasks table is readable and flags problems
python morning_brief.py --mock            # no network calls at all, uses fake example data
python morning_brief.py --skip-calendar   # real Notion, fake calendar, for testing before Calendar's set up
python morning_brief.py                   # the real thing
```

Run `check_notion_access.py` after changing the table's columns. To try
a table without editing `config.py`, pass its ID:
`python morning_brief.py --skip-calendar --table <table id>`.

## Seeing it as a popup instead of terminal text

`run_daily.pyw` renders the brief as a small, styled desktop popup
(Windows-tested) instead of printing plain text. `popup.py` handles
the rendering. Double-click `run_daily.pyw` to try it, once your env
vars are set as permanent environment variables (not just session
variables in one terminal window, since double-clicking a file starts
a separate process that never sees session-only variables).

## Running it daily, unattended

**Windows (tested):** Task Scheduler. Action = Start a program,
Program/script = `pythonw.exe` (not `python.exe`, so no console window
flashes behind the popup), Add arguments = the full path to
`run_daily.pyw` in quotes, followed by `--scheduled`. Set "Start in" to
the project folder.

Triggers (add all that apply, the launcher shows the brief at most once
per day, never before 6 AM, so extra triggers are harmless):

- **Daily at your chosen time**, for when the computer is awake.
- **On an event** (New trigger, Begin the task: On an event, Basic):
  Log `System`, Source `Microsoft-Windows-Power-Troubleshooter`,
  Event ID `1`. That is the "resumed from sleep" event, so the first
  time a sleeping laptop wakes up, the brief appears.

Why the second trigger matters: a laptop that sleeps overnight is
asleep at 7:00, so a clock-time trigger alone never fires. The
"Run task as soon as possible after a scheduled start is missed"
checkbox is supposed to cover that, but in testing it worked once and
then stopped working, so don't rely on it. Triggering on the wake
event itself does not depend on it.

Other settings worth getting right: uncheck "Start the task only if
the computer is on AC power" (or it skips mornings on battery), and
leave "If the task is already running" on "Do not start a new
instance". Popups close themselves at 4 AM, so an old window can never
block the next morning.

When something doesn't show up, read `morning_brief.log` (it sits next
to `run_daily.pyw`). It records every launch, why a run was skipped,
and any error with its full traceback, which matters because a
`pythonw.exe` program has no console to show errors in.

**Mac (untested):** launchd. A small plist file in `~/Library/LaunchAgents/`
runs `python3 morning_brief.py` at the time you choose and writes its
output to a log file. launchd runs a job it missed during sleep when
the Mac wakes. The environment variables go inside the plist, since a
Terminal window's variables don't reach background jobs.

**Linux (untested):** a systemd user timer with `OnCalendar=` and
`Persistent=true`, or cron. Cron skips any run that falls while the
machine is asleep or off, so the timer is the better choice for a
laptop. If `pip` refuses to install with an "externally-managed-
environment" error, create a virtual environment (`python3 -m venv
.venv`) and have the scheduled job call `.venv/bin/python`.

On Mac and Linux, `morning_brief.py` prints plain text and has no
once-a-day rule, since that lives in the Windows launcher
(`run_daily.pyw`). The popup (`popup.py`) is only tested on Windows, it
asks for the Segoe UI font and uses Windows-specific window handling,
so it will look and behave differently elsewhere. Tkinter may also
need installing (`python3-tk` on Debian or Ubuntu).

## Troubleshooting

`dump_database.py` prints the raw columns and values Notion returns for
the first few rows of your table, use it if `check_notion_access.py`
reports something odd.

`dump_blocks.py "<page ID or URL>"` prints the raw structure Notion
actually returns for a page, block types, nesting, everything. Useful
if `check_notion_access.py` reports a page as reachable but empty,
since that usually means the page's real structure doesn't match what
the parser expects (a different heading level, items nested a level
deeper than usual, etc.), and this shows you the ground truth instead
of guessing.

## Notes for anyone building their own version of this

This template intentionally keeps ranking logic fully deterministic
(no AI model call involved in deciding what shows up), so it's fast,
free to run, and easy to reason about. If you want something smarter,
like a one-line written summary of the day instead of just a sorted
list, that's a reasonable place to add a small LLM call, this project
just didn't need one for what it does.

The reader expects the table described above and finds columns by
name, so renaming one (other than the title column) means the brief
treats it as empty. `check_notion_access.py` will say so. If your
Notion habits are different, say a board or a list instead of a table,
`dump_database.py` shows exactly what Notion sends for each row, which
is the starting point for adapting `parse_task_row()` in
`morning_brief.py`.
