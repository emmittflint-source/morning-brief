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
from tkinter import font as tkfont

import config
from morning_brief import days_left, format_event_time, format_month_day

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


def _urgency_color(n_days: int) -> str:
    if n_days <= 3:
        return URGENT
    if n_days <= 7:
        return SOON
    return LATER


def _add_item_line(text_widget, n, item, name, today, is_rotation=False):
    text_widget.insert("end", f"{n}.  ", "item_number")

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
            text_widget.insert("end", f"{n_days} day{'s' if n_days != 1 else ''} left", (color_tag, "bold"))

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

    parent.insert("end", "Deadlines\n", "heading")
    dl_parts = []
    for d in config.DEADLINES:
        from morning_brief import try_parse_date
        target = try_parse_date(d["date"])
        dl_parts.append(f"{d['label']}: {days_left(target, today)}d")
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

    # Frameless windows lose the OS's own resize grips along with its
    # title bar, so these three handles rebuild just that part by hand.
    # Uses event.x_root/y_root (absolute screen position) rather than
    # widget-relative coordinates, so the drag delta stays accurate even
    # as the window itself changes size mid-drag.
    MIN_WIDTH, MIN_HEIGHT = 340, 260
    resize_origin = {"x": 0, "y": 0, "w": 0, "h": 0}

    def start_resize(event):
        resize_origin["x"] = event.x_root
        resize_origin["y"] = event.y_root
        resize_origin["w"] = root.winfo_width()
        resize_origin["h"] = root.winfo_height()

    def resize_right(event):
        new_w = max(MIN_WIDTH, resize_origin["w"] + (event.x_root - resize_origin["x"]))
        root.geometry(f"{new_w}x{root.winfo_height()}")

    def resize_bottom(event):
        new_h = max(MIN_HEIGHT, resize_origin["h"] + (event.y_root - resize_origin["y"]))
        root.geometry(f"{root.winfo_width()}x{new_h}")

    def resize_corner(event):
        new_w = max(MIN_WIDTH, resize_origin["w"] + (event.x_root - resize_origin["x"]))
        new_h = max(MIN_HEIGHT, resize_origin["h"] + (event.y_root - resize_origin["y"]))
        root.geometry(f"{new_w}x{new_h}")

    grip_right = tk.Frame(root, bg=header_bg, cursor="sb_h_double_arrow", width=4)
    grip_right.place(relx=1.0, rely=0.0, relheight=1.0, anchor="ne")
    grip_right.bind("<ButtonPress-1>", start_resize)
    grip_right.bind("<B1-Motion>", resize_right)

    grip_bottom = tk.Frame(root, bg=header_bg, cursor="sb_v_double_arrow", height=4)
    grip_bottom.place(relx=0.0, rely=1.0, relwidth=1.0, anchor="sw")
    grip_bottom.bind("<ButtonPress-1>", start_resize)
    grip_bottom.bind("<B1-Motion>", resize_bottom)

    # "size_nw_se" is a Windows-only cursor name; X11 has no such name and
    # raises TclError on it outright, this is exactly what caught the bug
    # during testing rather than it silently only breaking on Windows.
    corner_cursor = "size_nw_se" if sys.platform == "win32" else "bottom_right_corner"
    grip_corner = tk.Frame(root, bg=header_bg, cursor=corner_cursor, width=10, height=10)
    grip_corner.place(relx=1.0, rely=1.0, anchor="se")
    grip_corner.bind("<ButtonPress-1>", start_resize)
    grip_corner.bind("<B1-Motion>", resize_corner)

    root.focus_force()
    root.mainloop()
