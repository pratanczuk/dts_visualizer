# DTS Visualizer

A small Python Qt app to load a Device Tree Source (.dts) file and visualize nodes as icons by type.

- Left: hierarchical node tree
- Center: icon graph with pan/zoom
- Right: properties of selected node

## Run

1. Create venv and install deps

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Launch

```bash
python -m dts_visualizer.main
```

The app will auto-load `tests/device_tree.dts` if present.
