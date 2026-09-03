"""Tkinter WYSIWYG designer for the HAS GUI Creator.

Retro-styled canvas that mimics a Workbench 2.0 window so the layout the user
sees matches what intuition.library will render. All state lives in a
MetadataManager; the canvas is a pure view that is fully repainted on change.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import List, Optional

from . import has_export, hasmeta
from .model import (
    BITMAP_COLOR_DEPTHS,
    BORDER_TOP,
    CHAR_H,
    CHAR_W,
    Control,
    ControlType,
    MetadataManager,
)

# Workbench 2.0 four-colour palette.
PEN_GREY = "#a0a0a0"
PEN_BLACK = "#000000"
PEN_WHITE = "#ffffff"
PEN_BLUE = "#3b67a2"
PEN_DESK = "#5a5a5a"
PEN_SELECT = "#ff6600"

GRID = 2
HANDLE = 5


class GuiCreatorApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("HAS GUI Creator")
        self.minsize(1000, 640)

        self.manager = MetadataManager()
        self.selected: Optional[Control] = None
        self.project_path: Optional[Path] = None
        self.zoom = 2
        self.pad = 20

        self._drag_mode: Optional[str] = None
        self._drag_origin = (0, 0)
        self._drag_start = (0, 0, 0, 0)
        self._suspend_sync = False

        self._build_menu()
        self._build_layout()
        self._seed_example()
        self._refresh_all()

    # ------------------------------------------------------------------
    # construction
    # ------------------------------------------------------------------
    def _build_menu(self) -> None:
        bar = tk.Menu(self)

        file_menu = tk.Menu(bar, tearoff=0)
        file_menu.add_command(label="New", accelerator="Ctrl+N", command=self.new_project)
        file_menu.add_command(label="Open .hasmeta...", accelerator="Ctrl+O", command=self.open_project)
        file_menu.add_separator()
        file_menu.add_command(label="Save .hasmeta", accelerator="Ctrl+S", command=self.save_project)
        file_menu.add_command(label="Save .hasmeta As...", command=self.save_project_as)
        file_menu.add_separator()
        file_menu.add_command(label="Export .has skeleton...", accelerator="Ctrl+E", command=self.export_has)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.destroy)
        bar.add_cascade(label="File", menu=file_menu)

        edit_menu = tk.Menu(bar, tearoff=0)
        edit_menu.add_command(label="Delete control", accelerator="Del", command=self.delete_selected)
        edit_menu.add_command(label="Raise (later in TAB order)", command=lambda: self.reorder(+1))
        edit_menu.add_command(label="Lower (earlier in TAB order)", command=lambda: self.reorder(-1))
        edit_menu.add_separator()
        edit_menu.add_command(label="Validate layout", command=self.show_validation)
        bar.add_cascade(label="Edit", menu=edit_menu)

        view_menu = tk.Menu(bar, tearoff=0)
        for factor in (1, 2, 3):
            view_menu.add_command(label=f"Zoom {factor}x", command=lambda f=factor: self.set_zoom(f))
        bar.add_cascade(label="View", menu=view_menu)

        help_menu = tk.Menu(bar, tearoff=0)
        help_menu.add_command(label="About", command=self._about)
        bar.add_cascade(label="Help", menu=help_menu)

        self.config(menu=bar)
        self.bind("<Control-n>", lambda e: self.new_project())
        self.bind("<Control-o>", lambda e: self.open_project())
        self.bind("<Control-s>", lambda e: self.save_project())
        self.bind("<Control-e>", lambda e: self.export_has())
        self.bind("<Delete>", lambda e: self.delete_selected())
        for key, dx, dy in (("Left", -GRID, 0), ("Right", GRID, 0), ("Up", 0, -GRID), ("Down", 0, GRID)):
            self.bind(f"<{key}>", lambda e, dx=dx, dy=dy: self.nudge(dx, dy))

    def _build_layout(self) -> None:
        root = ttk.Frame(self, padding=6)
        root.pack(fill="both", expand=True)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        self._build_left_panel(root)

        centre = ttk.Frame(root)
        centre.grid(row=0, column=1, sticky="nsew", padx=6)
        centre.rowconfigure(0, weight=1)
        centre.columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(centre, background=PEN_DESK, highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)

        self._build_right_panel(root)

        self.status = tk.StringVar(value="Ready.")
        ttk.Label(root, textvariable=self.status, relief="sunken", anchor="w").grid(
            row=1, column=0, columnspan=3, sticky="ew", pady=(6, 0)
        )

    def _build_left_panel(self, root: ttk.Frame) -> None:
        panel = ttk.Frame(root, width=220)
        panel.grid(row=0, column=0, sticky="ns")

        box = ttk.LabelFrame(panel, text="Toolbox", padding=6)
        box.pack(fill="x")
        for kind, label in (
            (ControlType.BUTTON, "Add Button"),
            (ControlType.EDITBOX, "Add EditBox"),
            (ControlType.LABEL, "Add Label"),
            (ControlType.CHECKBOX, "Add CheckBox"),
            (ControlType.LIST, "Add List"),
            (ControlType.BITMAP, "Add Bitmap"),
        ):
            ttk.Button(box, text=label, command=lambda k=kind: self.add_control(k)).pack(
                fill="x", pady=2
            )

        win_box = ttk.LabelFrame(panel, text="Window", padding=6)
        win_box.pack(fill="x", pady=(10, 0))
        self.win_vars = {
            "caption": tk.StringVar(),
            "width": tk.StringVar(),
            "height": tk.StringVar(),
            "left": tk.StringVar(),
            "top": tk.StringVar(),
        }
        for row, (key, label) in enumerate(
            [
                ("caption", "Caption"),
                ("width", "Width"),
                ("height", "Height"),
                ("left", "Screen X"),
                ("top", "Screen Y"),
            ]
        ):
            ttk.Label(win_box, text=label).grid(row=row, column=0, sticky="w", pady=1)
            entry = ttk.Entry(win_box, textvariable=self.win_vars[key], width=16)
            entry.grid(row=row, column=1, sticky="ew", pady=1)
            entry.bind("<Return>", lambda e: self._apply_window())
            entry.bind("<FocusOut>", lambda e: self._apply_window())
        win_box.columnconfigure(1, weight=1)

        self.flag_vars = {
            "dragbar": tk.BooleanVar(),
            "depth_gadget": tk.BooleanVar(),
            "close_gadget": tk.BooleanVar(),
            "activate": tk.BooleanVar(),
            "sizeable": tk.BooleanVar(),
        }
        flag_box = ttk.LabelFrame(panel, text="Window flags (WFLG_*)", padding=6)
        flag_box.pack(fill="x", pady=(10, 0))
        for key, label in (
            ("dragbar", "DRAGBAR"),
            ("depth_gadget", "DEPTHGADGET"),
            ("close_gadget", "CLOSEGADGET"),
            ("activate", "ACTIVATE"),
            ("sizeable", "SIZEGADGET (resizable)"),
        ):
            ttk.Checkbutton(
                flag_box, text=label, variable=self.flag_vars[key], command=self._apply_window
            ).pack(anchor="w")
        ttk.Label(
            flag_box,
            text="SMART_REFRESH is flag value 0\nand is always in effect.",
            foreground="#444444",
        ).pack(anchor="w", pady=(4, 0))

        order_box = ttk.LabelFrame(panel, text="TAB order", padding=6)
        order_box.pack(fill="both", expand=True, pady=(10, 0))
        self.listbox = tk.Listbox(order_box, height=10, exportselection=False)
        self.listbox.pack(fill="both", expand=True)
        self.listbox.bind("<<ListboxSelect>>", self._on_list_select)

    def _build_right_panel(self, root: ttk.Frame) -> None:
        panel = ttk.Frame(root, width=250)
        panel.grid(row=0, column=2, sticky="ns")

        self.prop_box = ttk.LabelFrame(panel, text="Properties", padding=6)
        self.prop_box.pack(fill="x")
        self.prop_vars = {
            k: tk.StringVar()
            for k in (
                "name", "caption", "x", "y", "w", "h", "maxlen",
                "items", "selected", "asset", "bitmap_colors",
            )
        }
        self.prop_rows = {}
        for row, (key, label) in enumerate(
            [
                ("name", "Name (symbol)"),
                ("caption", "Text / Caption"),
                ("x", "X"),
                ("y", "Y"),
                ("w", "Width"),
                ("h", "Height"),
                ("maxlen", "MaxLen (+NUL)"),
                ("items", "List items (|)"),
                ("selected", "Selected row"),
                ("asset", "PNG/BMP asset"),
                ("bitmap_colors", "Bitmap colors"),
            ]
        ):
            lbl = ttk.Label(self.prop_box, text=label)
            lbl.grid(row=row, column=0, sticky="w", pady=1)
            if key == "bitmap_colors":
                entry = ttk.Combobox(
                    self.prop_box,
                    textvariable=self.prop_vars[key],
                    values=[str(value) for value in BITMAP_COLOR_DEPTHS],
                    width=16,
                    state="readonly",
                )
                entry.bind("<<ComboboxSelected>>", lambda e: self._apply_props())
            else:
                entry = ttk.Entry(self.prop_box, textvariable=self.prop_vars[key], width=18)
            entry.grid(row=row, column=1, sticky="ew", pady=1)
            entry.bind("<Return>", lambda e: self._apply_props())
            entry.bind("<FocusOut>", lambda e: self._apply_props())
            self.prop_rows[key] = (lbl, entry)
        self.prop_box.columnconfigure(1, weight=1)

        self.info = tk.StringVar()
        ttk.Label(panel, textvariable=self.info, foreground="#333333", justify="left").pack(
            anchor="w", pady=(8, 0)
        )

        val_box = ttk.LabelFrame(panel, text="Validation", padding=6)
        val_box.pack(fill="both", expand=True, pady=(10, 0))
        self.val_text = tk.Text(val_box, height=12, width=32, wrap="word", state="disabled")
        self.val_text.pack(fill="both", expand=True)

    def _seed_example(self) -> None:
        """Start with a small, valid form so the canvas is never blank."""
        m = self.manager
        m.window.caption = "Login"
        m.window.width = 320
        m.window.height = 120
        m.add(ControlType.LABEL, 12, 24, caption="Name:", name="lbl_name")
        m.add(ControlType.EDITBOX, 92, 22, 200, 14, name="edit_name", maxlen=32)
        m.add(ControlType.BUTTON, 116, 64, 88, 18, caption="OK", name="btn_ok")

    # ------------------------------------------------------------------
    # canvas rendering
    # ------------------------------------------------------------------
    def _sx(self, v: int) -> int:
        return self.pad + v * self.zoom

    def _sy(self, v: int) -> int:
        return self.pad + v * self.zoom

    def _redraw(self) -> None:
        c = self.canvas
        c.delete("all")
        self.pad = 20
        win = self.manager.window
        z = self.zoom
        w, h = win.width * z, win.height * z

        c.configure(scrollregion=(0, 0, w + 2 * self.pad, h + 2 * self.pad))

        # Outer window frame.
        c.create_rectangle(self.pad, self.pad, self.pad + w, self.pad + h, fill=PEN_GREY, outline=PEN_BLACK)
        # Title bar.
        bar_h = BORDER_TOP * z
        c.create_rectangle(self.pad, self.pad, self.pad + w, self.pad + bar_h, fill=PEN_BLUE, outline=PEN_BLACK)
        if win.close_gadget:
            c.create_rectangle(
                self.pad + 1, self.pad + 1, self.pad + bar_h + 6 * z, self.pad + bar_h, fill=PEN_GREY, outline=PEN_BLACK
            )
        if win.depth_gadget:
            c.create_rectangle(
                self.pad + w - bar_h - 6 * z, self.pad + 1, self.pad + w - 1, self.pad + bar_h,
                fill=PEN_GREY, outline=PEN_BLACK,
            )
        c.create_text(
            self.pad + bar_h + 12 * z, self.pad + bar_h // 2,
            text=win.caption, anchor="w", fill=PEN_WHITE, font=self._font(),
        )

        # Client area boundary (the region controls may occupy).
        c.create_rectangle(
            self._sx(win.client_left), self._sy(win.client_top),
            self._sx(win.client_right), self._sy(win.client_bottom),
            outline="#787878", dash=(2, 2),
        )

        for control in self.manager.controls:
            self._draw_control(control)

        if self.selected is not None:
            self._draw_selection(self.selected)

    def _font(self):
        return ("Courier New", max(6, int(6 * self.zoom)))

    def _draw_control(self, ctl: Control) -> None:
        c = self.canvas
        z = self.zoom
        x0, y0 = self._sx(ctl.x), self._sy(ctl.y)
        x1, y1 = self._sx(ctl.right), self._sy(ctl.bottom)

        if ctl.kind is ControlType.BUTTON:
            c.create_rectangle(x0, y0, x1, y1, fill=PEN_GREY, outline=PEN_BLACK)
            c.create_line(x0, y1, x0, y0, x1, y0, fill=PEN_WHITE)  # raised highlight
            c.create_line(x1, y0, x1, y1, x0, y1, fill="#606060")
            c.create_text(
                (x0 + x1) // 2, (y0 + y1) // 2, text=ctl.caption,
                fill=PEN_BLACK, font=self._font(),
            )
        elif ctl.kind is ControlType.EDITBOX:
            c.create_rectangle(x0, y0, x1, y1, fill=PEN_WHITE, outline=PEN_BLACK)
            c.create_line(x0, y1, x0, y0, x1, y0, fill="#606060")  # recessed
            c.create_text(
                x0 + 3 * z, (y0 + y1) // 2, text=ctl.caption or "",
                anchor="w", fill=PEN_BLACK, font=self._font(),
            )
            # Text cursor at the insertion point.
            c.create_rectangle(
                x0 + 2 * z, y0 + 2 * z, x0 + 2 * z + CHAR_W * z // 2, y1 - 2 * z,
                fill=PEN_BLUE, outline="",
            )
        elif ctl.kind is ControlType.CHECKBOX:
            box = min((y1 - y0) - 2 * z, 12 * z)
            c.create_rectangle(x0, y0, x0 + box, y0 + box, fill=PEN_WHITE, outline=PEN_BLACK)
            if ctl.checked:
                c.create_line(x0 + 2 * z, y0 + box // 2, x0 + box // 2, y0 + box - 2 * z, x0 + box - 2 * z, y0 + 2 * z, fill=PEN_BLACK, width=max(1, z))
            c.create_text(x0 + box + 3 * z, (y0 + y1) // 2, text=ctl.caption, anchor="w", fill=PEN_BLACK, font=self._font())
        elif ctl.kind is ControlType.LIST:
            c.create_rectangle(x0, y0, x1, y1, fill=PEN_WHITE, outline=PEN_BLACK)
            for index, item in enumerate(ctl.items):
                row_y = y0 + (2 + index * CHAR_H) * z
                if row_y + CHAR_H * z > y1:
                    break
                if index == ctl.selected:
                    c.create_rectangle(x0 + z, row_y, x1 - z, row_y + CHAR_H * z, fill=PEN_BLUE, outline="")
                    colour = PEN_WHITE
                else:
                    colour = PEN_BLACK
                c.create_text(x0 + 3 * z, row_y + CHAR_H * z // 2, text=item, anchor="w", fill=colour, font=self._font())
        elif ctl.kind is ControlType.BITMAP:
            c.create_rectangle(x0, y0, x1, y1, fill=PEN_WHITE, outline=PEN_BLACK)
            c.create_text((x0 + x1) // 2, (y0 + y1) // 2, text="BMP", fill=PEN_BLACK, font=self._font())
        else:
            c.create_text(
                x0, (y0 + y1) // 2, text=ctl.caption, anchor="w",
                fill=PEN_BLACK, font=self._font(),
            )

    def _draw_selection(self, ctl: Control) -> None:
        c = self.canvas
        x0, y0 = self._sx(ctl.x), self._sy(ctl.y)
        x1, y1 = self._sx(ctl.right), self._sy(ctl.bottom)
        c.create_rectangle(x0 - 1, y0 - 1, x1 + 1, y1 + 1, outline=PEN_SELECT, dash=(3, 2))
        c.create_rectangle(
            x1 - HANDLE, y1 - HANDLE, x1 + HANDLE, y1 + HANDLE,
            fill=PEN_SELECT, outline=PEN_BLACK, tags="resize_handle",
        )

    # ------------------------------------------------------------------
    # mouse interaction
    # ------------------------------------------------------------------
    def _canvas_to_model(self, ex: int, ey: int) -> tuple:
        return ((ex - self.pad) // self.zoom, (ey - self.pad) // self.zoom)

    def _hit(self, mx: int, my: int) -> Optional[Control]:
        for ctl in reversed(self.manager.controls):
            if ctl.x <= mx < ctl.right and ctl.y <= my < ctl.bottom:
                return ctl
        return None

    def _on_press(self, event) -> None:
        self.canvas.focus_set()
        if self.selected is not None:
            x1, y1 = self._sx(self.selected.right), self._sy(self.selected.bottom)
            if abs(event.x - x1) <= HANDLE and abs(event.y - y1) <= HANDLE:
                self._drag_mode = "resize"
                self._drag_origin = (event.x, event.y)
                s = self.selected
                self._drag_start = (s.x, s.y, s.w, s.h)
                return

        mx, my = self._canvas_to_model(event.x, event.y)
        hit = self._hit(mx, my)
        self.selected = hit
        if hit is not None:
            self._drag_mode = "move"
            self._drag_origin = (event.x, event.y)
            self._drag_start = (hit.x, hit.y, hit.w, hit.h)
        self._refresh_all()

    def _on_drag(self, event) -> None:
        if self._drag_mode is None or self.selected is None:
            return
        dx = (event.x - self._drag_origin[0]) // self.zoom
        dy = (event.y - self._drag_origin[1]) // self.zoom
        ox, oy, ow, oh = self._drag_start
        s = self.selected
        if self._drag_mode == "move":
            s.x = _snap(ox + dx)
            s.y = _snap(oy + dy)
        else:
            s.w = max(CHAR_W, _snap(ow + dx))
            s.h = max(CHAR_H, _snap(oh + dy))
        self._redraw()
        self._sync_props()
        self.status.set(f"{s.name}: x={s.x} y={s.y} w={s.w} h={s.h}")

    def _on_release(self, event) -> None:
        if self._drag_mode is not None:
            self._drag_mode = None
            self._refresh_all()

    # ------------------------------------------------------------------
    # commands
    # ------------------------------------------------------------------
    def add_control(self, kind: ControlType) -> None:
        win = self.manager.window
        x, y = win.client_left + 8, win.client_top + 8
        # Drop new widgets below whatever is already placed.
        if self.manager.controls:
            y = min(win.client_bottom - 20, max(c.bottom for c in self.manager.controls) + 6)
        ctl = self.manager.add(kind, x, y)
        if kind is ControlType.LIST:
            ctl.items = ["Item 1", "Item 2", "Item 3"]
        if kind is ControlType.BITMAP:
            path = filedialog.askopenfilename(title="Select bitmap", filetypes=[("Image", "*.png *.bmp"), ("All files", "*.*")])
            if not path:
                self.manager.remove(ctl)
                self._refresh_all()
                return
            ctl.asset_path = path
        self.selected = ctl
        self.status.set(f"Added {kind.value} '{ctl.name}' with ActionID {ctl.action_id}.")
        self._refresh_all()

    def delete_selected(self) -> None:
        if self.selected is None:
            return
        name = self.selected.name
        self.manager.remove(self.selected)
        self.selected = None
        self.status.set(f"Deleted '{name}'. ActionIDs are not recycled.")
        self._refresh_all()

    def reorder(self, delta: int) -> None:
        if self.selected is None:
            return
        idx = self.manager.controls.index(self.selected)
        self.manager.move(self.selected, idx + delta)
        self._refresh_all()

    def nudge(self, dx: int, dy: int) -> None:
        if self.selected is None or isinstance(self.focus_get(), (ttk.Entry, tk.Entry)):
            return
        self.selected.x += dx
        self.selected.y += dy
        self._refresh_all()

    def set_zoom(self, factor: int) -> None:
        self.zoom = factor
        self._redraw()

    def new_project(self) -> None:
        self.manager = MetadataManager()
        self.selected = None
        self.project_path = None
        self.status.set("New project.")
        self._refresh_all()

    def open_project(self) -> None:
        path = filedialog.askopenfilename(
            title="Open layout metadata",
            filetypes=[("HAS GUI metadata", "*.hasmeta"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            self.manager = hasmeta.load(Path(path))
        except Exception as exc:  # surfaced to the user, not swallowed
            messagebox.showerror("Open failed", str(exc))
            return
        self.selected = None
        self.project_path = Path(path)
        self.status.set(f"Loaded {path}")
        self._refresh_all()

    def save_project(self) -> None:
        if self.project_path is None:
            self.save_project_as()
            return
        hasmeta.save(self.manager, self.project_path)
        self.status.set(f"Saved {self.project_path}")

    def save_project_as(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save layout metadata",
            defaultextension=".hasmeta",
            filetypes=[("HAS GUI metadata", "*.hasmeta")],
        )
        if not path:
            return
        self.project_path = Path(path)
        self.save_project()

    def export_has(self) -> None:
        problems = self.manager.validate()
        if problems:
            if not messagebox.askyesno(
                "Layout problems",
                "The layout has %d problem(s):\n\n%s\n\nExport anyway?"
                % (len(problems), "\n".join("- " + p for p in problems[:8])),
            ):
                return
        path = filedialog.asksaveasfilename(
            title="Export HAS skeleton",
            defaultextension=".has",
            initialfile=(self.project_path.stem if self.project_path else "gui_form") + ".has",
            filetypes=[("HAS source", "*.has")],
        )
        if not path:
            return
        source = str(self.project_path) if self.project_path else "<unsaved layout>"
        try:
            has_export.save(self.manager, Path(path), meta_source=source)
        except (OSError, RuntimeError, ValueError) as exc:
            messagebox.showerror("Export failed", str(exc))
            return
        self.status.set(f"Exported {path} (existing USER CODE blocks preserved).")

    def show_validation(self) -> None:
        problems = self.manager.validate()
        if problems:
            messagebox.showwarning("Validation", "\n".join("- " + p for p in problems))
        else:
            messagebox.showinfo("Validation", "Layout is valid.")

    def _about(self) -> None:
        messagebox.showinfo(
            "HAS GUI Creator",
            "WYSIWYG designer that emits .hasmeta layout metadata and a\n"
            "compilable .has skeleton targeting intuition.library.\n\n"
            "Runtime contract: docs/GUI_INTUITION_RUNTIME_SPEC.md",
        )

    # ------------------------------------------------------------------
    # panel synchronisation
    # ------------------------------------------------------------------
    def _refresh_all(self) -> None:
        self._sync_window()
        self._sync_props()
        self._sync_list()
        self._sync_validation()
        self._redraw()

    def _sync_window(self) -> None:
        self._suspend_sync = True
        win = self.manager.window
        self.win_vars["caption"].set(win.caption)
        self.win_vars["width"].set(str(win.width))
        self.win_vars["height"].set(str(win.height))
        self.win_vars["left"].set(str(win.left))
        self.win_vars["top"].set(str(win.top))
        for key, var in self.flag_vars.items():
            var.set(getattr(win, key))
        self._suspend_sync = False

    def _apply_window(self) -> None:
        if self._suspend_sync:
            return
        win = self.manager.window
        win.caption = self.win_vars["caption"].get()
        win.width = _int_or(self.win_vars["width"].get(), win.width)
        win.height = _int_or(self.win_vars["height"].get(), win.height)
        win.left = _int_or(self.win_vars["left"].get(), win.left)
        win.top = _int_or(self.win_vars["top"].get(), win.top)
        for key, var in self.flag_vars.items():
            setattr(win, key, bool(var.get()))
        self._refresh_all()

    def _sync_props(self) -> None:
        self._suspend_sync = True
        s = self.selected
        if s is None:
            for var in self.prop_vars.values():
                var.set("")
            self.info.set("No control selected.")
        else:
            self.prop_vars["name"].set(s.name)
            self.prop_vars["caption"].set(s.caption)
            self.prop_vars["x"].set(str(s.x))
            self.prop_vars["y"].set(str(s.y))
            self.prop_vars["w"].set(str(s.w))
            self.prop_vars["h"].set(str(s.h))
            self.prop_vars["maxlen"].set(str(s.maxlen))
            self.prop_vars["items"].set("|".join(s.items))
            self.prop_vars["selected"].set(str(s.selected))
            self.prop_vars["asset"].set(s.asset_path)
            self.prop_vars["bitmap_colors"].set(str(s.bitmap_colors))
            self.info.set(
                f"{s.kind.value}  ActionID={s.action_id}\n"
                f"const {s.id_const} = {s.action_id};\n"
                + (
                    f"buffers: {s.buffer_symbol}, {s.undo_symbol}"
                    if s.kind is ControlType.EDITBOX
                    else f"string: {s.text_symbol}"
                )
            )
        state = "normal" if (s is not None and s.kind is ControlType.EDITBOX) else "disabled"
        for widget in self.prop_rows["maxlen"]:
            widget.configure(state=state)
        for key, allowed in (
            ("items", ControlType.LIST),
            ("selected", ControlType.LIST),
            ("asset", ControlType.BITMAP),
            ("bitmap_colors", ControlType.BITMAP),
        ):
            enabled = s is not None and s.kind is allowed
            label, widget = self.prop_rows[key]
            label.configure(state="normal" if enabled else "disabled")
            if key == "bitmap_colors" and enabled:
                widget_state = "readonly"
            else:
                widget_state = "normal" if enabled else "disabled"
            widget.configure(state=widget_state)
        self._suspend_sync = False

    def _apply_props(self) -> None:
        if self._suspend_sync or self.selected is None:
            return
        s = self.selected
        name = self.prop_vars["name"].get().strip()
        if name:
            s.name = name
        s.caption = self.prop_vars["caption"].get()
        s.x = _int_or(self.prop_vars["x"].get(), s.x)
        s.y = _int_or(self.prop_vars["y"].get(), s.y)
        s.w = max(1, _int_or(self.prop_vars["w"].get(), s.w))
        s.h = max(1, _int_or(self.prop_vars["h"].get(), s.h))
        s.maxlen = max(2, _int_or(self.prop_vars["maxlen"].get(), s.maxlen))
        s.items = [item.strip() for item in self.prop_vars["items"].get().split("|") if item.strip()]
        s.selected = max(0, _int_or(self.prop_vars["selected"].get(), s.selected))
        s.asset_path = self.prop_vars["asset"].get().strip()
        bitmap_colors = _int_or(self.prop_vars["bitmap_colors"].get(), s.bitmap_colors)
        if bitmap_colors in BITMAP_COLOR_DEPTHS:
            s.bitmap_colors = bitmap_colors
        self._refresh_all()

    def _sync_list(self) -> None:
        self.listbox.delete(0, tk.END)
        for ctl in self.manager.controls:
            self.listbox.insert(
                tk.END, f"{ctl.action_id:>3}  {ctl.kind.value[:4]:<4} {ctl.name}"
            )
        if self.selected in self.manager.controls:
            idx = self.manager.controls.index(self.selected)
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(idx)

    def _on_list_select(self, event) -> None:
        sel = self.listbox.curselection()
        if not sel:
            return
        self.selected = self.manager.controls[sel[0]]
        self._sync_props()
        self._redraw()

    def _sync_validation(self) -> None:
        problems: List[str] = self.manager.validate()
        self.val_text.configure(state="normal")
        self.val_text.delete("1.0", tk.END)
        self.val_text.insert(
            tk.END, "OK - layout is valid.\n" if not problems else "\n".join("- " + p for p in problems)
        )
        self.val_text.configure(state="disabled")


def _snap(value: int) -> int:
    return int(round(value / GRID) * GRID)


def _int_or(text: str, fallback: int) -> int:
    try:
        return int(str(text).strip())
    except (TypeError, ValueError):
        return fallback


def main() -> int:
    GuiCreatorApp().mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
