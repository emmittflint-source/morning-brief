"""
Rich overlay window for the morning brief. Builds its visuals directly
from the same structured data morning_brief.py computes internally
(gather_brief_data), rather than re-parsing the plain-text version meant
for a terminal. The plain string has markdown-style markers (**bold**,
*(rotation)*) that were never meant to be read by a human directly,
they only make sense once something renders them, and Tkinter's Text
widget doesn't do that on its own.

Uses Tkinter, which ships with Python on Windows already, no extra
install needed.
"""

import sys
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import font as tkfont

import config
from morning_brief import (
    days_left, describe_days, describe_deadline_days,
    format_event_time, format_month_day,
)

# Without this, Windows treats the app as DPI-unaware on a scaled display
# (125%/150%/etc., which is most laptops), renders it at a lower internal
# resolution, then stretches the whole window to fit, which is exactly
# what blurry/pixelated text looks like. This has to run before any Tk
# window is created, so it's at import time here, not inside show_popup.
if sys.platform == "win32":
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor, Windows 8.1+
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()  # fallback for older Windows
    except Exception:
        pass  # never let a DPI call be the reason the brief fails to show

BG = "#0f1420"
FG = "#e8ebf2"
MUTED = "#8b93a7"
ACCENT = "#5aa9ff"
HEADER_BG = "#1f3a5f"
ERROR_HEADER_BG = "#7a1f1f"
WARNING = "#e0a030"
ROTATION_COLOR = "#b48ce0"

URGENT = "#ff6b6b"      # <= 3 days left
SOON = "#e0a030"        # <= 7 days left
LATER = "#7fd88f"       # anything further out


MIN_WIDTH, MIN_HEIGHT = 340, 260


def compute_resized_geometry(origin, dx, dy, edges, min_w=MIN_WIDTH, min_h=MIN_HEIGHT):
    """
    New (x, y, w, h) for a window being dragged by one or two of its edges.

    origin: dict with the window's x, y, w, h when the drag started.
    dx, dy: how far the mouse has moved since then.
    edges:  any of "n", "s", "e", "w".

    Dragging the right or bottom edge only changes the size. Dragging the
    left or top edge changes the size AND moves the window, and the
    opposite edge must stay exactly where it was, even once the minimum
    size stops the window from shrinking any further.
    """
    x, y, w, h = origin["x"], origin["y"], origin["w"], origin["h"]
    if "e" in edges:
        w = max(min_w, origin["w"] + dx)
    if "w" in edges:
        w = max(min_w, origin["w"] - dx)
        x = origin["x"] + (origin["w"] - w)
    if "s" in edges:
        h = max(min_h, origin["h"] + dy)
    if "n" in edges:
        h = max(min_h, origin["h"] - dy)
        y = origin["y"] + (origin["h"] - h)
    return x, y, w, h


def _urgency_color(n_days: int) -> str:
    if n_days <= 3:
        return URGENT
    if n_days <= 7:
        return SOON
    return LATER


def _add_item_line(text_widget, n, item, name, today, is_rotation=False):
    text_widget.insert("end", f"{n}.  ", "item_number")

    if item.get("urgent"):
        text_widget.insert("end", "URGENT  ", "urgent_tag")
    if is_rotation:
        text_widget.insert("end", "ROTATION  ", "rotation_tag")

    text_widget.insert("end", f"{item['next_action']}", "action")

    if item.get("done_when"):
        text_widget.insert("end", f"\n     done when {item['done_when']}", "done_when")

    text_widget.insert("end", f"\n     {name}", "project_name")

    if item.get("due"):
        n_days = days_left(item["due"], today)
        if is_rotation:
            text_widget.insert("end", f"  ·  due {format_month_day(item['due'])}", "muted")
        else:
            color_tag = "urgency_" + _urgency_color(n_days).lstrip("#")
            text_widget.tag_configure(color_tag, foreground=_urgency_color(n_days))
            text_widget.insert("end", f"  ·  ", "muted")
            text_widget.insert("end", describe_days(n_days), (color_tag, "bold"))

    text_widget.insert("end", "\n\n")


def build_brief_view(parent, today, data):
    """Populate a Text widget (parent) with the rich rendering. Split out
    from show_popup so it can be exercised without a real Tk mainloop."""
    body_font = tkfont.Font(family="Segoe UI", size=10)
    bold_font = tkfont.Font(family="Segoe UI", size=10, weight="bold")
    italic_font = tkfont.Font(family="Segoe UI", size=9, slant="italic")
    small_font = tkfont.Font(family="Segoe UI", size=9)
    heading_font = tkfont.Font(family="Segoe UI", size=11, weight="bold")

    parent.configure(font=body_font, bg=BG, fg=FG, borderwidth=0, padx=14, pady=12,
                      wrap="word", spacing3=2)

    parent.tag_configure("heading", font=heading_font, foreground=FG)
    parent.tag_configure("bold", font=bold_font)
    parent.tag_configure("muted", foreground=MUTED, font=small_font)
    parent.tag_configure("item_number", font=bold_font, foreground=ACCENT)
    parent.tag_configure("action", font=body_font, foreground=FG)
    parent.tag_configure("done_when", font=italic_font, foreground=MUTED)
    parent.tag_configure("project_name", font=small_font, foreground=ACCENT)
    parent.tag_configure("rotation_tag", font=small_font, foreground=ROTATION_COLOR)
    parent.tag_configure("urgent_tag", font=bold_font, foreground=URGENT)
    parent.tag_configure("warning", font=small_font, foreground=WARNING)

    day_str = f"{today.strftime('%a')} {format_month_day(today)}"
    parent.insert("end", f"Today · {day_str}\n", "heading")
    if data["events"]:
        ev_str = ", ".join(
            f"{e['summary']} {format_event_time(e['start'])}" for e in data["events"][:4]
        )
    else:
        ev_str = "nothing on the calendar"
    parent.insert("end", f"{ev_str}\n\n", "muted")

    n = 1
    for name, item in data["top3"]:
        _add_item_line(parent, n, item, name, today)
        n += 1
    if data["rotation_entry"]:
        name, item = data["rotation_entry"]
        _add_item_line(parent, n, item, name, today, is_rotation=True)

    if not data["top3"] and not data["rotation_entry"]:
        parent.insert("end", "No open tasks right now.\n\n", "muted")

    parent.insert("end", "Deadlines\n", "heading")
    dl_parts = []
    for d in config.DEADLINES:
        from morning_brief import try_parse_date
        target = try_parse_date(d["date"])
        dl_parts.append(f"{d['label']}: {describe_deadline_days(days_left(target, today))}")
    parent.insert("end", "  ·  ".join(dl_parts) + "\n", "muted")

    if data["empty_projects"]:
        parent.insert("end", f"\nNo Next actions block: {', '.join(data['empty_projects'])}\n", "warning")
    if data["failed_projects"]:
        reasons = ", ".join(f"{name} ({msg})" for name, msg in data["failed_projects"].items())
        parent.insert("end", f"\nCouldn't read: {reasons}\n", "warning")

    parent.configure(state="disabled")


def show_popup(title: str, text_or_data, is_error: bool = False, today=None):
    """
    Two modes, kept backward compatible:
    - text_or_data is a dict from gather_brief_data(): rich rendering.
      today must be the same date the data was built for, passed in
      explicitly rather than recomputed here, since re-deriving "today"
      independently could disagree with the actual run (timezone edge
      cases, or a manual --date test run).
    - text_or_data is a plain string (error messages, e.g. FetchError
      text): shown as simple text, same as before. today is unused here.
    """
    root = tk.Tk()
    root.title(title)  # still set, for whatever OS-level fallback references it
    root.attributes("-topmost", True)

    # Bigger default now that the DPI fix renders at true size instead of
    # Windows quietly upscaling a smaller window to fill the same space.
    width, height = 560, 480
    screen_w = root.winfo_screenwidth()
    x = screen_w - width - 24
    y = 48
    root.geometry(f"{width}x{height}+{x}+{y}")
    root.configure(bg=BG)

    # No OS title bar at all: this is the tradeoff that makes min/max/close
    # live inside the blue bar itself instead of a native bar above it.
    # Real cost: Windows typically won't show a frameless window in the
    # taskbar. -topmost above is what keeps it reachable regardless.
    root.overrideredirect(True)

    header_bg = ERROR_HEADER_BG if is_error else HEADER_BG
    titlebar = tk.Frame(root, bg=header_bg, height=34)
    titlebar.pack(fill="x", side="top")
    titlebar.pack_propagate(False)

    title_label = tk.Label(
        titlebar, text=title, bg=header_bg, fg="white",
        font=("Segoe UI", 11, "bold"), anchor="w",
    )
    title_label.pack(side="left", fill="y", padx=(12, 0))

    def _titlebar_button(symbol, hover_bg, command):
        btn = tk.Button(
            titlebar, text=symbol, command=command, bg=header_bg, fg="white",
            activeforeground="white", font=("Segoe UI", 10), bd=0,
            width=3, cursor="hand2",
        )
        btn.bind("<Enter>", lambda e: btn.configure(bg=hover_bg))
        btn.bind("<Leave>", lambda e: btn.configure(bg=header_bg))
        return btn

    close_btn = _titlebar_button("\u2715", "#c0392b", root.destroy)

    maximize_state = {"is_max": False, "restore_geometry": None}

    def toggle_maximize():
        if not maximize_state["is_max"]:
            maximize_state["restore_geometry"] = root.geometry()
            sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
            root.geometry(f"{sw}x{sh}+0+0")
            maximize_state["is_max"] = True
        else:
            if maximize_state["restore_geometry"]:
                root.geometry(maximize_state["restore_geometry"])
            maximize_state["is_max"] = False

    maximize_btn = _titlebar_button("\u25a1", "#2a4a73", toggle_maximize)

    def minimize():
        # overrideredirect windows don't minimize normally on Windows;
        # the standard workaround is dropping it right before iconify()
        # and restoring it once the window is mapped again.
        root.overrideredirect(False)
        root.iconify()

    def on_map(event):
        if root.state() == "normal":
            root.overrideredirect(True)

    root.bind("<Map>", on_map)
    minimize_btn = _titlebar_button("\u2013", "#2a4a73", minimize)

    close_btn.pack(side="right")
    maximize_btn.pack(side="right")
    minimize_btn.pack(side="right")

    # Dragging: with no OS title bar, the window has no native drag
    # handle either, so the custom one has to provide it.
    drag_origin = {"x": 0, "y": 0}

    def start_drag(event):
        drag_origin["x"] = event.x
        drag_origin["y"] = event.y

    def do_drag(event):
        new_x = root.winfo_x() + event.x - drag_origin["x"]
        new_y = root.winfo_y() + event.y - drag_origin["y"]
        root.geometry(f"+{new_x}+{new_y}")

    for widget in (titlebar, title_label):
        widget.bind("<ButtonPress-1>", start_drag)
        widget.bind("<B1-Motion>", do_drag)

    # No Scrollbar widget: a Tk Text widget scrolls with the mouse wheel
    # on its own regardless, the Scrollbar was only ever the visible
    # track, removing it doesn't remove actual scrolling.
    body = tk.Text(root, borderwidth=0, highlightthickness=0)
    body.pack(fill="both", expand=True)

    if isinstance(text_or_data, dict):
        if today is None:
            raise ValueError("show_popup: today= is required when passing a data dict")
        build_brief_view(body, today, text_or_data)
    else:
        body.configure(bg=BG, fg=FG, font=("Segoe UI", 10), padx=14, pady=12,
                        wrap="word")
        body.insert("1.0", text_or_data)
        body.configure(state="disabled")

    # Frameless windows lose the OS's own resize grips along with its title
    # bar, so these eight handles (four edges, four corners) rebuild them.
    # Uses event.x_root/y_root (absolute screen position) rather than
    # widget-relative coordinates, so the drag stays accurate even while
    # the window itself moves and changes size mid-drag.
    resize_origin = {}
    win = sys.platform == "win32"
    # name: (edges, Windows cursor, other-platform cursor, place() arguments)
    grip_specs = {
        "left":   ("w",  "sb_h_double_arrow", "sb_h_double_arrow",
                   dict(relx=0.0, rely=0.0, relheight=1.0, width=5, anchor="nw")),
        "right":  ("e",  "sb_h_double_arrow", "sb_h_double_arrow",
                   dict(relx=1.0, rely=0.0, relheight=1.0, width=5, anchor="ne")),
        "top":    ("n",  "sb_v_double_arrow", "sb_v_double_arrow",
                   dict(relx=0.0, rely=0.0, relwidth=1.0, height=5, anchor="nw")),
        "bottom": ("s",  "sb_v_double_arrow", "sb_v_double_arrow",
                   dict(relx=0.0, rely=1.0, relwidth=1.0, height=5, anchor="sw")),
        # corners last, so they sit on top of the edges where the two overlap
        "top_left":     ("nw", "size_nw_se", "top_left_corner",
                         dict(relx=0.0, rely=0.0, width=8, height=8, anchor="nw")),
        "top_right":    ("ne", "size_ne_sw", "top_right_corner",
                         dict(relx=1.0, rely=0.0, width=8, height=8, anchor="ne")),
        "bottom_left":  ("sw", "size_ne_sw", "bottom_left_corner",
                         dict(relx=0.0, rely=1.0, width=8, height=8, anchor="sw")),
        "bottom_right": ("se", "size_nw_se", "bottom_right_corner",
                         dict(relx=1.0, rely=1.0, width=8, height=8, anchor="se")),
    }

    def make_handlers(edges):
        def start(event):
            resize_origin.update(px=event.x_root, py=event.y_root,
                                 x=root.winfo_x(), y=root.winfo_y(),
                                 w=root.winfo_width(), h=root.winfo_height())

        def drag(event):
            x, y, w, h = compute_resized_geometry(
                resize_origin, event.x_root - resize_origin["px"],
                event.y_root - resize_origin["py"], edges)
            root.geometry(f"{w}x{h}+{x}+{y}")
        return start, drag

    for grip_name, (edges, cursor_win, cursor_other, place_args) in grip_specs.items():
        try:
            grip = tk.Frame(root, bg=header_bg, cursor=cursor_win if win else cursor_other)
        except tk.TclError:
            grip = tk.Frame(root, bg=header_bg)   # an unknown cursor name must never stop the window opening
        grip.place(**place_args)
        on_press, on_drag = make_handlers(edges)
        grip.bind("<ButtonPress-1>", on_press)
        grip.bind("<B1-Motion>", on_drag)

    # A popup left open overnight must not block tomorrow's brief: Task
    # Scheduler ignores a new launch while an old instance is still alive.
    # So every popup closes itself at the next 4 AM local time.
    now = datetime.now()
    next_4am = now.replace(hour=4, minute=0, second=0, microsecond=0)
    if next_4am <= now:
        next_4am += timedelta(days=1)
    root.after(int((next_4am - now).total_seconds() * 1000), root.destroy)

    root.focus_force()
    root.mainloop()
