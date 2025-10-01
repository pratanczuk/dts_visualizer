import os
import sys

ROOT = os.path.dirname(__file__)
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from dts_visualizer.main import main

if __name__ == "__main__":
    main()
