# CustomTkinter Settings UI Restyle — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle `settings_ui.py` with CustomTkinter for a modern rounded look, preserving all current behavior.

**Architecture:** Swap the `tk.Tk` root for `ctk.CTk`, replace every `ttk`/`tk` widget with its `CTk*` equivalent, and delete the manual palette/`ttk.Style` theming layer — CustomTkinter's `set_appearance_mode` follows Windows light/dark automatically and recolors widgets live. The custom pieces (Win32 icon extraction, letter-tile fallback, `place()` slide animation) are kept and only reparented onto CTk frames.

**Tech Stack:** Python 3.11, CustomTkinter, Pillow, pywin32, tkinter (dialogs only).

## Global Constraints

- Windows-only; Python 3.11.9; run with the `py` launcher (not `python`).
- Behavior-preserving: no change to what the Settings window does (grid, slide-in edit panel, App/Terminal field toggle, Save/Disable/Remove, Find/browse, theme selector, Launch Now, lift-on-reopen).
- Only `settings_ui.py` and `requirements.txt` change. Do not touch `config.py`, `launcher.py`, `monitors.py`, `app_index.py`, `tray.py`.
- Threading model unchanged: UI runs on its own daemon thread; `config.save()` is the only cross-thread contact point.
- `cfg["theme"]` values are exactly `"system" | "light" | "dark"` and map 1:1 to `ctk.set_appearance_mode(...)`.
- The App/Terminal control is a `CTkSegmentedButton` with display values `["App", "Terminal"]`, mapped to stored `kind` values `"app"/"terminal"`.

---

### Task 1: Add the CustomTkinter dependency

**Files:**
- Modify: `requirements.txt`

**Interfaces:**
- Consumes: nothing.
- Produces: `import customtkinter as ctk` available to Task 2.

- [ ] **Step 1: Add the dependency line**

Append `customtkinter` to `requirements.txt` so it reads:

```
pywin32
pystray
customtkinter
```

- [ ] **Step 2: Install**

Run: `py -m pip install -r requirements.txt`
Expected: `customtkinter` installs successfully (pulls in `darkdetect`).

- [ ] **Step 3: Verify import**

Run: `py -c "import customtkinter as c; print(c.__version__)"`
Expected: prints a version string (e.g. `5.2.x`), no traceback.

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "chore: add customtkinter dependency"
```

---

### Task 2: Rewrite `settings_ui.py` on CustomTkinter

**Files:**
- Modify (full rewrite): `settings_ui.py`

**Interfaces:**
- Consumes: `config.load/save/DEFAULT_HOTKEY/ZONES`, `launcher.launch_all`, `monitors.get_monitors`, `app_index.resolve` (all unchanged public functions).
- Produces: `open_settings() -> None` (unchanged public entry point, called by `tray.py`/`main.py`).

**Design notes (why the shape below):**
- `_palette()` and the entire `ttk.Style` block are **deleted** — CTk widgets self-theme.
- The theme dropdown just calls `ctk.set_appearance_mode(...)` + `config.save(...)`; no widget-tree rebuild (the old `build_ui()` wrapper is gone — the UI is built once in `_run`).
- The old `Canvas + Scrollbar + inner + create_window + mousewheel` machinery is replaced by a single `CTkScrollableFrame`. Column reflow is driven by a `<Configure>` binding on the containing `host` frame (not on the scrollable frame, to avoid CTkScrollableFrame's restricted `bind`).
- Icons move from `ImageTk.PhotoImage` to `ctk.CTkImage`.
- `filedialog` and `messagebox` stay (CTk has no replacement).

- [ ] **Step 1: Replace the entire file with the CustomTkinter version**

Overwrite `settings_ui.py` with exactly this content:

```python
"""CustomTkinter entry-list editor. Runs on its own dedicated thread; only that
thread touches widgets. config.save() from UI callbacks is the only
cross-thread contact point."""

import colorsys
import os
import shutil
import threading
import tkinter as tk
import zlib
from tkinter import filedialog, messagebox

import customtkinter as ctk
import win32api
import win32con
import win32gui
import win32ui
from PIL import Image, ImageDraw, ImageFont

import config
import launcher
import monitors
import app_index

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

_ACCENT = "#4a90d9"
_TILE_BORDER = ("gray75", "gray30")  # (light, dark) default tile border


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
    img = ctk.CTkImage(light_image=pil, dark_image=pil, size=(_ICON_SIZE, _ICON_SIZE))
    _photo_cache[key] = img
    return img


def _make_block(parent, entry: dict, command) -> ctk.CTkFrame:
    enabled = entry.get("enabled", True)
    f = ctk.CTkFrame(
        parent, width=_BLOCK, height=_BLOCK,
        corner_radius=8, border_width=1, border_color=_TILE_BORDER,
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
    return f


def _make_plus_tile(parent, command) -> ctk.CTkFrame:
    f = ctk.CTkFrame(
        parent, width=_BLOCK, height=_BLOCK,
        corner_radius=8, border_width=1, border_color=_TILE_BORDER,
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
    global _root
    cfg = config.load()
    cfg.setdefault("hotkey", config.DEFAULT_HOTKEY)
    cfg.setdefault("entries", [])
    cfg.setdefault("theme", "system")

    ctk.set_appearance_mode(cfg.get("theme", "system"))
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    _root = root
    root.title("App Launcher — Settings")
    root.geometry("720x480")
    root.minsize(480, 320)
    root.bind("<<Lift>>", lambda e: (root.deiconify(), root.lift(), root.focus_force()))
    _photo_cache.clear()  # root recreated each open; drop stale CTkImages

    theme_labels = {"system": "System", "light": "Light", "dark": "Dark"}
    inv_theme = {v: k for k, v in theme_labels.items()}

    def launch_now():
        threading.Thread(target=launcher.launch_all, daemon=True).start()

    top = ctk.CTkFrame(root, fg_color="transparent")
    top.pack(fill="x", padx=10, pady=(8, 4))
    ctk.CTkLabel(top, text="App Launcher", font=("Segoe UI", 14, "bold")).pack(side="left")
    ctk.CTkButton(top, text="Launch Now", width=100, command=launch_now).pack(side="right")

    theme_var = tk.StringVar(value=theme_labels.get(cfg.get("theme", "system"), "System"))

    def on_theme_change(choice):
        cfg["theme"] = inv_theme.get(choice, "system")
        config.save(cfg)
        ctk.set_appearance_mode(cfg["theme"])

    ctk.CTkOptionMenu(
        top, values=list(theme_labels.values()),
        variable=theme_var, width=90, command=on_theme_change,
    ).pack(side="right", padx=(0, 8))

    host = ctk.CTkFrame(root, fg_color="transparent")
    host.pack(fill="both", expand=True)

    grid = ctk.CTkScrollableFrame(host, fg_color="transparent")
    grid.pack(side="left", fill="both", expand=True)

    grid_cols = [0]

    def persist():
        config.save(cfg)
        refresh()

    def refresh():
        for w in grid.winfo_children():
            w.destroy()
        cols = max(1, host.winfo_width() // (_BLOCK + 2 * _PAD))
        grid_cols[0] = cols
        for i, entry in enumerate(cfg["entries"]):
            block = _make_block(grid, entry, lambda i=i: load_panel(i))
            block.grid(row=i // cols, column=i % cols, padx=_PAD, pady=_PAD)
        n = len(cfg["entries"])
        plus = _make_plus_tile(grid, lambda: load_panel(None))
        plus.grid(row=n // cols, column=n % cols, padx=_PAD, pady=_PAD)

    def on_host_resize(event):
        if max(1, event.width // (_BLOCK + 2 * _PAD)) != grid_cols[0]:
            refresh()

    host.bind("<Configure>", on_host_resize)

    panel = ctk.CTkFrame(host, corner_radius=0, border_width=1, border_color=_TILE_BORDER)
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
        panel.place(x=-_PANEL_W, y=0, width=_PANEL_W, relheight=1.0)
        panel.lift()
        slide(-_PANEL_W, 0)

    def close_panel():
        if not anim["open"] or anim["busy"]:
            return
        anim["open"] = False
        slide(0, -_PANEL_W, done=panel.place_forget)

    header = ctk.CTkFrame(panel, fg_color="transparent")
    header.pack(fill="x", padx=8, pady=(8, 0))
    ctk.CTkButton(header, text="◀ Back", width=70, command=close_panel).pack(side="left")

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
        body, values=["App", "Terminal"], command=lambda _v: update_kind()
    )
    kind_seg.set("App")
    add_row(0, "Kind", kind_seg)
    add_row(1, "Name", ctk.CTkEntry(body, textvariable=name_var))

    path_buttons = ctk.CTkFrame(body, fg_color="transparent")
    ctk.CTkButton(path_buttons, text="Find", width=50, command=find_by_name).pack(side="left")
    ctk.CTkButton(path_buttons, text="…", width=30, command=browse_file).pack(
        side="left", padx=(4, 0)
    )
    app_widgets = (
        add_row(2, "Path", ctk.CTkEntry(body, textvariable=path_var), path_buttons)
        + add_row(3, "Args", ctk.CTkEntry(body, textvariable=args_var))
        + add_row(4, "Match process", ctk.CTkEntry(body, textvariable=match_var))
    )
    terminal_widgets = add_row(
        5, "Workdir",
        ctk.CTkEntry(body, textvariable=workdir_var),
        ctk.CTkButton(body, text="…", width=30, command=browse_dir),
    ) + add_row(6, "Startup command", ctk.CTkEntry(body, textvariable=cmd_var))

    monitor_count = max(1, len(monitors.get_monitors()))
    mon_values = [str(i) for i in range(1, max(monitor_count, 9) + 1)]
    add_row(7, "Monitor", ctk.CTkOptionMenu(body, values=mon_values, variable=mon_var, width=70))
    add_row(8, "Zone", ctk.CTkOptionMenu(body, values=list(config.ZONES), variable=zone_var))

    def update_kind():
        is_app = kind_seg.get() == "App"
        for w in app_widgets:
            w.grid() if is_app else w.grid_remove()
        for w in terminal_widgets:
            w.grid_remove() if is_app else w.grid()

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
        kind = "app" if kind_seg.get() == "App" else "terminal"
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
    btns.grid(row=9, column=0, columnspan=3, sticky="we", pady=(12, 0))
    save_btn = ctk.CTkButton(btns, text="Save", width=70, command=save_entry)
    toggle_btn = ctk.CTkButton(btns, text="Disable", width=70, command=toggle_entry)
    remove_btn = ctk.CTkButton(
        btns, text="Remove", width=70, command=remove_entry,
        fg_color="#a03030", hover_color="#c04040",
    )
    save_btn.pack(side="left")

    def load_panel(i):
        if anim["busy"]:
            return
        state["index"] = i
        e = cfg["entries"][i] if i is not None else {}
        kind_seg.set("App" if e.get("kind", "app") == "app" else "Terminal")
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
    _root = None
```

- [ ] **Step 2: Verify the module imports (syntax + all widget constructors resolve at import)**

Run: `py -c "import settings_ui; print('ok')"`
Expected: prints `ok`, no traceback. (This catches syntax errors and bad imports without launching the GUI, since `open_settings`/`_run` are not called at import.)

- [ ] **Step 3: Verify pure-logic tests still pass**

Run: `py -m pytest tests/ -q`
Expected: all pass (these cover `monitors`/`config`; this task doesn't touch them, so they must be unaffected).

- [ ] **Step 4: Manual launch verification**

Run: `py main.py`, then trigger the tray/hotkey to open Settings, and confirm each:
- Tile grid renders; resizing the window reflows columns.
- Clicking a tile slides the edit panel in from the left; ◀ Back slides it out.
- The plus tile opens a blank panel (add mode).
- App ↔ Terminal segmented button toggles the correct field set (Path/Args/Match vs Workdir/Startup command).
- Save with empty Name shows the "Name is required" warning; saving a nonexistent path shows the confirm dialog.
- Disable/Enable toggles the entry (tile dims); Remove deletes it.
- Find and `…` populate Path/Workdir.
- Theme menu switches System/Light/Dark live (widgets recolor, no rebuild flash).
- Launch Now runs the launcher; re-opening Settings while open lifts the existing window.

If any CTk API mismatch surfaces here (e.g. an unexpected kwarg), fix it in place and re-run Steps 2–4 before committing.

- [ ] **Step 5: Re-index GitNexus (project rule) and commit**

```bash
npx gitnexus analyze
git add settings_ui.py
git commit -m "feat: restyle settings UI with customtkinter"
```

---

## Self-Review

**Spec coverage:**
- Dependency added → Task 1. ✓
- `ctk.CTk` root + `set_appearance_mode` + delete `_palette`/`style` → Task 2 Step 1. ✓
- Delete theme-rebuild; live theme switch → `on_theme_change` in Step 1; verified Step 4. ✓
- Widget swaps (Button/Entry/OptionMenu/Spinbox→OptionMenu/SegmentedButton/tile frames/CTkImage) → Step 1 code. ✓
- `CTkScrollableFrame` replacing Canvas machinery; reflow via `host` `<Configure>` → Step 1 code. ✓
- Plus tile → `CTkFrame` with "+" → `_make_plus_tile`. ✓
- Kept as-is: filedialog/messagebox, Win32 extraction, `_letter_tile`, dimmed grayscale, `place()` slide, thread lifecycle → all present in Step 1. ✓
- Verification: import check + pure tests + manual checklist → Steps 2–4. ✓

**Placeholder scan:** No TBD/TODO/"handle edge cases"; full file content provided. ✓

**Type consistency:** `_icon_image` returns `ctk.CTkImage` (cache typed to match); `_make_block`/`_make_plus_tile` return `ctk.CTkFrame` and drop the old `pal` param; segmented button read via `kind_seg.get()` → `"App"/"Terminal"` mapped to `"app"/"terminal"` consistently in `load_panel` and `save_entry`. `open_settings` signature unchanged for `tray.py`/`main.py`. ✓
