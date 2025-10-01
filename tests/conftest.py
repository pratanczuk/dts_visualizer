import os
import sys


def _ensure_src_on_path():
    repo_root = os.path.dirname(os.path.dirname(__file__))
    src = os.path.join(repo_root, 'src')
    if src not in sys.path:
        sys.path.insert(0, src)


_ensure_src_on_path()
