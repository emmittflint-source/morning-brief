"""
Generic example data for testing without real credentials or a real
Notion workspace set up yet. Nothing here is real, it's just enough to
see the ranking logic and popup actually work end to end.

Run with: python morning_brief.py --mock
"""

from datetime import date

EVENTS = [
    {"summary": "Team standup", "start": "2026-09-30T09:00:00-10:00"},
    {"summary": "Dentist appointment", "start": "2026-09-30T14:30:00-10:00"},
]

PROJECT_ITEMS = {
    "Home Renovation": [
        {"next_action": "Get three quotes for the kitchen countertop",
         "done_when": "three written quotes are saved in the shared folder",
         "due": date(2026, 10, 3), "raw_due": "Oct 3", "time": "45 min"},
    ],
    "Side Business": [
        {"next_action": "File the quarterly estimated tax payment",
         "done_when": "payment confirmation email is received",
         "due": date(2026, 10, 5), "raw_due": "Oct 5", "time": "20 min"},
        {"next_action": "Update the pricing page on the website",
         "done_when": "new prices are live and confirmed in an incognito window",
         "due": date(2026, 10, 12), "raw_due": "Oct 12", "time": "30 min"},
    ],
    "Learning Spanish": [
        {"next_action": "Finish the next Duolingo unit",
         "done_when": "unit shows complete in the app",
         "due": None, "raw_due": None, "time": "15 min"},
    ],
    "Book Club": [
        {"next_action": "Read chapters 4 through 6",
         "done_when": "chapter 6 is finished before Thursday's meeting",
         "due": None, "raw_due": None, "time": "60 min"},
    ],
    "Car Trouble": [
        {"next_action": "Renew the car registration",
         "done_when": "the new sticker is on the plate",
         "due": None, "raw_due": None, "time": "20 min", "urgent": True},
    ],
    "Garage Cleanout": [
        {"next_action": "Sort the tools into keep, donate, and toss piles",
         "done_when": "all three piles exist and the workbench is clear",
         "due": None, "raw_due": None, "time": "40 min"},
    ],
}
