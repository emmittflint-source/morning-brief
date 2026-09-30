#!/usr/bin/env python3
"""
Run this ONCE, after creating the OAuth client ID (Desktop app type) in
Google Cloud Console. It gets you the one thing the daily script needs
that a simple API key can't provide: a refresh token.

What happens: this opens your browser to Google's consent screen, you
approve read-only access to your own calendar, Google redirects back to
a tiny local server this script starts on your own machine, and the
refresh token gets printed once.

Usage:
  set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET first
  (session variables are fine, same as NOTION_API_KEY earlier), then:

  python authorize_calendar.py
"""

import http.server
import os
import sys
import threading
import urllib.parse
import webbrowser

import requests

REDIRECT_PORT = 8080
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/"
SCOPE = "https://www.googleapis.com/auth/calendar.readonly"

_received_code = {"value": None, "error": None}


class _RedirectHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()

        if "code" in params:
            _received_code["value"] = params["code"][0]
            self.wfile.write(b"<html><body>Got it. You can close this tab and go back to the terminal.</body></html>")
        else:
            _received_code["error"] = params.get("error", ["unknown error"])[0]
            self.wfile.write(b"<html><body>Something went wrong. Check the terminal.</body></html>")

    def log_message(self, format, *args):
        pass  # keep the terminal clean, the script prints its own status


def wait_for_redirect():
    server = http.server.HTTPServer(("localhost", REDIRECT_PORT), _RedirectHandler)
    server.timeout = 120
    server.handle_request()  # blocks for exactly one request, then returns


def main():
    client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET first, same way you set NOTION_API_KEY.")
        sys.exit(1)

    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",  # forces a refresh token even if you've approved this app before
    })

    print("Opening your browser to approve access...")
    print("If it doesn't open automatically, go to this URL:\n")
    print(auth_url)
    print()
    webbrowser.open(auth_url)

    server_thread = threading.Thread(target=wait_for_redirect, daemon=True)
    server_thread.start()
    server_thread.join(timeout=125)

    if _received_code["error"]:
        print(f"Google returned an error: {_received_code['error']}")
        sys.exit(1)
    if not _received_code["value"]:
        print("Timed out waiting for the browser redirect. Try again.")
        sys.exit(1)

    resp = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": client_id,
        "client_secret": client_secret,
        "code": _received_code["value"],
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    })

    if not resp.ok:
        print(f"Token exchange failed ({resp.status_code}): {resp.text}")
        sys.exit(1)

    tokens = resp.json()
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        print(
            "No refresh_token in the response. This usually means you'd already "
            "approved this app before without revoking it. Go to "
            "https://myaccount.google.com/permissions, remove this app's access, "
            "and run this script again."
        )
        sys.exit(1)

    print()
    print("Success. Set this as GOOGLE_CALENDAR_REFRESH_TOKEN (don't screenshot or paste it anywhere else):")
    print()
    print(refresh_token)


if __name__ == "__main__":
    main()
