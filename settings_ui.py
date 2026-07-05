"""Tkinter entry-list editor. Runs on its own dedicated thread; only that
thread touches widgets. config.save() from UI callbacks is the only
cross-thread contact point."""

import colorsys
import os
import shutil
import threading
import tkinter as tk
import zlib
from tkinter import filedialog, messagebox, ttk

import win32api
import win32con
import win32gui
import win32ui
from PIL import Image, ImageDraw, ImageFont, ImageTk

import config
import launcher
import monitors

_ui_thread: threading.Thread | None = None
_root: tk.Tk | None = None

_ICON_SIZE = 48
# PhotoImages are bound to the Tk root that created them — _run() clears
# _photo_cache on every window open; the PIL cache survives across sessions.
_photo_cache: dict[tuple[str, bool], ImageTk.PhotoImage] = {}
_pil_cache: dict[str, Image.Image] = {}


def _extract_exe_icon(path: str) -> Image.Image | None:
    """First icon of an .exe as RGBA, or None if it can't be extracted."""
    if not path or not os.path.exists(path):
        return None
    try:
        large, small = win32gui.ExtractIconEx(path, 0)
    except Exception:
        return None
    for h in (small or []) + (large or [])[1:]:
        win32gui.DestroyIcon(h)
    if not large:
        return None
    hicon = large[0]
    try:
        size = win32api.GetSystemMetrics(win32con.SM_CXICON)
        hdc = win32ui.CreateDCFromHandle(win32gui.GetDC(0))
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(hdc, size, size)
        memdc = hdc.CreateCompatibleDC()
        memdc.SelectObject(bmp)
        memdc.DrawIcon((0, 0), hicon)
        info = bmp.GetInfo()
        img = Image.frombuffer(
            "RGBA",
            (info["bmWidth"], info["bmHeight"]),
            bmp.GetBitmapBits(True),
            "raw",
            "BGRA",
            0,
            1,
        )
        # ponytail: leaks one small GDI bitmap per distinct exe — bounded by
        # the icon cache, not worth the handle bookkeeping
        if not img.getchannel("A").getbbox():
            img.putalpha(255)  # DrawIcon leaves alpha=0 for alpha-less icons
        return img
    except Exception:
        return None
    finally:
        win32gui.DestroyIcon(hicon)


def _letter_tile(name: str, size: int) -> Image.Image:
    """Flat colored square with the entry's first letter; color is a stable
    hash of the name so tiles don't change between refreshes."""
    hue = (zlib.crc32(name.encode("utf-8")) % 360) / 360
    r, g, b = (int(c * 255) for c in colorsys.hsv_to_rgb(hue, 0.45, 0.62))
    img = Image.new("RGBA", (size, size), (r, g, b, 255))
    letter = (name.strip()[:1] or "?").upper()
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("segoeui.ttf", size // 2)
    except OSError:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), letter, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        ((size - w) / 2 - bbox[0], (size - h) / 2 - bbox[1]),
        letter,
        fill="white",
        font=font,
    )
    return img


def _icon_image(entry: dict, dimmed: bool = False) -> ImageTk.PhotoImage:
    """48px tile icon for an entry, letter-tile fallback, cached.
    Requires a live Tk root (PhotoImage creation)."""
    src = (
        shutil.which("wt.exe")
        if entry.get("kind") == "terminal"
        else entry.get("path", "")
    ) or ""
    base_key = src or "letter:" + entry.get("name", "")
    key = (base_key, dimmed)
    if key in _photo_cache:
        return _photo_cache[key]
    pil = _pil_cache.get(base_key)
    if pil is None:
        pil = _extract_exe_icon(src)
        if pil is None:
            pil = _letter_tile(entry.get("name", ""), _ICON_SIZE)
        pil = pil.resize((_ICON_SIZE, _ICON_SIZE), Image.LANCZOS)
        _pil_cache[base_key] = pil
    if dimmed:
        alpha = pil.getchannel("A")
        pil = pil.convert("L").convert("RGBA")
        pil.putalpha(alpha)
    photo = ImageTk.PhotoImage(pil)
    _photo_cache[key] = photo
    return photo


def open_settings() -> None:
    global _ui_thread
    if _ui_thread and _ui_thread.is_alive():
        try:
            # event_generate(when="tail") is the thread-safe way to poke Tk
            _root.event_generate("<<Lift>>", when="tail")
        except Exception:
            pass
        return
    _ui_thread = threading.Thread(target=_run, daemon=True)
    _ui_thread.start()


def _run() -> None:
    global _root
    root = tk.Tk()
    _root = root
    root.title("App Launcher — Settings")
    root.geometry("680x380")
    root.bind("<<Lift>>", lambda e: (root.deiconify(), root.lift(), root.focus_force()))

    cfg = config.load()
    cfg.setdefault("hotkey", config.DEFAULT_HOTKEY)
    cfg.setdefault("entries", [])

    columns = ("name", "kind", "monitor", "zone", "enabled")
    tree = ttk.Treeview(root, columns=columns, show="headings", selectmode="browse")
    for col, width in zip(columns, (250, 80, 70, 110, 70)):
        tree.heading(col, text=col.capitalize())
        tree.column(col, width=width, anchor="w")
    tree.pack(fill="both", expand=True, padx=8, pady=8)

    def refresh():
        tree.delete(*tree.get_children())
        for i, e in enumerate(cfg["entries"]):
            tree.insert(
                "",
                "end",
                iid=str(i),
                values=(
                    e.get("name", ""),
                    e.get("kind", ""),
                    e.get("monitor", 1),
                    e.get("zone", ""),
                    "yes" if e.get("enabled", True) else "no",
                ),
            )

    def selected_index():
        sel = tree.selection()
        return int(sel[0]) if sel else None

    def persist():
        config.save(cfg)  # every mutation writes immediately — no Apply button
        refresh()

    def add():
        entry = _entry_dialog(root, None)
        if entry:
            cfg["entries"].append(entry)
            persist()

    def edit():
        i = selected_index()
        if i is None:
            return
        entry = _entry_dialog(root, cfg["entries"][i])
        if entry:
            cfg["entries"][i] = entry
            persist()

    def remove():
        i = selected_index()
        if i is None:
            return
        del cfg["entries"][i]
        persist()

    def toggle():
        i = selected_index()
        if i is None:
            return
        cfg["entries"][i]["enabled"] = not cfg["entries"][i].get("enabled", True)
        persist()

    def launch_now():
        threading.Thread(target=launcher.launch_all, daemon=True).start()

    buttons = ttk.Frame(root)
    buttons.pack(fill="x", padx=8, pady=(0, 8))
    for text, command in (
        ("Add", add),
        ("Edit", edit),
        ("Remove", remove),
        ("✓ Enable/Disable", toggle),
        ("Launch Now", launch_now),
        ("Close", root.destroy),
    ):
        ttk.Button(buttons, text=text, command=command).pack(side="left", padx=2)

    refresh()
    root.mainloop()


def _entry_dialog(parent: tk.Tk, existing: dict | None) -> dict | None:
    """Modal add/edit form. Returns the new entry dict, or None on cancel."""
    e = existing or {}
    result: dict = {}

    dlg = tk.Toplevel(parent)
    dlg.title("Edit entry" if existing else "Add entry")
    dlg.grab_set()
    dlg.resizable(False, False)

    kind_var = tk.StringVar(value=e.get("kind", "app"))
    name_var = tk.StringVar(value=e.get("name", ""))
    path_var = tk.StringVar(value=e.get("path", ""))
    args_var = tk.StringVar(value=e.get("args", ""))
    match_var = tk.StringVar(value=e.get("match_process", ""))
    workdir_var = tk.StringVar(value=e.get("workdir", ""))
    cmd_var = tk.StringVar(value=e.get("startup_command", ""))
    mon_var = tk.StringVar(value=str(e.get("monitor", 1)))
    zone_var = tk.StringVar(value=e.get("zone", "maximized"))

    body = ttk.Frame(dlg, padding=10)
    body.pack(fill="both", expand=True)
    body.columnconfigure(1, weight=1, minsize=320)

    def browse_file():
        p = filedialog.askopenfilename(
            parent=dlg, filetypes=[("Programs", "*.exe"), ("All files", "*.*")]
        )
        if p:
            path_var.set(p.replace("/", "\\"))

    def browse_dir():
        p = filedialog.askdirectory(parent=dlg)
        if p:
            workdir_var.set(p.replace("/", "\\"))

    def add_row(r, label, widget, extra=None):
        lbl = ttk.Label(body, text=label)
        lbl.grid(row=r, column=0, sticky="w", pady=2, padx=(0, 8))
        widget.grid(row=r, column=1, sticky="we", pady=2)
        if extra is not None:
            extra.grid(row=r, column=2, padx=(4, 0))
        return [lbl, widget] + ([extra] if extra is not None else [])

    kind_frame = ttk.Frame(body)
    ttk.Radiobutton(
        kind_frame,
        text="App",
        variable=kind_var,
        value="app",
        command=lambda: update_kind(),
    ).pack(side="left")
    ttk.Radiobutton(
        kind_frame,
        text="Terminal",
        variable=kind_var,
        value="terminal",
        command=lambda: update_kind(),
    ).pack(side="left", padx=(8, 0))
    add_row(0, "Kind", kind_frame)
    add_row(1, "Name", ttk.Entry(body, textvariable=name_var))

    app_widgets = (
        add_row(
            2,
            "Path",
            ttk.Entry(body, textvariable=path_var),
            ttk.Button(body, text="…", width=3, command=browse_file),
        )
        + add_row(3, "Args", ttk.Entry(body, textvariable=args_var))
        + add_row(4, "Match process", ttk.Entry(body, textvariable=match_var))
    )
    terminal_widgets = add_row(
        5,
        "Workdir",
        ttk.Entry(body, textvariable=workdir_var),
        ttk.Button(body, text="…", width=3, command=browse_dir),
    ) + add_row(6, "Startup command", ttk.Entry(body, textvariable=cmd_var))

    monitor_count = max(1, len(monitors.get_monitors()))
    # accepts indexes past the connected count: monitors may be unplugged
    add_row(
        7,
        "Monitor",
        ttk.Spinbox(
            body, from_=1, to=max(monitor_count, 9), textvariable=mon_var, width=5
        ),
    )
    add_row(
        8,
        "Zone",
        ttk.Combobox(
            body, values=config.ZONES, textvariable=zone_var, state="readonly"
        ),
    )

    def update_kind():
        is_app = kind_var.get() == "app"
        for w in app_widgets:
            w.grid() if is_app else w.grid_remove()
        for w in terminal_widgets:
            w.grid_remove() if is_app else w.grid()

    update_kind()

    def save():
        name = name_var.get().strip()
        if not name:
            messagebox.showwarning("App Launcher", "Name is required.", parent=dlg)
            return
        try:
            monitor = max(1, int(mon_var.get()))
        except ValueError:
            monitor = 1
        kind = kind_var.get()
        entry = {
            "name": name,
            "enabled": e.get("enabled", True),
            "kind": kind,
            "monitor": monitor,
            "zone": zone_var.get(),
        }
        if kind == "app":
            path = path_var.get().strip()
            entry["path"] = path
            entry["args"] = args_var.get().strip()
            entry["match_process"] = match_var.get().strip() or os.path.basename(path)
            check_path = path
        else:
            entry["workdir"] = workdir_var.get().strip()
            entry["startup_command"] = cmd_var.get().strip()
            check_path = entry["workdir"]
        # warn but allow: the launcher already handles dead paths gracefully
        if check_path and not os.path.exists(check_path):
            if not messagebox.askyesno(
                "App Launcher", f"{check_path} does not exist. Save anyway?", parent=dlg
            ):
                return
        result.update(entry)
        dlg.destroy()

    footer = ttk.Frame(dlg, padding=(10, 0, 10, 10))
    footer.pack(fill="x")
    ttk.Button(footer, text="Save", command=save).pack(side="right")
    ttk.Button(footer, text="Cancel", command=dlg.destroy).pack(
        side="right", padx=(0, 6)
    )

    dlg.wait_window()
    return result or None
