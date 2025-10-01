from __future__ import annotations
import re
from typing import Dict, List, Optional

from .model import DTNode


def export_dtsi(root: DTNode) -> str:
    """
    Export the given node subtree to .dtsi text.
    - For nodes inside the subtree that have a numeric phandle property, generate a label and remove the phandle property.
    - Replace any numeric cells in properties that match a subtree phandle with &label references.
    - Leave external references untouched.
    """
    subtree_nodes: List[DTNode] = []

    def collect(n: DTNode):
        subtree_nodes.append(n)
        for c in n.children:
            collect(c)

    collect(root)

    # Build phandle -> node map for subtree
    ph_to_node: Dict[int, DTNode] = {}
    for n in subtree_nodes:
        ph = _parse_single_cell(n.properties.get("phandle"))
        if ph is not None:
            ph_to_node[ph] = n

    # Assign labels for nodes with phandle
    labels: Dict[DTNode, str] = {}
    used: set[str] = set()
    for ph, n in ph_to_node.items():
        base = _sanitize_label(n.name)
        if not base:
            base = "node"
        # Ensure unique; include phandle hex as suffix for stability
        candidate = f"{base}_{ph:x}"
        i = 1
        while candidate in used:
            i += 1
            candidate = f"{base}_{ph:x}_{i}"
        labels[n] = candidate
        used.add(candidate)

    # Emit text
    lines: List[str] = []
    lines.append(f"// Exported from path: {root.path}")
    _write_node_export(root, lines, 0, labels, ph_to_node)
    return "\n".join(lines) + "\n"


def _indent(n: int) -> str:
    return "  " * n


def _write_node_export(node: DTNode, out: List[str], level: int, labels: Dict[DTNode, str], ph_to_node: Dict[int, DTNode]):
    label = labels.get(node)
    name = node.name
    prefix = f"{label}: " if label else ""
    if level == 0:
        out.append(f"{prefix}{name} {{")
    else:
        out.append(f"{_indent(level)}{prefix}{name} {{")

    # properties (skip phandle)
    for k, v in node.properties.items():
        if k == "phandle":
            continue
        out.append(f"{_indent(level+1)}{k} = {_replace_phandles_in_value(v, ph_to_node, labels)};")

    # children
    for ch in node.children:
        _write_node_export(ch, out, level + 1, labels, ph_to_node)

    out.append(f"{_indent(level)}}};")


def _sanitize_label(name: str) -> str:
    # Labels: [A-Za-z_][A-Za-z0-9_]*
    s = name.split("@")[0]  # drop unit-address
    s = re.sub(r"[^A-Za-z0-9_]", "_", s)
    if not s or not re.match(r"[A-Za-z_]", s[0]):
        s = f"_{s}" if s else "_n"
    return s


def _replace_phandles_in_value(v: str, ph_to_node: Dict[int, DTNode], labels: Dict[DTNode, str]) -> str:
    """
    Replace numeric cells that match subtree phandles with &label within <...> groups.
    Leaves non-<...> content unchanged (strings, booleans, etc.).
    """
    if "<" not in v:
        return v

    def repl_group(m: re.Match[str]) -> str:
        content = m.group(1)
        tokens = content.strip().split()
        new_tokens: List[str] = []
        for t in tokens:
            try:
                num = int(t, 0)
            except Exception:
                new_tokens.append(t)
                continue
            node = ph_to_node.get(num)
            if node is None:
                new_tokens.append(t)
            else:
                lbl = labels.get(node)
                if lbl:
                    new_tokens.append(f"&{lbl}")
                else:
                    new_tokens.append(t)
        return "<" + " ".join(new_tokens) + ">"

    return re.sub(r"<([^>]*)>", repl_group, v)


def _parse_cells(val: Optional[str]) -> List[int]:
    if not val:
        return []
    nums: List[int] = []
    for grp in re.findall(r"<([^>]*)>", val):
        for tok in grp.strip().split():
            try:
                nums.append(int(tok, 0))
            except Exception:
                pass
    return nums


def _parse_single_cell(val: Optional[str]) -> Optional[int]:
    cells = _parse_cells(val)
    return cells[0] if cells else None
