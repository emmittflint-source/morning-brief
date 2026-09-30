# Morning brief

A personal daily agent that reads a "Next actions" list off your own
Notion pages, checks your Google Calendar, and shows you a short
summary each morning: today's events, your top 3 most urgent tasks
(by due date), and one more picked in rotation so nothing gets
permanently buried.

**Read-only.** It never writes to Notion or your calendar, only reads.

## How it decides what to show you

- Every project you track gets one line on a Notion "index" page:
  `Project Name - <link to that project's Notion page>`.
- Each project's own page has a section starting with a line that says
  exactly **"Next actions"** (a heading or plain paragraph, either
  works), followed by a numbered or bulleted list, one item per task.
  Each item can optionally have `Done when: ...`, `Due: ...`, and
  `Time: ...` as sub-lines under it.
- Every run: the 3 soonest-due items win the top slots (one project
  can only take one of the 3 slots, so a single busy project can't
  crowd everything else out), and a 4th slot rotates fairly among
  whatever's left with no due date at all, so those don't just sit
  invisible forever.
- Add a new project any time by adding one line to the index page.
  No code ever needs to change for that.

## Setup

```
pip install -r requirements.txt
```

Copy the config template and fill in your own values:

```
cp config.example.py config.py       # Mac/Linux
copy config.example.py config.py     # Windows
```

`config.py` is gitignored on purpose, your personal Notion page ID
never gets committed, whether you're the original author or someone
who forked this.

### 1. Create your project index page in Notion

Make a new Notion page. Add one line per project, in this exact shape
(paste a real link to each project's page, don't just type the URL as
plain text, let Notion turn it into an actual page mention):

```
My Side Project - <link to that page>
Fitness Goals - <link to that page>
```

Copy that index page's ID (the 32-character string in its URL) into
`INDEX_PAGE_ID` in your `config.py`.

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
python check_notion_access.py     # confirms the index page and every listed project page are readable
python morning_brief.py --mock            # no network calls at all, uses fake example data
python morning_brief.py --skip-calendar   # real Notion, fake calendar, for testing before Calendar's set up
python morning_brief.py                   # the real thing
```

Run `check_notion_access.py` any time you add a project or change
something on the index page, it checks each page independently, so
one broken page won't hide behind a wall of noise from the other
working ones.

## Seeing it as a popup instead of terminal text

`run_daily.pyw` renders the brief as a small, styled desktop popup
(Windows-tested) instead of printing plain text. `popup.py` handles
the rendering. Double-click `run_daily.pyw` to try it, once your env
vars are set as permanent environment variables (not just session
variables in one terminal window, since double-clicking a file starts
a separate process that never sees session-only variables).

## Running it daily, unattended

**Windows (tested):** Task Scheduler, a daily trigger at whatever
time you want, Action = Start a program, Program/script =
`pythonw.exe` (not `python.exe`, so no console window flashes behind
the popup), Add arguments = the full path to `run_daily.pyw`. Two
settings worth getting right: uncheck "Start the task only if the
computer is on AC power" (or it'll skip mornings on battery), and
check "Run task as soon as possible after a scheduled start is
missed" (so a sleeping laptop catches up instead of silently skipping
the day).

**Mac/Linux (untested, but the equivalent):** a cron job calling
`python morning_brief.py`, the popup won't work as-is since it's
built with Windows quirks in mind (a DPI-awareness fix that's a
no-op elsewhere, and Windows-specific cursor names with a fallback),
but the terminal output works anywhere Python does.

## Troubleshooting

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

The parser expects the specific Notion structure described above. If
your own Notion habits look different (a table instead of a list, a
different section header), `dump_blocks.py` is the tool to figure out
what actually needs to change in `find_action_item_blocks()` in
`morning_brief.py`.
