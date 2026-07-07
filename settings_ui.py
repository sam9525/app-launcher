"""CustomTkinter entry-list editor. Runs on its own dedicated thread; only that
thread touches widgets. config.save() from UI callbacks is the only
cross-thread contact point."""

import colorsys
import os
import shutil
import threading
import tkinter as tk
import winreg
import zlib
from tkinter import filedialog, messagebox

import customtkinter as ctk
import win32api
import win32con
import win32gui
import win32ui
from PIL import Image, ImageDraw, ImageFont

import app_index
import config
import launcher
import monitors
import zone_preview

_ui_thread: threading.Thread | None = None
_root: ctk.CTk | None = None

_ICON_SIZE = 48
# CTkImages are cached per (source, dimmed); _run() clears the cache on every
# window open (root is recreated each open). The PIL cache survives sessions.
_photo_cache: dict[tuple[str, bool], ctk.CTkImage] = {}
_pil_cache: dict[str, Image.Image] = {}

_BLOCK = 96
_PAD = 6
_PANEL_W = 340

_ACCENT = "#4a90d9"  # fallback; replaced at runtime by the Windows accent color
_TILE_BORDER = ("gray75", "gray30")  # (light, dark) default tile border


def _resolve(pair):
    """Pick the light or dark member of a CTk [light, dark] color pair for the
    current appearance mode — tk.Canvas needs a concrete bg color."""
    return pair[0] if ctk.get_appearance_mode() == "Light" else pair[1]


def _system_accent() -> str:
    """Windows accent color as #RRGGBB (DWM AccentColor is 0xAABBGGRR)."""
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\DWM"
        ) as k:
            val, _ = winreg.QueryValueEx(k, "AccentColor")
        return f"#{val & 0xFF:02x}{(val >> 8) & 0xFF:02x}{(val >> 16) & 0xFF:02x}"
    except OSError:
        return _ACCENT


def _shade(hex_color: str, factor: float) -> str:
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
    r, g, b = (max(0, min(255, int(c * factor))) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


def _apply_accent(accent: str) -> None:
    """Point CTk's shared theme at the system accent for the widgets in use."""
    hover = _shade(accent, 0.85)
    t = ctk.ThemeManager.theme
    t["CTkButton"]["fg_color"] = [accent, accent]
    t["CTkButton"]["hover_color"] = [hover, hover]
    t["CTkOptionMenu"]["fg_color"] = [accent, accent]
    t["CTkOptionMenu"]["button_color"] = [hover, hover]
    t["CTkOptionMenu"]["button_hover_color"] = [_shade(accent, 0.7)] * 2
    t["CTkSwitch"]["progress_color"] = [accent, accent]
    t["CTkSegmentedButton"]["selected_color"] = [accent, accent]
    t["CTkSegmentedButton"]["selected_hover_color"] = [hover, hover]


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
    hdc_handle = None
    memdc = None
    bmp = None
    old_bmp = None
    try:
        size = win32api.GetSystemMetrics(win32con.SM_CXICON)
        hdc_handle = win32gui.GetDC(0)
        hdc = win32ui.CreateDCFromHandle(hdc_handle)
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(hdc, size, size)
        memdc = hdc.CreateCompatibleDC()
        old_bmp = memdc.SelectObject(bmp)
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
        if not img.getchannel("A").getbbox():
            img.putalpha(255)  # DrawIcon leaves alpha=0 for alpha-less icons
        return img
    except Exception:
        return None
    finally:
        if memdc and old_bmp:
            try:
                memdc.SelectObject(old_bmp)
            except Exception:
                pass
        if memdc:
            try:
                memdc.DeleteDC()
            except Exception:
                pass
        if bmp:
            try:
                win32gui.DeleteObject(bmp.GetHandle())
            except Exception:
                pass
        if hdc_handle:
            try:
                win32gui.ReleaseDC(0, hdc_handle)
            except Exception:
                pass
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


def _icon_image(entry: dict, dimmed: bool = False) -> ctk.CTkImage:
    """48px tile icon for an entry, letter-tile fallback, cached."""
    kind = entry.get("kind")
    if kind == "terminal":
        src = shutil.which("wt.exe") or ""
    elif kind == "explorer":
        src = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "explorer.exe")
    else:
        src = entry.get("path", "") or ""
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
    img = ctk.CTkImage(light_image=pil, dark_image=pil, size=(_ICON_SIZE, _ICON_SIZE))
    _photo_cache[key] = img
    return img


def _make_block(
    parent, entry: dict, command, on_toggle, on_open, mons, accent
) -> ctk.CTkFrame:
    enabled = entry.get("enabled", True)
    wrap = ctk.CTkFrame(parent, fg_color="transparent")
    f = ctk.CTkFrame(
        wrap,
        width=_BLOCK,
        height=_BLOCK,
        corner_radius=8,
        border_width=1,
        border_color=_TILE_BORDER,
    )
    f.pack_propagate(False)
    icon = ctk.CTkLabel(f, text="", image=_icon_image(entry, dimmed=not enabled))
    name = entry.get("name") or ""
    if len(name) > 12:
        name = name[:11] + "…"
    label = ctk.CTkLabel(f, text=name, font=("Segoe UI", 12))
    if not enabled:
        label.configure(text_color="gray")
    icon.pack(pady=(12, 2))
    label.pack()
    f.pack()

    sw = ctk.CTkSwitch(wrap, text="", width=40, command=on_toggle)
    (sw.select if enabled else sw.deselect)()
    sw.pack(pady=(6, 2))
    zone_preview.build_map(
        wrap,
        mons,
        entry.get("monitor", 1),
        entry.get("zone", "maximized"),
        width=_BLOCK,
        height=30,
        accent=accent,
        bg=_resolve(ctk.ThemeManager.theme["CTk"]["fg_color"]),
    ).pack(pady=(4, 2))
    ctk.CTkButton(wrap, text="Open", width=_BLOCK, height=24, command=on_open).pack()

    def on_enter(_e):
        f.configure(border_color=_ACCENT)

    def on_leave(_e):
        x, y = f.winfo_pointerxy()
        fx, fy = f.winfo_rootx(), f.winfo_rooty()
        fw, fh = f.winfo_width(), f.winfo_height()
        if not (fx <= x < fx + fw and fy <= y < fy + fh):
            f.configure(border_color=_TILE_BORDER)

    f.bind("<Enter>", on_enter)
    f.bind("<Leave>", on_leave)
    for w in (f, icon, label):
        w.bind("<Button-1>", lambda _e: command())
    return wrap


def _make_plus_tile(parent, command) -> ctk.CTkFrame:
    f = ctk.CTkFrame(
        parent,
        width=_BLOCK,
        height=_BLOCK,
        corner_radius=8,
        border_width=1,
        border_color=_TILE_BORDER,
    )
    f.pack_propagate(False)
    lbl = ctk.CTkLabel(f, text="+", font=("Segoe UI", 28), text_color="gray")
    lbl.pack(expand=True)
    for w in (f, lbl):
        w.bind("<Button-1>", lambda _e: command())
    return f


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
    global _root, _ACCENT
    cfg = config.load()
    cfg.setdefault("hotkey", config.DEFAULT_HOTKEY)
    cfg.setdefault("entries", [])
    cfg.setdefault("theme", "system")

    mons = monitors.get_monitors()

    ctk.set_appearance_mode(cfg.get("theme", "system"))
    ctk.set_default_color_theme("blue")
    _ACCENT = _system_accent()
    _apply_accent(_ACCENT)

    root = ctk.CTk()
    _root = root
    root.title("App Launcher — Settings")
    root.geometry("720x480")
    root.minsize(480, 320)
    root.bind("<<Lift>>", lambda e: (root.deiconify(), root.lift(), root.focus_force()))
    _photo_cache.clear()  # root recreated each open; drop stale CTkImages

    def launch_now():
        threading.Thread(target=launcher.launch_all, daemon=True).start()

    top = ctk.CTkFrame(root, fg_color="transparent")
    top.pack(fill="x", padx=10, pady=(8, 4))
    ctk.CTkLabel(top, text="App Launcher", font=("Segoe UI", 14, "bold")).pack(
        side="left"
    )
    ctk.CTkButton(top, text="Launch Now", width=100, command=launch_now).pack(
        side="right"
    )

    # CTkSwitch is binary, so it only carries light/dark; a stored "system"
    # theme is resolved to its current effective value for the initial state.
    theme_var = tk.StringVar(value=config.resolve_theme(cfg))

    def on_theme_toggle():
        cfg["theme"] = theme_var.get()
        config.save(cfg)
        ctk.set_appearance_mode(cfg["theme"])
        refresh()

    ctk.CTkSwitch(
        top,
        text="Dark",
        variable=theme_var,
        onvalue="dark",
        offvalue="light",
        command=on_theme_toggle,
    ).pack(side="right", padx=(0, 8))

    host = ctk.CTkFrame(root, fg_color="transparent")
    host.pack(fill="both", expand=True)

    grid = ctk.CTkScrollableFrame(host, fg_color="transparent")
    grid.pack(side="left", fill="both", expand=True)

    grid_cols = [0]

    def persist():
        config.save(cfg)
        refresh()

    def toggle_at(i):
        e = cfg["entries"][i]
        e["enabled"] = not e.get("enabled", True)
        persist()

    def open_one(entry):
        def target():
            if not launcher._run_lock.acquire(blocking=False):
                return
            try:
                launcher._handle_entry(entry, {})
            finally:
                launcher._run_lock.release()
        threading.Thread(target=target, daemon=True).start()

    def refresh():
        for w in grid.winfo_children():
            w.destroy()
        cols = max(1, host.winfo_width() // (_BLOCK + 2 * _PAD))
        grid_cols[0] = cols
        for i, entry in enumerate(cfg["entries"]):
            block = _make_block(
                grid,
                entry,
                lambda i=i: load_panel(i),
                lambda i=i: toggle_at(i),
                lambda e=entry: open_one(e),
                mons,
                _ACCENT,
            )
            block.grid(row=i // cols, column=i % cols, padx=_PAD, pady=_PAD)
        n = len(cfg["entries"])
        plus = _make_plus_tile(grid, lambda: load_panel(None))
        plus.grid(row=n // cols, column=n % cols, padx=_PAD, pady=_PAD)

    def on_host_resize(event):
        if max(1, event.width // (_BLOCK + 2 * _PAD)) != grid_cols[0]:
            refresh()

    host.bind("<Configure>", on_host_resize)

    panel = ctk.CTkFrame(
        host, width=_PANEL_W, corner_radius=0, border_width=1, border_color=_TILE_BORDER
    )
    anim = {"busy": False, "open": False}
    state = {"index": None}

    def slide(frm, to, done=None):
        anim["busy"] = True
        steps = 10

        def tick(i):
            if not root.winfo_exists() or not panel.winfo_exists():
                return
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
        for child in grid.winfo_children():
            if isinstance(child, ctk.CTkFrame):
                child.configure(border_color=_TILE_BORDER)
        anim["open"] = True
        panel.place(x=-_PANEL_W, y=0, relheight=1.0)
        panel.lift()
        slide(-_PANEL_W, 0)

    def close_panel():
        if not anim["open"] or anim["busy"]:
            return
        anim["open"] = False
        slide(0, -_PANEL_W, done=panel.place_forget)

    header = ctk.CTkFrame(panel, fg_color="transparent")
    header.pack(fill="x", padx=8, pady=(8, 0))
    ctk.CTkButton(header, text="◀ Back", width=70, command=close_panel).pack(
        side="left"
    )

    name_var = tk.StringVar()
    path_var = tk.StringVar()
    args_var = tk.StringVar()
    match_var = tk.StringVar()
    workdir_var = tk.StringVar()
    cmd_var = tk.StringVar()
    mon_var = tk.StringVar(value="1")
    zone_var = tk.StringVar(value="maximized")

    body = ctk.CTkFrame(panel, fg_color="transparent")
    body.pack(fill="both", expand=True, padx=12, pady=12)
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

    def find_by_name():
        p = app_index.resolve(name_var.get())
        if p:
            path_var.set(p.replace("/", "\\"))
        else:
            messagebox.showinfo(
                "App Launcher",
                "No match found — use the … button to browse.",
                parent=root,
            )

    def add_row(r, label, widget, extra=None):
        lbl = ctk.CTkLabel(body, text=label)
        lbl.grid(row=r, column=0, sticky="w", pady=3, padx=(0, 8))
        widget.grid(row=r, column=1, sticky="we", pady=3)
        if extra is not None:
            extra.grid(row=r, column=2, padx=(4, 0))
        return [lbl, widget] + ([extra] if extra is not None else [])

    kind_seg = ctk.CTkSegmentedButton(
        body, values=["App", "Terminal", "Explorer"], command=lambda _v: update_kind()
    )
    kind_seg.set("App")
    add_row(0, "Kind", kind_seg)
    add_row(1, "Name", ctk.CTkEntry(body, textvariable=name_var))

    path_buttons = ctk.CTkFrame(body, fg_color="transparent")
    ctk.CTkButton(path_buttons, text="Find", width=50, command=find_by_name).pack(
        side="left"
    )
    ctk.CTkButton(path_buttons, text="…", width=30, command=browse_file).pack(
        side="left", padx=(4, 0)
    )
    app_widgets = (
        add_row(2, "Path", ctk.CTkEntry(body, textvariable=path_var), path_buttons)
        + add_row(3, "Args", ctk.CTkEntry(body, textvariable=args_var))
        + add_row(4, "Match process", ctk.CTkEntry(body, textvariable=match_var))
    )
    terminal_widgets = add_row(
        5,
        "Workdir",
        ctk.CTkEntry(body, textvariable=workdir_var),
        ctk.CTkButton(body, text="…", width=30, command=browse_dir),
    ) + add_row(6, "Startup command", ctk.CTkEntry(body, textvariable=cmd_var))

    folders_box = ctk.CTkTextbox(body, height=90)

    def browse_folder_append():
        p = filedialog.askdirectory(parent=root)
        if p:
            p = p.replace("/", "\\")
            cur = folders_box.get("1.0", "end").strip()
            folders_box.delete("1.0", "end")
            folders_box.insert("1.0", cur + "\n" + p if cur else p)

    explorer_widgets = add_row(
        5,
        "Folders",
        folders_box,
        ctk.CTkButton(body, text="…", width=30, command=browse_folder_append),
    )

    monitor_count = max(1, len(mons))
    mon_values = [str(i) for i in range(1, monitor_count + 1)]
    mon_menu = ctk.CTkOptionMenu(body, values=mon_values, variable=mon_var, width=70)
    add_row(7, "Monitor", mon_menu)
    zone_menu = ctk.CTkOptionMenu(body, values=list(config.ZONES), variable=zone_var)
    add_row(8, "Zone", zone_menu)

    map_holder = ctk.CTkFrame(body, fg_color="transparent")
    map_holder.grid(row=9, column=0, columnspan=3, sticky="we", pady=(8, 0))

    def redraw_map():
        for w in map_holder.winfo_children():
            w.destroy()
        try:
            mon = max(1, int(mon_var.get()))
        except ValueError:
            mon = 1
        zone_preview.build_map(
            map_holder,
            mons,
            mon,
            zone_var.get(),
            width=_PANEL_W - 40,
            height=72,
            accent=_ACCENT,
            bg=_resolve(ctk.ThemeManager.theme["CTkFrame"]["fg_color"]),
            on_pick=on_pick_zone,
        ).pack()

    def on_pick_zone(mon, zone):
        mon_var.set(str(mon))
        zone_var.set(zone)
        redraw_map()

    mon_menu.configure(command=lambda _v: redraw_map())
    zone_menu.configure(command=lambda _v: redraw_map())

    def update_kind():
        kind = kind_seg.get()
        sets = {"App": app_widgets, "Terminal": terminal_widgets, "Explorer": explorer_widgets}
        for name, widgets in sets.items():
            for w in widgets:
                w.grid() if name == kind else w.grid_remove()

    def save_entry():
        if anim["busy"]:
            return
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
        kind = {"App": "app", "Terminal": "terminal", "Explorer": "explorer"}[kind_seg.get()]
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
            check_paths = [path] if path else []
        elif kind == "terminal":
            entry["workdir"] = workdir_var.get().strip()
            entry["startup_command"] = cmd_var.get().strip()
            check_paths = [entry["workdir"]] if entry["workdir"] else []
        else:  # explorer
            folders = launcher.parse_folder_lines(folders_box.get("1.0", "end"))
            if not folders:
                messagebox.showwarning(
                    "App Launcher", "At least one folder is required.", parent=root
                )
                return
            entry["folders"] = folders
            check_paths = folders

        missing = [p for p in check_paths if not os.path.exists(p)]
        if missing:
            if len(missing) == 1:
                msg = f"{missing[0]} does not exist. Save anyway?"
            else:
                msg = "The following folders do not exist:\n" + "\n".join(missing) + "\n\nSave anyway?"
            if not messagebox.askyesno(
                "App Launcher",
                msg,
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
        if state["index"] is None:
            return
        if anim["busy"]:
            return
        del cfg["entries"][state["index"]]
        persist()
        close_panel()

    def toggle_entry():
        if state["index"] is None:
            return
        if anim["busy"]:
            return
        e = cfg["entries"][state["index"]]
        e["enabled"] = not e.get("enabled", True)
        persist()
        close_panel()

    btns = ctk.CTkFrame(body, fg_color="transparent")
    btns.grid(row=10, column=0, columnspan=3, sticky="we", pady=(12, 0))
    save_btn = ctk.CTkButton(btns, text="Save", width=70, command=save_entry)
    toggle_btn = ctk.CTkButton(btns, text="Disable", width=70, command=toggle_entry)
    remove_btn = ctk.CTkButton(
        btns,
        text="Remove",
        width=70,
        command=remove_entry,
        fg_color="#a03030",
        hover_color="#c04040",
    )
    save_btn.pack(side="left")

    def load_panel(i):
        if anim["busy"]:
            return
        state["index"] = i
        e = cfg["entries"][i] if i is not None else {}
        kind_seg.set(
            {"app": "App", "terminal": "Terminal", "explorer": "Explorer"}[
                e.get("kind", "app")
            ]
        )
        name_var.set(e.get("name", ""))
        path_var.set(e.get("path", ""))
        args_var.set(e.get("args", ""))
        match_var.set(e.get("match_process", ""))
        workdir_var.set(e.get("workdir", ""))
        cmd_var.set(e.get("startup_command", ""))
        folders_box.delete("1.0", "end")
        folders_box.insert("1.0", "\n".join(e.get("folders", [])))
        mon_var.set(str(e.get("monitor", 1)))
        zone_var.set(e.get("zone", "maximized"))
        update_kind()
        redraw_map()
        toggle_btn.pack_forget()
        remove_btn.pack_forget()
        if i is not None:
            toggle_btn.configure(text="Disable" if e.get("enabled", True) else "Enable")
            toggle_btn.pack(side="left", padx=6)
            remove_btn.pack(side="left")
        open_panel()

    refresh()
    root.mainloop()
    _root = None
