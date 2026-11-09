#!/usr/bin/env python3
"""SDF2Map Studio: a desktop GUI for the ROS 2 Jazzy sdf2map CLI.

Uses only the Python standard library (Tkinter). Run from a desktop terminal
with ROS 2 and the sdf2map workspace available, e.g.:
    cd /jazzy_ws && source install/setup.bash && python3 /path/to/sdf2map_studio.py
"""
from __future__ import annotations

import json
import os
import queue
import shlex
import shutil
import subprocess
import threading
import uuid
from pathlib import Path
from tkinter import (
    BOTH, END, LEFT, RIGHT, X, Y, BooleanVar, StringVar, IntVar,
    Tk, Toplevel, Canvas, Text, filedialog, messagebox, simpledialog,
)
from tkinter import ttk

APP_NAME = "SDF2Map Studio"
VERSION = "1.0.1"
CONFIG_DIR = Path.home() / ".config" / "sdf2map-studio"
PRESETS_FILE = CONFIG_DIR / "presets.json"

BG = "#0B1220"
PANEL = "#111C2E"
PANEL_2 = "#162338"
BORDER = "#25344C"
TEXT = "#E8EEF8"
MUTED = "#8FA2BD"
ACCENT = "#38BDF8"
ACCENT_DARK = "#0C4A6E"
GREEN = "#34D399"
RED = "#FB7185"
AMBER = "#FBBF24"

OUTPUT_MODES = ["3D point cloud", "2D occupancy grid", "Both"]

# Presets only replace conversion settings, not source/output paths.
BUILTIN_PRESETS = {
    "Balanced · Both outputs": {
        "output_mode": "Both", "density": "400", "geometry": "collision",
        "voxel": "0.05", "z_min_enabled": False, "z_min": "0.0",
        "z_max_enabled": False, "z_max": "2.5", "transparency": "0.95",
        "exclude_ground": False, "ascii": False, "seed": "42",
        "no_download": False, "publish": False, "verbose": True,
        "exclude_regex": "", "grid_resolution": "0.05",
        "slice_z_min": "0.1", "slice_z_max": "1.8", "grid_bounds": "slice",
        "grid_margin": "2.0", "grid_close": "1",
    },
    "Nav2 · Compact 5 cm": {
        "output_mode": "2D occupancy grid", "density": "400", "geometry": "collision",
        "voxel": "0.05", "z_min_enabled": False, "z_min": "0.0",
        "z_max_enabled": False, "z_max": "2.5", "transparency": "0.95",
        "exclude_ground": False, "ascii": False, "seed": "42",
        "no_download": False, "publish": False, "verbose": False,
        "exclude_regex": "", "grid_resolution": "0.05",
        "slice_z_min": "0.1", "slice_z_max": "1.8", "grid_bounds": "slice",
        "grid_margin": "2.0", "grid_close": "1",
    },
    "3D · High detail": {
        "output_mode": "3D point cloud", "density": "800", "geometry": "collision",
        "voxel": "0.02", "z_min_enabled": False, "z_min": "0.0",
        "z_max_enabled": False, "z_max": "2.5", "transparency": "0.95",
        "exclude_ground": False, "ascii": False, "seed": "42",
        "no_download": False, "publish": False, "verbose": True,
        "exclude_regex": "", "grid_resolution": "0.05",
        "slice_z_min": "0.1", "slice_z_max": "1.8", "grid_bounds": "slice",
        "grid_margin": "1.0", "grid_close": "1",
    },
    "Quick · 2D preview": {
        "output_mode": "2D occupancy grid", "density": "200", "geometry": "collision",
        "voxel": "0.0", "z_min_enabled": False, "z_min": "0.0",
        "z_max_enabled": False, "z_max": "2.5", "transparency": "0.95",
        "exclude_ground": False, "ascii": False, "seed": "42",
        "no_download": False, "publish": False, "verbose": False,
        "exclude_regex": "", "grid_resolution": "0.10",
        "slice_z_min": "0.1", "slice_z_max": "1.8", "grid_bounds": "slice",
        "grid_margin": "1.0", "grid_close": "0",
    },
    "Visual geometry · audit": {
        "output_mode": "Both", "density": "400", "geometry": "visual",
        "voxel": "0.05", "z_min_enabled": False, "z_min": "0.0",
        "z_max_enabled": True, "z_max": "8.0", "transparency": "0.95",
        "exclude_ground": False, "ascii": False, "seed": "42",
        "no_download": False, "publish": False, "verbose": True,
        "exclude_regex": "Person|MaleVisitor|Casual", "grid_resolution": "0.05",
        "slice_z_min": "0.1", "slice_z_max": "1.8", "grid_bounds": "slice",
        "grid_margin": "2.0", "grid_close": "1",
    },
}


def first_existing(paths: list[Path]) -> str:
    for p in paths:
        if p.exists():
            return str(p)
    return ""


def default_workspace_setup() -> str:
    candidates = [
        Path.cwd() / "install" / "setup.bash",
        Path("/jazzy_ws/install/setup.bash"),
        Path.home() / "jazzy_ws" / "install" / "setup.bash",
        Path.home() / "robot_ws" / "install" / "setup.bash",
    ]
    return first_existing(candidates)


def default_world() -> str:
    candidates = [
        Path("/jazzy_ws/src/robot_description/worlds/small_city.world"),
        Path.home() / "jazzy_ws/src/robot_description/worlds/small_city.world",
        Path.cwd() / "src/robot_description/worlds/small_city.world",
    ]
    return first_existing(candidates)


def default_model_path() -> str:
    candidates = [
        Path("/jazzy_ws/src/robot_description/models"),
        Path.home() / "jazzy_ws/src/robot_description/models",
        Path.cwd() / "src/robot_description/models",
    ]
    return first_existing(candidates)


class ToolTip:
    """Small hover tooltip for parameter explanations."""
    def __init__(self, widget, text: str):
        self.widget = widget
        self.text = text
        self.window = None
        widget.bind("<Enter>", self.show, add="+")
        widget.bind("<Leave>", self.hide, add="+")

    def show(self, _event=None):
        if self.window or not self.text:
            return
        try:
            x = self.widget.winfo_rootx() + 18
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
            self.window = Toplevel(self.widget)
            self.window.wm_overrideredirect(True)
            self.window.wm_geometry(f"+{x}+{y}")
            label = ttk.Label(self.window, text=self.text, style="Tooltip.TLabel", wraplength=330,
                              justify="left", padding=(10, 7))
            label.pack()
        except Exception:
            self.window = None

    def hide(self, _event=None):
        if self.window:
            self.window.destroy()
            self.window = None


class ScrollableFrame(ttk.Frame):
    def __init__(self, parent, bg=PANEL):
        super().__init__(parent, style="Panel.TFrame")
        self.canvas = Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas, style="Panel.TFrame")
        self.window_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side=LEFT, fill=BOTH, expand=True)
        self.scrollbar.pack(side=RIGHT, fill=Y)
        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel, add="+")
        self.canvas.bind_all("<Button-4>", self._on_linux_wheel, add="+")
        self.canvas.bind_all("<Button-5>", self._on_linux_wheel, add="+")

    def _on_inner_configure(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfigure(self.window_id, width=event.width)

    def _pointer_is_inside(self, event):
        widget = self.winfo_containing(event.x_root, event.y_root)
        while widget is not None:
            if widget == self:
                return True
            widget = getattr(widget, "master", None)
        return False

    def _on_mousewheel(self, event):
        if self._pointer_is_inside(event):
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_linux_wheel(self, event):
        if self._pointer_is_inside(event):
            self.canvas.yview_scroll(-1 if event.num == 4 else 1, "units")


class SDF2MapStudio:
    def __init__(self, root: Tk):
        self.root = root
        self.root.title(f"{APP_NAME} · v{VERSION}")
        self.root.geometry("1320x900")
        self.root.minsize(1080, 740)
        self.root.configure(bg=BG)

        self.process: subprocess.Popen | None = None
        self.worker: threading.Thread | None = None
        self.events: queue.Queue = queue.Queue()
        self.running = False
        self.active_temp_pcd: Path | None = None
        self.preview_temp_pcd: Path | None = None
        self._preview_after_id = None
        self._log_line_count = 0
        self._field_widgets: dict[str, list] = {}

        self.vars = {
            "input": StringVar(value=default_world()),
            "model_paths": StringVar(value=default_model_path()),
            "output_dir": StringVar(value=str(Path.cwd() / "generated_maps")),
            "pcd_name": StringVar(value="small_city.pcd"),
            "yaml_name": StringVar(value="small_city.yaml"),
            "output_mode": StringVar(value="Both"),
            "ros_setup": StringVar(value=first_existing([Path("/opt/ros/jazzy/setup.bash")])),
            "workspace_setup": StringVar(value=default_workspace_setup()),
            "density": StringVar(value="400"),
            "geometry": StringVar(value="collision"),
            "voxel": StringVar(value="0.05"),
            "z_min_enabled": BooleanVar(value=False),
            "z_min": StringVar(value="0.0"),
            "z_max_enabled": BooleanVar(value=False),
            "z_max": StringVar(value="2.5"),
            "transparency": StringVar(value="0.95"),
            "exclude_ground": BooleanVar(value=False),
            "ascii": BooleanVar(value=False),
            "seed": StringVar(value="42"),
            "no_download": BooleanVar(value=False),
            "publish": BooleanVar(value=False),
            "verbose": BooleanVar(value=True),
            "exclude_regex": StringVar(value=""),
            "grid_resolution": StringVar(value="0.05"),
            "slice_z_min": StringVar(value="0.1"),
            "slice_z_max": StringVar(value="1.8"),
            "grid_bounds": StringVar(value="slice"),
            "grid_margin": StringVar(value="2.0"),
            "grid_close": StringVar(value="1"),
        }
        self.preset_var = StringVar(value="Balanced · Both outputs")
        self.status_var = StringVar(value="Ready · Configure your map and run conversion")
        self.status_dot = StringVar(value="●")
        self.mode_hint = StringVar(value="Creates a PCD point cloud and a Nav2 PGM/YAML map.")
        self.preset_names: list[str] = []

        self._configure_styles()
        self._build_ui()
        self._load_preset_names()
        self._connect_traces()
        self.update_preview()
        self.update_mode_state()
        self.root.after(100, self._poll_events)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _configure_styles(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("Card.TFrame", background=PANEL, borderwidth=1, relief="solid")
        style.configure("TLabel", background=BG, foreground=TEXT, font=("DejaVu Sans", 10))
        style.configure("Panel.TLabel", background=PANEL, foreground=TEXT, font=("DejaVu Sans", 10))
        style.configure("Muted.TLabel", background=PANEL, foreground=MUTED, font=("DejaVu Sans", 8))
        style.configure("Title.TLabel", background=BG, foreground=TEXT, font=("DejaVu Sans", 19, "bold"))
        style.configure("Subtitle.TLabel", background=BG, foreground=MUTED, font=("DejaVu Sans", 9))
        style.configure("Section.TLabel", background=PANEL, foreground=TEXT, font=("DejaVu Sans", 11, "bold"))
        style.configure("SmallHeading.TLabel", background=PANEL, foreground=ACCENT, font=("DejaVu Sans", 8, "bold"))
        style.configure("Tooltip.TLabel", background="#1D2C43", foreground=TEXT, font=("DejaVu Sans", 9),
                        borderwidth=1, relief="solid")
        style.configure("TEntry", fieldbackground="#0D1727", foreground=TEXT, insertcolor=TEXT,
                        bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER, padding=7)
        style.map("TEntry", bordercolor=[("focus", ACCENT)])
        style.configure("TCombobox", fieldbackground="#0D1727", background=PANEL_2,
                        foreground=TEXT, arrowcolor=ACCENT, bordercolor=BORDER, padding=6)
        style.map("TCombobox", fieldbackground=[("readonly", "#0D1727")],
                  foreground=[("readonly", TEXT)], selectbackground=[("readonly", ACCENT_DARK)])
        style.configure("TSpinbox", fieldbackground="#0D1727", foreground=TEXT, insertcolor=TEXT,
                        bordercolor=BORDER, padding=6)
        style.configure("TCheckbutton", background=PANEL, foreground=TEXT, font=("DejaVu Sans", 9))
        style.map("TCheckbutton", background=[("active", PANEL)], foreground=[("disabled", "#52637C")])
        style.configure("TRadiobutton", background=PANEL, foreground=TEXT, font=("DejaVu Sans", 9))
        style.map("TRadiobutton", background=[("active", PANEL)], foreground=[("disabled", "#52637C")])
        style.configure("TNotebook", background=PANEL, borderwidth=0, tabmargins=(0, 0, 0, 0))
        style.configure("TNotebook.Tab", background="#152238", foreground=MUTED,
                        padding=(15, 10), font=("DejaVu Sans", 9, "bold"), borderwidth=0)
        style.map("TNotebook.Tab", background=[("selected", ACCENT_DARK)],
                  foreground=[("selected", "#FFFFFF")])
        style.configure("TSeparator", background=BORDER)
        style.configure("Primary.TButton", background=ACCENT, foreground="#06111D",
                        font=("DejaVu Sans", 10, "bold"), padding=(15, 10), borderwidth=0)
        style.map("Primary.TButton", background=[("active", "#7DD3FC"), ("disabled", "#34465D")],
                  foreground=[("disabled", "#74859D")])
        style.configure("Secondary.TButton", background="#22324A", foreground=TEXT,
                        font=("DejaVu Sans", 9, "bold"), padding=(10, 7), borderwidth=0)
        style.map("Secondary.TButton", background=[("active", "#314660"), ("disabled", "#1A2638")])
        style.configure("Danger.TButton", background="#4A2332", foreground="#FDA4AF")
        style.configure("TProgressbar", troughcolor="#1B2A40", background=ACCENT, bordercolor=PANEL,
                        lightcolor=ACCENT, darkcolor=ACCENT)

    def _build_ui(self):
        # Header
        header = ttk.Frame(self.root, padding=(22, 18, 22, 12))
        header.pack(fill=X)
        brand = ttk.Frame(header)
        brand.pack(side=LEFT, fill=X, expand=True)
        mark = ttk.Label(brand, text="SDF", background=ACCENT_DARK, foreground="#BAE6FD",
                         font=("DejaVu Sans", 11, "bold"), padding=(9, 7))
        mark.pack(side=LEFT, padx=(0, 12))
        titles = ttk.Frame(brand)
        titles.pack(side=LEFT, fill=X)
        ttk.Label(titles, text="SDF2MAP STUDIO", style="Title.TLabel").pack(anchor="w")
        ttk.Label(titles, text="Gazebo SDF  →  Point cloud & Nav2 maps", style="Subtitle.TLabel").pack(anchor="w", pady=(2, 0))

        preset_box = ttk.Frame(header)
        preset_box.pack(side=RIGHT, anchor="n")
        ttk.Label(preset_box, text="PRESET", style="Subtitle.TLabel").pack(anchor="w", pady=(0, 5))
        preset_row = ttk.Frame(preset_box)
        preset_row.pack(anchor="e")
        self.preset_combo = ttk.Combobox(preset_row, textvariable=self.preset_var, state="readonly", width=28)
        self.preset_combo.pack(side=LEFT, padx=(0, 6))
        self.preset_combo.bind("<<ComboboxSelected>>", self.apply_selected_preset)
        ttk.Button(preset_row, text="Save preset", style="Secondary.TButton", command=self.save_preset).pack(side=LEFT)
        ttk.Button(preset_row, text="Delete", style="Secondary.TButton", command=self.delete_preset).pack(side=LEFT, padx=(6, 0))

        separator = ttk.Separator(self.root, orient="horizontal")
        separator.pack(fill=X, padx=22, pady=(0, 12))

        main = ttk.Panedwindow(self.root, orient="horizontal")
        main.pack(fill=BOTH, expand=True, padx=22, pady=(0, 12))
        left = ttk.Frame(main, style="Panel.TFrame", padding=14)
        right = ttk.Frame(main, style="Panel.TFrame", padding=14)
        main.add(left, weight=6)
        main.add(right, weight=5)

        self._build_source_card(left)
        settings_header = ttk.Frame(left, style="Panel.TFrame")
        settings_header.pack(fill=X, pady=(15, 8))
        ttk.Label(settings_header, text="CONVERSION SETTINGS", style="Section.TLabel").pack(side=LEFT)
        ttk.Label(settings_header, text="Hover a field label for context", style="Muted.TLabel").pack(side=RIGHT)
        self.notebook = ttk.Notebook(left)
        self.notebook.pack(fill=BOTH, expand=True)
        self.tab_3d = ScrollableFrame(self.notebook)
        self.tab_2d = ScrollableFrame(self.notebook)
        self.tab_advanced = ScrollableFrame(self.notebook)
        self.notebook.add(self.tab_3d, text="3D · Sampling")
        self.notebook.add(self.tab_2d, text="2D · Occupancy grid")
        self.notebook.add(self.tab_advanced, text="Advanced · Filters")
        self._build_3d_tab(self.tab_3d.inner)
        self._build_2d_tab(self.tab_2d.inner)
        self._build_advanced_tab(self.tab_advanced.inner)

        self._build_right_panel(right)

        # Footer/status
        footer = ttk.Frame(self.root, padding=(22, 0, 22, 14))
        footer.pack(fill=X)
        ttk.Separator(footer, orient="horizontal").pack(fill=X, pady=(0, 10))
        self.status_label = ttk.Label(footer, textvariable=self.status_var, style="Subtitle.TLabel")
        self.status_label.pack(side=LEFT)
        self.progress = ttk.Progressbar(footer, mode="determinate", maximum=100, value=0, length=155)
        self.progress.pack(side=RIGHT, padx=(12, 0))

    def _card_heading(self, parent, text):
        row = ttk.Frame(parent, style="Panel.TFrame")
        row.pack(fill=X, pady=(0, 10))
        ttk.Label(row, text=text, style="Section.TLabel").pack(side=LEFT)
        return row

    def _build_source_card(self, parent):
        card = ttk.Frame(parent, style="Panel.TFrame", padding=(0, 0, 0, 0))
        card.pack(fill=X)
        self._card_heading(card, "SOURCE & OUTPUTS")

        self._path_row(card, "Input world", "input", "Choose the .sdf or .world file to convert.", self.browse_input)
        self._path_row(card, "Model search paths", "model_paths",
                       "Extra model:// directories. Add multiple folders; separate them with colons.", self.browse_model_path)
        self._path_row(card, "Output folder", "output_dir", "Folder where selected map files will be written.", self.browse_output_dir)

        self._filename_row(card, "PCD filename", "pcd_name",
                           "Final .pcd file name, used in 3D/Both modes. A .pcd extension is added if omitted.")
        self._filename_row(card, "Nav2 YAML filename", "yaml_name",
                           "YAML metadata filename. Its matching PGM image is generated beside it.")

        ttk.Label(card, text="OUTPUT TYPE", style="SmallHeading.TLabel").pack(anchor="w", pady=(9, 5))
        mode_frame = ttk.Frame(card, style="Panel.TFrame")
        mode_frame.pack(fill=X)
        self.mode_buttons = []
        for mode in OUTPUT_MODES:
            rb = ttk.Radiobutton(mode_frame, text=mode, value=mode, variable=self.vars["output_mode"],
                                 command=self.update_mode_state)
            rb.pack(side=LEFT, padx=(0, 13))
            self.mode_buttons.append(rb)
        ttk.Label(card, textvariable=self.mode_hint, style="Muted.TLabel", wraplength=620).pack(anchor="w", pady=(6, 2))

    def _filename_row(self, parent, title, key, explanation):
        self._source_row(parent, title, key, explanation)

    def _path_row(self, parent, title, key, explanation, browse_cb):
        self._source_row(parent, title, key, explanation, browse_cb=browse_cb)

    def _source_row(self, parent, title, key, explanation, browse_cb=None):
        """Compact source/output row with a full-width, responsive explanation."""
        row = ttk.Frame(parent, style="Panel.TFrame")
        row.pack(fill=X, pady=(0, 8))

        controls = ttk.Frame(row, style="Panel.TFrame")
        controls.pack(fill=X)
        lbl = ttk.Label(controls, text=title, style="Panel.TLabel", width=18)
        lbl.pack(side=LEFT, padx=(0, 12))
        ToolTip(lbl, explanation)

        entry = ttk.Entry(controls, textvariable=self.vars[key])
        entry.pack(side=LEFT, fill=X, expand=True, padx=(0, 7) if browse_cb else (0, 0))
        self._register_field(key, entry)
        if browse_cb:
            ttk.Button(controls, text="Browse", style="Secondary.TButton", command=browse_cb).pack(side=RIGHT)

        help_label = ttk.Label(row, text=explanation, style="Muted.TLabel", justify="left")
        help_label.pack(anchor="w", fill=X, pady=(3, 0))

        # Keep the helper text readable when the user resizes the split panes.
        def resize_help(event):
            help_label.configure(wraplength=max(180, event.width - 4))

        row.bind("<Configure>", resize_help, add="+")

    def _section(self, parent, title, description=None):
        box = ttk.Frame(parent, style="Panel.TFrame", padding=(0, 10, 0, 5))
        box.pack(fill=X, padx=15)
        ttk.Label(box, text=title.upper(), style="SmallHeading.TLabel").pack(anchor="w")
        if description:
            ttk.Label(box, text=description, style="Muted.TLabel", wraplength=660).pack(anchor="w", pady=(4, 0))
        ttk.Separator(parent, orient="horizontal").pack(fill=X, padx=15, pady=(4, 2))
        return box

    def _parameter_row(self, parent, label, key, description, values=None, checkbox_key=None, width=18):
        row = ttk.Frame(parent, style="Panel.TFrame", padding=(15, 6, 15, 6))
        row.pack(fill=X)
        text_col = ttk.Frame(row, style="Panel.TFrame")
        text_col.pack(side=LEFT, fill=X, expand=True, padx=(0, 12))
        lab = ttk.Label(text_col, text=label, style="Panel.TLabel")
        lab.pack(anchor="w")
        ttk.Label(text_col, text=description, style="Muted.TLabel", wraplength=405, justify="left").pack(anchor="w", pady=(3, 0))
        ToolTip(lab, description)
        control_col = ttk.Frame(row, style="Panel.TFrame")
        control_col.pack(side=RIGHT, anchor="e")
        if values is not None:
            ctrl = ttk.Combobox(control_col, textvariable=self.vars[key], values=values, state="readonly", width=width)
        else:
            ctrl = ttk.Entry(control_col, textvariable=self.vars[key], width=width)
        ctrl.pack(side=LEFT)
        self._register_field(key, ctrl)
        if checkbox_key:
            chk = ttk.Checkbutton(control_col, text="Enable", variable=self.vars[checkbox_key], command=self.update_preview)
            chk.pack(side=LEFT, padx=(8, 0))
            self._register_field(checkbox_key, chk)
        return ctrl

    def _toggle_row(self, parent, label, key, description):
        row = ttk.Frame(parent, style="Panel.TFrame", padding=(15, 6, 15, 6))
        row.pack(fill=X)
        chk = ttk.Checkbutton(row, text=label, variable=self.vars[key], command=self.update_preview)
        chk.pack(side=LEFT, anchor="w")
        ttk.Label(row, text=description, style="Muted.TLabel", wraplength=450, justify="left").pack(side=LEFT, fill=X, expand=True, padx=(12, 0))
        ToolTip(chk, description)
        self._register_field(key, chk)

    def _build_3d_tab(self, parent):
        self._section(parent, "Surface sampling", "These settings determine which world surfaces become points. Sampling affects both outputs; PCD-only filters below affect only the saved 3D file.")
        self._parameter_row(parent, "Sampling density", "density",
                            "Points per square metre. Higher values retain smaller details but increase runtime and memory use.")
        self._parameter_row(parent, "Geometry source", "geometry",
                            "Collision is usually best for navigation. Choose visual if walls or objects have no collision geometry.",
                            values=["collision", "visual"])
        self._parameter_row(parent, "Random seed", "seed",
                            "Keeps sampling repeatable when the input and all settings remain the same.")

        self._section(parent, "PCD output filters", "Only used when saving the 3D point cloud. They do not crop points used to build the 2D grid.")
        self._parameter_row(parent, "Voxel leaf size (m)", "voxel",
                            "Downsamples the PCD. 0 disables voxel filtering; 0.05 means 5 cm voxels.")
        self._parameter_row(parent, "Minimum height (m)", "z_min",
                            "Discard PCD points below this world-frame Z height.", checkbox_key="z_min_enabled")
        self._parameter_row(parent, "Maximum height (m)", "z_max",
                            "Discard PCD points above this world-frame Z height.", checkbox_key="z_max_enabled")
        self._parameter_row(parent, "Transparency threshold", "transparency",
                            "In visual mode, skip visuals with SDF transparency at or above this value. Valid range: 0–1.")
        self._toggle_row(parent, "Write ASCII PCD", "ascii",
                         "Creates a human-readable PCD file. Binary is smaller and generally preferable.")

    def _build_2d_tab(self, parent):
        self._section(parent, "Nav2 occupancy grid", "The selected height band is projected into 2D. This map is binary occupied/free; it does not contain unknown cells.")
        self._parameter_row(parent, "Grid resolution (m/cell)", "grid_resolution",
                            "Cell size. 0.05 creates 5 cm cells; smaller resolution increases memory use and file size.")
        self._parameter_row(parent, "Obstacle band · minimum Z (m)", "slice_z_min",
                            "Lowest point height considered an obstacle in the 2D grid.")
        self._parameter_row(parent, "Obstacle band · maximum Z (m)", "slice_z_max",
                            "Highest point height considered an obstacle in the 2D grid.")
        self._parameter_row(parent, "Map extent", "grid_bounds",
                            "Full uses bounds from the whole sampled cloud. Slice uses only obstacle-band points plus a margin.",
                            values=["full", "slice"])
        self._parameter_row(parent, "Slice margin (m)", "grid_margin",
                            "Extra border around slice bounds. Used only when map extent is slice.")
        self._parameter_row(parent, "Closing radius (cells)", "grid_close",
                            "Fills small speckle holes. 0 disables it; large values may close narrow passages.")
        note = ttk.Frame(parent, style="Panel.TFrame", padding=(15, 12, 15, 12))
        note.pack(fill=X)
        ttk.Label(note, text="Map semantics", style="Section.TLabel").pack(anchor="w")
        ttk.Label(note, text="Every in-bounds cell not hit by a sampled point in the obstacle band becomes free. Inspect the PGM before autonomous use; geometrically unobserved spaces can also appear free.",
                  style="Muted.TLabel", wraplength=630, justify="left").pack(anchor="w", pady=(5, 0))

    def _build_advanced_tab(self, parent):
        self._section(parent, "Model filters", "One regular expression per line. Each line is passed as a separate repeatable --exclude option.")
        row = ttk.Frame(parent, style="Panel.TFrame", padding=(15, 8, 15, 8))
        row.pack(fill=X)
        self.exclude_text = Text(row, height=4, bg="#0D1727", fg=TEXT, insertbackground=TEXT,
                                 relief="flat", highlightthickness=1, highlightbackground=BORDER,
                                 highlightcolor=ACCENT, font=("DejaVu Sans Mono", 9), wrap="word")
        self.exclude_text.pack(fill=X, expand=True)
        self.exclude_text.insert("1.0", self.vars["exclude_regex"].get())
        self.exclude_text.bind("<KeyRelease>", self._exclude_text_changed)
        ToolTip(self.exclude_text, "Examples: Person|MaleVisitor|Casual or Tree_.*. Matching model names are excluded from sampling.")

        self._section(parent, "Sampling & runtime")
        self._toggle_row(parent, "Exclude plane geometries", "exclude_ground",
                         "Skips SDF plane shapes. Does not remove ground represented by a mesh or box.")
        self._toggle_row(parent, "Disable Fuel URL downloads", "no_download",
                         "Prevents downloading missing models referenced by full Fuel URLs. It does not make unresolved model:// names resolvable.")
        self._toggle_row(parent, "Publish point cloud to RViz", "publish",
                         "Publishes /sdf2map/map_cloud and keeps the converter alive. Available only in 3D/Both output modes.")
        self._toggle_row(parent, "Verbose model poses", "verbose",
                         "Prints resolved model poses and additional exclusion details in the run log.")

        self._section(parent, "ROS 2 environment", "Optional setup scripts are sourced before running ros2. Paths are auto-detected where possible.")
        self._path_row(parent, "ROS setup script", "ros_setup", "Usually /opt/ros/jazzy/setup.bash.", self.browse_ros_setup)
        self._path_row(parent, "Workspace setup script", "workspace_setup", "Your overlay, typically /jazzy_ws/install/setup.bash.", self.browse_workspace_setup)

        note = ttk.Frame(parent, style="Panel.TFrame", padding=(15, 10, 15, 12))
        note.pack(fill=X)
        ttk.Label(note, text="Important implementation detail", style="Section.TLabel").pack(anchor="w")
        ttk.Label(note, text="The current sdf2map executable always writes a PCD internally. In 2D-only mode, Studio directs that required file to a hidden temporary path and deletes it after the process exits.",
                  style="Muted.TLabel", wraplength=630, justify="left").pack(anchor="w", pady=(5, 0))

    def _build_right_panel(self, parent):
        self._card_heading(parent, "COMMAND PREVIEW")
        ttk.Label(parent, text="Generated from the active settings. The app runs this safely through Bash after sourcing the setup files above.",
                  style="Muted.TLabel", wraplength=460, justify="left").pack(anchor="w", pady=(0, 8))
        command_frame = ttk.Frame(parent, style="Panel.TFrame")
        command_frame.pack(fill=X)
        self.command_text = Text(command_frame, height=9, bg="#08111E", fg="#BAE6FD", insertbackground=TEXT,
                                 relief="flat", padx=10, pady=9, wrap="word", font=("DejaVu Sans Mono", 8),
                                 highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT)
        self.command_text.pack(fill=X, expand=True)
        buttons = ttk.Frame(parent, style="Panel.TFrame")
        buttons.pack(fill=X, pady=(7, 14))
        ttk.Button(buttons, text="Copy command", style="Secondary.TButton", command=self.copy_command).pack(side=LEFT)
        ttk.Button(buttons, text="Open output folder", style="Secondary.TButton", command=self.open_output_folder).pack(side=LEFT, padx=(7, 0))

        ttk.Separator(parent, orient="horizontal").pack(fill=X, pady=(0, 13))
        run_header = ttk.Frame(parent, style="Panel.TFrame")
        run_header.pack(fill=X)
        ttk.Label(run_header, text="RUN CONVERSION", style="Section.TLabel").pack(side=LEFT)
        ttk.Label(run_header, text="LIVE OUTPUT", style="SmallHeading.TLabel").pack(side=RIGHT)
        actions = ttk.Frame(parent, style="Panel.TFrame")
        actions.pack(fill=X, pady=(9, 8))
        self.run_button = ttk.Button(actions, text="▶  Run conversion", style="Primary.TButton", command=self.start_run)
        self.run_button.pack(side=LEFT, fill=X, expand=True)
        self.stop_button = ttk.Button(actions, text="Stop", style="Secondary.TButton", command=self.stop_run, state="disabled")
        self.stop_button.pack(side=LEFT, padx=(8, 0))
        self.clear_log_button = ttk.Button(actions, text="Clear log", style="Secondary.TButton", command=self.clear_log)
        self.clear_log_button.pack(side=LEFT, padx=(8, 0))

        log_frame = ttk.Frame(parent, style="Panel.TFrame")
        log_frame.pack(fill=BOTH, expand=True)
        self.log_text = Text(log_frame, bg="#08111E", fg="#C7D3E5", insertbackground=TEXT,
                             relief="flat", padx=10, pady=9, wrap="word", font=("DejaVu Sans Mono", 8),
                             highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT,
                             state="disabled")
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.pack(side=LEFT, fill=BOTH, expand=True)
        log_scroll.pack(side=RIGHT, fill=Y)
        self.log_text.tag_configure("success", foreground=GREEN)
        self.log_text.tag_configure("warning", foreground=AMBER)
        self.log_text.tag_configure("error", foreground=RED)
        self.log_text.tag_configure("muted", foreground=MUTED)
        self._append_log("Ready. Configure the source, choose outputs, then run conversion.", "muted")

    def _register_field(self, key, widget):
        self._field_widgets.setdefault(key, []).append(widget)

    def _connect_traces(self):
        for key, variable in self.vars.items():
            if key in {"exclude_regex"}:
                continue
            try:
                variable.trace_add("write", self._schedule_preview)
            except Exception:
                pass

    def _schedule_preview(self, *_args):
        if self._preview_after_id is not None:
            try:
                self.root.after_cancel(self._preview_after_id)
            except Exception:
                pass
        self._preview_after_id = self.root.after(120, self._refresh_debounced)

    def _refresh_debounced(self):
        self._preview_after_id = None
        self.update_preview()
        self.update_mode_state()

    def _exclude_text_changed(self, _event=None):
        self.vars["exclude_regex"].set(self.exclude_text.get("1.0", "end-1c"))
        self.update_preview()

    def _load_preset_names(self):
        names = list(BUILTIN_PRESETS.keys())
        custom = self._read_custom_presets()
        names.extend(sorted(custom.keys(), key=str.casefold))
        self.preset_names = names
        self.preset_combo.configure(values=names)
        if self.preset_var.get() not in names:
            self.preset_var.set(names[0] if names else "")

    def _read_custom_presets(self):
        try:
            data = json.loads(PRESETS_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _write_custom_presets(self, data):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        PRESETS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def _parameter_settings(self):
        keys = [
            "output_mode", "density", "geometry", "voxel", "z_min_enabled", "z_min",
            "z_max_enabled", "z_max", "transparency", "exclude_ground", "ascii", "seed",
            "no_download", "publish", "verbose", "exclude_regex", "grid_resolution",
            "slice_z_min", "slice_z_max", "grid_bounds", "grid_margin", "grid_close",
        ]
        return {key: self.vars[key].get() for key in keys}

    def apply_selected_preset(self, _event=None):
        name = self.preset_var.get()
        data = BUILTIN_PRESETS.get(name)
        if data is None:
            data = self._read_custom_presets().get(name)
        if not isinstance(data, dict):
            return
        for key, value in data.items():
            if key in self.vars:
                try:
                    self.vars[key].set(value)
                except Exception:
                    pass
        if hasattr(self, "exclude_text"):
            self.exclude_text.delete("1.0", END)
            self.exclude_text.insert("1.0", self.vars["exclude_regex"].get())
        self.update_preview()
        self.update_mode_state()
        self._set_status(f"Preset loaded · {name}")
        self._append_log(f"Applied preset: {name}", "muted")

    def save_preset(self):
        name = simpledialog.askstring("Save preset", "Preset name:", parent=self.root)
        if not name:
            return
        name = name.strip()
        if not name:
            return
        if name in BUILTIN_PRESETS:
            messagebox.showerror("Preset name reserved", "Choose a different name; built-in presets cannot be overwritten.", parent=self.root)
            return
        custom = self._read_custom_presets()
        custom[name] = self._parameter_settings()
        try:
            self._write_custom_presets(custom)
        except OSError as exc:
            messagebox.showerror("Cannot save preset", str(exc), parent=self.root)
            return
        self._load_preset_names()
        self.preset_var.set(name)
        self._set_status(f"Preset saved · {name}")
        self._append_log(f"Saved preset: {name}", "success")

    def delete_preset(self):
        name = self.preset_var.get()
        if name in BUILTIN_PRESETS:
            messagebox.showinfo("Built-in preset", "Built-in presets cannot be deleted.", parent=self.root)
            return
        custom = self._read_custom_presets()
        if name not in custom:
            return
        if not messagebox.askyesno("Delete preset", f"Delete preset ‘{name}’?", parent=self.root):
            return
        del custom[name]
        try:
            self._write_custom_presets(custom)
        except OSError as exc:
            messagebox.showerror("Cannot delete preset", str(exc), parent=self.root)
            return
        self._load_preset_names()
        if self.preset_names:
            self.preset_var.set(self.preset_names[0])
            self.apply_selected_preset()
        self._set_status(f"Preset deleted · {name}")

    def browse_input(self):
        path = filedialog.askopenfilename(parent=self.root, title="Choose an SDF world or model",
                                          filetypes=[("SDF / world files", "*.sdf *.world"), ("All files", "*.*")])
        if path:
            previous_input = self.vars["input"].get().strip()
            previous_stem = Path(previous_input).stem if previous_input else "small_city"
            self.vars["input"].set(path)
            new_stem = Path(path).stem
            current_pcd = self.vars["pcd_name"].get().strip()
            current_yaml = self.vars["yaml_name"].get().strip()
            if current_pcd in {"", "small_city.pcd", previous_stem + ".pcd"}:
                self.vars["pcd_name"].set(new_stem + ".pcd")
            if current_yaml in {"", "small_city.yaml", previous_stem + ".yaml"}:
                self.vars["yaml_name"].set(new_stem + ".yaml")

    def browse_model_path(self):
        path = filedialog.askdirectory(parent=self.root, title="Add model search directory")
        if path:
            existing = [p.strip() for p in self.vars["model_paths"].get().split(os.pathsep) if p.strip()]
            if path not in existing:
                existing.append(path)
            self.vars["model_paths"].set(os.pathsep.join(existing))

    def browse_output_dir(self):
        path = filedialog.askdirectory(parent=self.root, title="Choose output folder")
        if path:
            self.vars["output_dir"].set(path)

    def browse_ros_setup(self):
        path = filedialog.askopenfilename(parent=self.root, title="Choose ROS 2 setup.bash",
                                          filetypes=[("Bash setup scripts", "*.bash *.sh"), ("All files", "*.*")])
        if path:
            self.vars["ros_setup"].set(path)

    def browse_workspace_setup(self):
        path = filedialog.askopenfilename(parent=self.root, title="Choose workspace install/setup.bash",
                                          filetypes=[("Bash setup scripts", "*.bash *.sh"), ("All files", "*.*")])
        if path:
            self.vars["workspace_setup"].set(path)

    def update_mode_state(self):
        mode = self.vars["output_mode"].get()
        if mode == "3D point cloud":
            self.mode_hint.set("Generates only the .pcd deliverable. Occupancy-grid options are ignored.")
        elif mode == "2D occupancy grid":
            self.mode_hint.set("Generates .yaml + .pgm only. A hidden temporary PCD is used internally and removed afterwards.")
        else:
            self.mode_hint.set("Generates .pcd plus the Nav2 .yaml + .pgm map.")
        publish_enabled = mode in {"3D point cloud", "Both"}
        for widget in self._field_widgets.get("publish", []):
            try:
                widget.configure(state="normal" if publish_enabled else "disabled")
            except Exception:
                pass
        # These are PCD-only filters. Disable them in 2D-only mode to signal they do not affect the grid.
        pcd_only_enabled = mode in {"3D point cloud", "Both"}
        for key in ("voxel", "z_min", "z_max", "z_min_enabled", "z_max_enabled", "ascii", "pcd_name"):
            for widget in self._field_widgets.get(key, []):
                try:
                    widget.configure(state="normal" if pcd_only_enabled else "disabled")
                except Exception:
                    pass
        for widget in self._field_widgets.get("yaml_name", []):
            try:
                widget.configure(state="normal" if mode in {"2D occupancy grid", "Both"} else "disabled")
            except Exception:
                pass
        self.update_preview()

    def _normalised_filename(self, key: str, suffix: str) -> str:
        name = self.vars[key].get().strip()
        if name and not name.lower().endswith(suffix):
            name += suffix
        return name

    def _current_temp_path(self, output_dir: Path, base: str) -> Path:
        if self.preview_temp_pcd is not None and self.preview_temp_pcd.parent == output_dir and not self.preview_temp_pcd.exists():
            return self.preview_temp_pcd
        candidate = output_dir / f".{base}.sdf2map-studio-temp.pcd"
        suffix = 2
        while candidate.exists():
            candidate = output_dir / f".{base}.sdf2map-studio-temp-{suffix}.pcd"
            suffix += 1
        self.preview_temp_pcd = candidate
        return candidate

    def _make_args(self, temp_path: Path | None = None):
        mode = self.vars["output_mode"].get()
        input_file = Path(self.vars["input"].get().strip()).expanduser()
        outdir = Path(self.vars["output_dir"].get().strip()).expanduser()
        pcd_filename = self._normalised_filename("pcd_name", ".pcd")
        yaml_filename = self._normalised_filename("yaml_name", ".yaml")
        base = Path(yaml_filename).stem or "map"
        pcd_path = outdir / pcd_filename
        yaml_path = outdir / yaml_filename
        is_2d = mode == "2D occupancy grid"
        if is_2d:
            pcd_path = temp_path or self._current_temp_path(outdir, base)

        args = ["ros2", "run", "sdf2map", "sdf2map", "--input", str(input_file)]
        model_paths = [p.strip() for p in self.vars["model_paths"].get().split(os.pathsep) if p.strip()]
        for p in model_paths:
            args.extend(["--model-path", str(Path(p).expanduser())])
        args.extend(["--output", str(pcd_path)])

        # Geometry sampling options affect both PCD and 2D grid.
        args.extend(["--density", self.vars["density"].get().strip() or "400"])
        geom = self.vars["geometry"].get().strip().lower()
        args.extend(["--geometry", "v" if geom == "visual" else "c"])
        args.extend(["--seed", self.vars["seed"].get().strip() or "42"])
        args.extend(["--transparency-threshold", self.vars["transparency"].get().strip() or "0.95"])

        for key, flag in (("z_min_enabled", "--z-min"), ("z_max_enabled", "--z-max")):
            if not is_2d and self.vars[key].get():
                val_key = "z_min" if key == "z_min_enabled" else "z_max"
                args.extend([flag, self.vars[val_key].get().strip()])
        if not is_2d:
            args.extend(["--voxel", self.vars["voxel"].get().strip() or "0"])
            if self.vars["ascii"].get():
                args.append("--ascii")

        if self.vars["exclude_ground"].get():
            args.append("--exclude-ground")
        for pattern in self.vars["exclude_regex"].get().splitlines():
            pattern = pattern.strip()
            if pattern:
                args.extend(["--exclude", pattern])
        if self.vars["no_download"].get():
            args.append("--no-download")
        if self.vars["verbose"].get():
            args.append("--verbose")
        if self.vars["publish"].get() and not is_2d:
            args.append("--publish")

        if mode in {"2D occupancy grid", "Both"}:
            args.extend([
                "--occupancy-grid", str(yaml_path),
                "--grid-resolution", self.vars["grid_resolution"].get().strip() or "0.05",
                "--slice-z-min", self.vars["slice_z_min"].get().strip() or "0.1",
                "--slice-z-max", self.vars["slice_z_max"].get().strip() or "1.8",
                "--grid-bounds", self.vars["grid_bounds"].get().strip() or "full",
                "--grid-margin", self.vars["grid_margin"].get().strip() or "1.0",
                "--grid-close", self.vars["grid_close"].get().strip() or "1",
            ])
        return args, pcd_path, yaml_path

    def _shell_command(self, args):
        commands = []
        ros_setup = self.vars["ros_setup"].get().strip()
        workspace_setup = self.vars["workspace_setup"].get().strip()
        if ros_setup:
            commands.append(f"source {shlex.quote(str(Path(ros_setup).expanduser()))}")
        if workspace_setup:
            commands.append(f"source {shlex.quote(str(Path(workspace_setup).expanduser()))}")
        commands.append("exec " + shlex.join(args))
        return "set -o pipefail; " + " && ".join(commands)

    def _preview_text_value(self):
        try:
            args, pcd_path, yaml_path = self._make_args()
            shell_script = self._shell_command(args)
            return "bash -lc " + shlex.quote(shell_script)
        except Exception as exc:
            return f"Configuration preview unavailable: {exc}"

    def update_preview(self):
        if not hasattr(self, "command_text"):
            return
        command = self._preview_text_value()
        self.command_text.configure(state="normal")
        self.command_text.delete("1.0", END)
        self.command_text.insert("1.0", command)
        self.command_text.configure(state="disabled")

    def copy_command(self):
        command = self._preview_text_value()
        self.root.clipboard_clear()
        self.root.clipboard_append(command)
        self._set_status("Command copied to clipboard")

    def open_output_folder(self):
        path = Path(self.vars["output_dir"].get().strip()).expanduser()
        try:
            path.mkdir(parents=True, exist_ok=True)
            if shutil.which("xdg-open"):
                subprocess.Popen(["xdg-open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                messagebox.showinfo("Output folder", str(path), parent=self.root)
        except OSError as exc:
            messagebox.showerror("Cannot open output folder", str(exc), parent=self.root)

    def _validate(self):
        input_text = self.vars["input"].get().strip()
        if not input_text:
            raise ValueError("Choose an input SDF/world file.")
        input_path = Path(input_text).expanduser()
        if not input_path.is_file():
            raise ValueError(f"Input file does not exist:\n{input_path}")
        for key, label, suffix in (("pcd_name", "PCD filename", ".pcd"), ("yaml_name", "Nav2 YAML filename", ".yaml")):
            filename = self._normalised_filename(key, suffix)
            if not filename or filename in {".", ".."} or any(ch in filename for ch in "/\\\0"):
                raise ValueError(f"{label} must be a simple filename without directory separators.")
        output_text = self.vars["output_dir"].get().strip()
        if not output_text:
            raise ValueError("Choose an output folder.")
        output_dir = Path(output_text).expanduser()

        def get_float(key, label):
            try:
                value = float(self.vars[key].get().strip())
            except ValueError:
                raise ValueError(f"{label} must be a number.")
            if not (value == value and abs(value) != float("inf")):
                raise ValueError(f"{label} must be finite.")
            return value

        def get_int(key, label):
            try:
                return int(self.vars[key].get().strip())
            except ValueError:
                raise ValueError(f"{label} must be an integer.")

        if get_float("density", "Sampling density") <= 0:
            raise ValueError("Sampling density must be greater than zero.")
        if get_float("transparency", "Transparency threshold") < 0 or get_float("transparency", "Transparency threshold") > 1:
            raise ValueError("Transparency threshold must be between 0 and 1.")
        if get_int("seed", "Random seed") < 0:
            raise ValueError("Random seed must be a non-negative integer.")
        mode = self.vars["output_mode"].get()
        if mode != "2D occupancy grid":
            if get_float("voxel", "Voxel size") < 0:
                raise ValueError("Voxel size cannot be negative.")
            if self.vars["z_min_enabled"].get():
                get_float("z_min", "Minimum PCD height")
            if self.vars["z_max_enabled"].get():
                get_float("z_max", "Maximum PCD height")
            if self.vars["z_min_enabled"].get() and self.vars["z_max_enabled"].get():
                if get_float("z_min", "Minimum PCD height") >= get_float("z_max", "Maximum PCD height"):
                    raise ValueError("Minimum PCD height must be below maximum PCD height.")
        if mode in {"2D occupancy grid", "Both"}:
            if get_float("grid_resolution", "Grid resolution") <= 0:
                raise ValueError("Grid resolution must be greater than zero.")
            if get_float("slice_z_min", "Obstacle-band minimum Z") >= get_float("slice_z_max", "Obstacle-band maximum Z"):
                raise ValueError("Obstacle-band minimum Z must be below maximum Z.")
            if get_float("grid_margin", "Grid margin") < 0:
                raise ValueError("Grid margin cannot be negative.")
            if get_int("grid_close", "Closing radius") < 0:
                raise ValueError("Closing radius cannot be negative.")
        for key, title in (("ros_setup", "ROS setup script"), ("workspace_setup", "Workspace setup script")):
            path_text = self.vars[key].get().strip()
            if path_text and not Path(path_text).expanduser().is_file():
                raise ValueError(f"{title} does not exist:\n{path_text}")
        return input_path, output_dir, Path(self._normalised_filename("yaml_name", ".yaml")).stem or "map"

    def start_run(self):
        if self.running:
            return
        try:
            input_path, output_dir, _ = self._validate()
            output_dir.mkdir(parents=True, exist_ok=True)
            yaml_stem = Path(self._normalised_filename("yaml_name", ".yaml")).stem or "map"
            if self.vars["output_mode"].get() == "2D occupancy grid":
                # Allocate a hidden file name not already present, so existing files are never overwritten.
                self.preview_temp_pcd = None
                self.active_temp_pcd = self._current_temp_path(output_dir, yaml_stem)
                pcd_temp = self.active_temp_pcd
            else:
                self.active_temp_pcd = None
                pcd_temp = None
            args, pcd_path, yaml_path = self._make_args(temp_path=pcd_temp)
            shell_script = self._shell_command(args)
        except (ValueError, OSError) as exc:
            messagebox.showerror("Check your settings", str(exc), parent=self.root)
            return

        mode = self.vars["output_mode"].get()
        self.running = True
        self.run_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.clear_log_button.configure(state="disabled")
        # Animate only while a conversion is active. In determinate mode at
        # zero, the idle progress bar is visually empty instead of showing a
        # misleading leftover indeterminate segment.
        self.progress.configure(mode="indeterminate")
        self.progress.start(10)
        self._set_status("Running · Sampling world geometry…", ACCENT)
        self._append_log("\n" + "─" * 52, "muted")
        self._append_log(f"Starting conversion · mode={mode}", "success")
        self._append_log(f"Input: {input_path}", "muted")
        self._append_log(f"Output folder: {output_dir}", "muted")
        if mode in {"3D point cloud", "Both"}:
            self._append_log(f"PCD target: {output_dir / self._normalised_filename('pcd_name', '.pcd')}", "muted")
        if mode in {"2D occupancy grid", "Both"}:
            self._append_log(f"Nav2 map target: {yaml_path} (+ PGM)", "muted")
        self._append_log("Running CLI…", "muted")
        self.update_preview()

        def run_worker():
            return_code = None
            launch_error = None
            try:
                # shell_script is shell-quoted argument-by-argument by _shell_command().
                self.process = subprocess.Popen(
                    ["bash", "-lc", shell_script], stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, text=True, bufsize=1,
                )
                assert self.process.stdout is not None
                for line in self.process.stdout:
                    self.events.put(("line", line.rstrip("\n")))
                return_code = self.process.wait()
            except Exception as exc:
                launch_error = str(exc)
            finally:
                self.process = None
                if self.active_temp_pcd:
                    try:
                        if self.active_temp_pcd.exists():
                            self.active_temp_pcd.unlink()
                        self.events.put(("line", "[Studio] Removed temporary PCD used for 2D-only output."))
                    except OSError as exc:
                        self.events.put(("line", f"[Studio] Warning: could not remove temporary PCD: {exc}"))
                self.events.put(("done", return_code, launch_error, mode, str(output_dir), pcd_path.name, yaml_path.name))

        self.worker = threading.Thread(target=run_worker, daemon=True)
        self.worker.start()

    def stop_run(self):
        proc = self.process
        if proc is not None and proc.poll() is None:
            self._set_status("Stopping process…", AMBER)
            try:
                proc.terminate()
            except OSError as exc:
                self._append_log(f"Could not stop process: {exc}", "error")
        else:
            self._append_log("No active process to stop.", "muted")

    def _poll_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "line":
                    line = event[1]
                    tag = None
                    if "ERROR" in line or "Error" in line or "error:" in line.lower():
                        tag = "error"
                    elif "WARNING" in line or "Warning" in line or "skipped" in line.lower():
                        tag = "warning"
                    elif "wrote" in line or "success" in line.lower():
                        tag = "success"
                    self._append_log(line, tag)
                elif event[0] == "done":
                    _, return_code, launch_error, mode, outdir, pcd_filename, yaml_filename = event
                    self.running = False
                    self.run_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                    self.clear_log_button.configure(state="normal")
                    self.progress.stop()
                    self.progress.configure(mode="determinate", value=0)
                    self.active_temp_pcd = None
                    self.preview_temp_pcd = None
                    if launch_error:
                        self._append_log(f"[Studio] Failed to launch converter: {launch_error}", "error")
                        self._set_status("Failed to launch converter", RED)
                    elif return_code == 0:
                        self._append_log("Conversion completed successfully.", "success")
                        if mode in {"3D point cloud", "Both"}:
                            self._append_log(f"Saved: {Path(outdir) / pcd_filename}", "success")
                        if mode in {"2D occupancy grid", "Both"}:
                            self._append_log(f"Saved: {Path(outdir) / yaml_filename} and matching .pgm", "success")
                        self._set_status("Completed successfully", GREEN)
                    else:
                        self._append_log(f"Converter exited with status {return_code}.", "error")
                        self._set_status(f"Conversion failed · exit code {return_code}", RED)
                    self.update_preview()
        except queue.Empty:
            pass
        if self.root.winfo_exists():
            self.root.after(100, self._poll_events)

    def _append_log(self, text, tag=None):
        if not hasattr(self, "log_text"):
            return
        self.log_text.configure(state="normal")
        self.log_text.insert(END, text + "\n", tag or "")
        self._log_line_count += 1
        # Keep the console responsive during extremely verbose runs.
        if self._log_line_count > 12000:
            self.log_text.delete("1.0", "1200.0")
            self._log_line_count = 10800
        self.log_text.see(END)
        self.log_text.configure(state="disabled")

    def clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", END)
        self.log_text.configure(state="disabled")
        self._log_line_count = 0

    def _set_status(self, text, color=MUTED):
        self.status_var.set(text)
        try:
            self.status_label.configure(foreground=color)
        except Exception:
            pass

    def on_close(self):
        if self.running:
            if not messagebox.askyesno("Conversion running", "Stop the running conversion and close Studio?", parent=self.root):
                return
            if self.process is not None and self.process.poll() is None:
                try:
                    self.process.terminate()
                except OSError:
                    pass
        self.root.destroy()


def main():
    root = Tk()
    try:
        app = SDF2MapStudio(root)
    except Exception as exc:
        try:
            messagebox.showerror(APP_NAME, f"Could not start the interface:\n{exc}", parent=root)
        except Exception:
            pass
        raise
    root.mainloop()


if __name__ == "__main__":
    main()
