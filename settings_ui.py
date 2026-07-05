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

_BLOCK = 96
_PAD = 6
_PANEL_W = 340


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


def _letter_tile(name: str | None, size: int) -> Image.Image:
    """Flat colored square with the entry's first letter; color is a stable
    hash of the name so tiles don't change between refreshes."""
    name_str = str(name or "")
    hue = (zlib.crc32(name_str.encode("utf-8")) % 360) / 360
    r, g, b = (int(c * 255) for c in colorsys.hsv_to_rgb(hue, 0.45, 0.62))
    img = Image.new("RGBA", (size, size), (r, g, b, 255))
    letter = (name_str.strip()[:1] or "?").upper()
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
    name = str(entry.get("name") or "")
    base_key = src or "letter:" + name
    key = (base_key, dimmed)
    if key in _photo_cache:
        return _photo_cache[key]
    pil = _pil_cache.get(base_key)
    if pil is None:
        pil = _extract_exe_icon(src)
        if pil is None:
            pil = _letter_tile(name, _ICON_SIZE)
        pil = pil.resize((_ICON_SIZE, _ICON_SIZE), Image.LANCZOS)
        _pil_cache[base_key] = pil
    if dimmed:
        alpha = pil.getchannel("A")
        pil = pil.convert("L").convert("RGBA")
        pil.putalpha(alpha)
    photo = ImageTk.PhotoImage(pil)
    _photo_cache[key] = photo
    return photo


def _make_block(parent: tk.Widget, entry: dict, command) -> tk.Frame:
    enabled = entry.get("enabled", True)
    f = tk.Frame(
        parent,
        width=_BLOCK,
        height=_BLOCK,
        cursor="hand2",
        highlightthickness=1,
        highlightbackground="#dcdcdc",
    )
    f.pack_propagate(False)
    icon = tk.Label(f, image=_icon_image(entry, dimmed=not enabled))
    name = entry.get("name", "")
    if len(name) > 12:
        name = name[:11] + "…"
    label = tk.Label(
        f,
        text=name,
        font=("Segoe UI", 9),
        fg="#404040" if enabled else "#a0a0a0",
    )
    icon.pack(pady=(12, 2))
    label.pack()

    def on_enter(_e):
        f.configure(highlightbackground="#4a90d9")

    def on_leave(_e):
        f.configure(highlightbackground="#dcdcdc")

    for w in (f, icon, label):
        w.bind("<Button-1>", lambda _e: command())
        w.bind("<Enter>", on_enter)
        w.bind("<Leave>", on_leave)
    return f


def _make_plus_tile(parent: tk.Widget, command) -> tk.Canvas:
    c = tk.Canvas(
        parent, width=_BLOCK, height=_BLOCK, highlightthickness=0, cursor="hand2"
    )
    c.create_rectangle(5, 5, _BLOCK - 5, _BLOCK - 5, dash=(3, 2), outline="#a0a0a0")
    c.create_text(
        _BLOCK / 2, _BLOCK / 2, text="+", font=("Segoe UI", 24), fill="#a0a0a0"
    )
    c.bind("<Button-1>", lambda _e: command())
    return c


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
    root.geometry("720x480")
    root.minsize(480, 320)
    root.bind("<<Lift>>", lambda e: (root.deiconify(), root.lift(), root.focus_force()))
    _photo_cache.clear()  # PhotoImages died with any previous Tk root

    cfg = config.load()
    cfg.setdefault("hotkey", config.DEFAULT_HOTKEY)
    cfg.setdefault("entries", [])

    def launch_now():
        threading.Thread(target=launcher.launch_all, daemon=True).start()

    top = ttk.Frame(root, padding=(10, 8))
    top.pack(fill="x")
    ttk.Label(top, text="App Launcher", font=("Segoe UI", 12, "bold")).pack(side="left")
    ttk.Button(top, text="Launch Now", command=launch_now).pack(side="right")

    host = tk.Frame(root)  # grid viewport now, panel overlay target in Task 4
    host.pack(fill="both", expand=True)

    canvas = tk.Canvas(host, highlightthickness=0)
    vsb = ttk.Scrollbar(host, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=vsb.set)
    vsb.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    inner = tk.Frame(canvas)
    inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")
    inner.bind(
        "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )
    canvas.bind_all(
        "<MouseWheel>", lambda e: canvas.yview_scroll(-e.delta // 120, "units")
    )

    grid_cols = [0]  # current column count; reflow only when it changes

    def persist():
        config.save(cfg)
        refresh()

    def refresh():
        for w in inner.winfo_children():
            w.destroy()
        cols = max(1, canvas.winfo_width() // (_BLOCK + 2 * _PAD))
        grid_cols[0] = cols
        for i, entry in enumerate(cfg["entries"]):
            block = _make_block(inner, entry, lambda i=i: load_panel(i))
            block.grid(row=i // cols, column=i % cols, padx=_PAD, pady=_PAD)
        n = len(cfg["entries"])
        plus = _make_plus_tile(inner, lambda: load_panel(None))
        plus.grid(row=n // cols, column=n % cols, padx=_PAD, pady=_PAD)

    def on_canvas_resize(event):
        canvas.itemconfigure(inner_id, width=event.width)
        if max(1, event.width // (_BLOCK + 2 * _PAD)) != grid_cols[0]:
            refresh()

    canvas.bind("<Configure>", on_canvas_resize)

    # --- details panel (placed off-canvas left; slides in over the grid) ---
    panel = tk.Frame(host, highlightthickness=1, highlightbackground="#c0c0c0")
    anim = {"busy": False, "open": False}
    state = {"index": None}  # index being edited; None = adding new

    def slide(frm, to, done=None):
        anim["busy"] = True
        steps = 10

        def tick(i):
            panel.place_configure(x=int(frm + (to - frm) * i / steps))
            if i < steps:
                root.after(15, lambda: tick(i + 1))
            else:
                anim["busy"] = False
                if done:
                    done()

        tick(1)

    def open_panel():
        if anim["open"]:
            return
        anim["open"] = True
        panel.place(x=-_PANEL_W, y=0, width=_PANEL_W, relheight=1.0)
        panel.lift()
        slide(-_PANEL_W, 0)

    def close_panel():
        if not anim["open"] or anim["busy"]:
            return
        anim["open"] = False
        slide(0, -_PANEL_W, done=panel.place_forget)

    header = ttk.Frame(panel, padding=(8, 8, 8, 0))
    header.pack(fill="x")
    ttk.Button(header, text="◀ Back", command=close_panel).pack(side="left")

    kind_var = tk.StringVar(value="app")
    name_var = tk.StringVar()
    path_var = tk.StringVar()
    args_var = tk.StringVar()
    match_var = tk.StringVar()
    workdir_var = tk.StringVar()
    cmd_var = tk.StringVar()
    mon_var = tk.StringVar(value="1")
    zone_var = tk.StringVar(value="maximized")

    body = ttk.Frame(panel, padding=12)
    body.pack(fill="both", expand=True)
    body.columnconfigure(1, weight=1)

    def browse_file():
        p = filedialog.askopenfilename(
            parent=root, filetypes=[("Programs", "*.exe"), ("All files", "*.*")]
        )
        if p:
            path_var.set(p.replace("/", "\\"))

    def browse_dir():
        p = filedialog.askdirectory(parent=root)
        if p:
            workdir_var.set(p.replace("/", "\\"))

    def add_row(r, label, widget, extra=None):
        lbl = ttk.Label(body, text=label)
        lbl.grid(row=r, column=0, sticky="w", pady=3, padx=(0, 8))
        widget.grid(row=r, column=1, sticky="we", pady=3)
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
            body,
            from_=1,
            to=max(monitor_count, 9),
            textvariable=mon_var,
            width=5,
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

    def save_entry():
        name = name_var.get().strip()
        if not name:
            messagebox.showwarning("App Launcher", "Name is required.", parent=root)
            return
        try:
            monitor = max(1, int(mon_var.get()))
        except ValueError:
            monitor = 1
        i = state["index"]
        old = cfg["entries"][i] if i is not None else {}
        kind = kind_var.get()
        entry = {
            "name": name,
            "enabled": old.get("enabled", True),
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
                "App Launcher",
                f"{check_path} does not exist. Save anyway?",
                parent=root,
            ):
                return
        if i is None:
            cfg["entries"].append(entry)
        else:
            cfg["entries"][i] = entry
        persist()
        close_panel()

    def remove_entry():
        del cfg["entries"][state["index"]]
        persist()
        close_panel()

    def toggle_entry():
        e = cfg["entries"][state["index"]]
        e["enabled"] = not e.get("enabled", True)
        persist()
        close_panel()

    btns = ttk.Frame(body)
    btns.grid(row=9, column=0, columnspan=3, sticky="we", pady=(12, 0))
    save_btn = ttk.Button(btns, text="Save", command=save_entry)
    toggle_btn = ttk.Button(btns, text="Disable", command=toggle_entry)
    remove_btn = ttk.Button(btns, text="Remove", command=remove_entry)
    save_btn.pack(side="left")

    def load_panel(i):
        if anim["busy"]:
            return
        state["index"] = i
        e = cfg["entries"][i] if i is not None else {}
        kind_var.set(e.get("kind", "app"))
        name_var.set(e.get("name", ""))
        path_var.set(e.get("path", ""))
        args_var.set(e.get("args", ""))
        match_var.set(e.get("match_process", ""))
        workdir_var.set(e.get("workdir", ""))
        cmd_var.set(e.get("startup_command", ""))
        mon_var.set(str(e.get("monitor", 1)))
        zone_var.set(e.get("zone", "maximized"))
        update_kind()
        toggle_btn.pack_forget()
        remove_btn.pack_forget()
        if i is not None:
            toggle_btn.configure(text="Disable" if e.get("enabled", True) else "Enable")
            toggle_btn.pack(side="left", padx=6)
            remove_btn.pack(side="left")
        open_panel()

    refresh()
    root.mainloop()
