# DTS Visualizer

A small Python Qt app to load a Device Tree Source (.dts) file and visualize nodes as icons by type.

- Left: hierarchical node tree
- Center: icon graph with pan/zoom
- Right: properties of selected node

## Run

### Ubuntu prerequisites

Install system packages required for Qt, OpenGL, and common DT tooling:

```bash
sudo apt update
sudo apt install -y \
	python3-venv python3-pip \
	libxcb-xinerama0 libxcb-cursor0 libxkbcommon-x11-0 \
	libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-render-util0 \
	libegl1 libgl1 \
	xdg-utils \
	device-tree-compiler dtc
```

Notes:
- On some distros you may see a benign warning about “xapp-gtk3-module”. It’s optional and not required by this app.
- If your Ubuntu version doesn’t have some XCB helper libraries, you can try installing `libqt5gui5` which pulls common X11 dependencies.
- If you run in a minimal container/WSL, ensure an X server is available or use an X11 forwarding setup.

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
