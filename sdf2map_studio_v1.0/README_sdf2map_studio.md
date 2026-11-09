# SDF2Map Studio · v1.0.1

A single-file desktop GUI for the existing `sdf2map` executable on ROS 2 Jazzy. It uses Python's standard-library Tkinter; no pip packages are required.

## Launch

Copy `sdf2map_studio.py` to your machine, then run it from a desktop terminal:

```bash
cd /jazzy_ws
python3 /path/to/sdf2map_studio.py
```

The app auto-detects `/opt/ros/jazzy/setup.bash` and common workspace overlay paths. You can edit both setup paths in **Advanced · Filters**. The conversion command is launched in Bash after sourcing those scripts.

If Python reports that `tkinter` is missing, install it with:

```bash
sudo apt update
sudo apt install python3-tk
```

Run it as the normal desktop user when possible. A graphical desktop session (`DISPLAY`/Wayland) is required.

## Features

- Output mode selector: 3D PCD, 2D Nav2 map (PGM + YAML), or both.
- Every `sdf2map --help` option is represented, with short inline explanations and hover help.
- Independent PCD and YAML output filenames; output directory selection.
- Editable source world and repeated/colon-separated `--model-path` directories.
- Built-in conversion presets and user presets saved persistently to `~/.config/sdf2map-studio/presets.json`.
- Live CLI preview, copy-command action, live process log, error reporting, and stop control.
- Basic input validation before a conversion starts.
- Source/output explanations display on a full-width line below each field row and reflow when the window is resized.
- Progress indicator stays empty while idle and animates only during conversion.

## 2D-only mode detail

The current upstream CLI always calls `ExportPCD` and writes a PCD before optionally writing the occupancy grid. For 2D-only mode, Studio directs that required intermediate PCD to a hidden temporary filename in the selected output directory and removes it when the process exits. The geometry sampling still happens; only the final PCD artifact is discarded.

## Map semantics

The generated occupancy grid marks sampled points in the configured height band as occupied and the other in-bounds cells as free. It does not create unknown cells, so inspect the PGM before using it for autonomous navigation.
