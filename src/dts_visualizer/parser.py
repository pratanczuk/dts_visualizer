from __future__ import annotations
from typing import Dict, List, Optional
import re

from .model import DTNode


class DTSParser:
    """
    Lightweight, tolerant parser for a single .dts file.
    It won't support includes or macros, but is good enough for visualizing structure.
    If pyfdt is available, we could later swap to a full parser.
    """

    node_start_re = re.compile(r"^\s*([A-Za-z0-9_,.@-]+)?\s*\{\s*$")
    node_with_name_re = re.compile(r"^\s*([A-Za-z0-9_,.@-]+)\s*:\s*([A-Za-z0-9_,.@-]+)?\s*\{\s*$")
    property_re = re.compile(r"^\s*([A-Za-z0-9_,.+@/#-]+)\s*=\s*(.*?);\s*$")

    def parse(self, text: str) -> DTNode:
        tokens = self._tokenize(text)
        root = DTNode(name="/", path="/")
        stack: List[DTNode] = [root]

        i = 0
        while i < len(tokens):
            line = tokens[i].strip()
            i += 1
            if not line:
                continue

            if line.endswith("{"):
                # Root node like '/ {' should not create a child; just enter root scope
                if line.strip().startswith('/'):
                    # nothing to push; we are already at root
                    continue
                # try label: name { or name {
                m_label = self.node_with_name_re.match(line)
                if m_label:
                    label, name = m_label.groups()
                    name = name or label or "node"
                else:
                    m_name = self.node_start_re.match(line)
                    if m_name:
                        name = m_name.group(1) or "node"
                    else:
                        name = "node"
                parent = stack[-1]
                path = parent.path.rstrip("/") + "/" + name if parent.path != "/" else "/" + name
                new_node = DTNode(name=name, path=path)
                parent.add_child(new_node)
                stack.append(new_node)
                continue

            if line == "};":
                if len(stack) > 1:
                    stack.pop()
                continue

            # properties like: key = value;
            m_prop = self.property_re.match(line)
            if m_prop:
                key, value = m_prop.groups()
                # compress spaces and unquote common strings
                value = value.strip()
                if value.startswith('"') and value.endswith('"'):
                    value = value.strip('"')
                stack[-1].properties[key] = value
                continue

            # tolerate other lines (e.g., /dts-v1/, comments, directives)
        return root

    def _tokenize(self, text: str) -> List[str]:
        # Remove comments /* ... */ and // ...
        text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
        text = re.sub(r"//.*", " ", text)
        # Join multiline properties ending with ; on multiple lines
        lines: List[str] = []
        buf: List[str] = []
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            buf.append(line)
            joined = " ".join(buf)
            # if braces standalone, flush early
            if joined.endswith("{") or joined == "};" or joined.endswith(";"):
                lines.append(joined)
                buf = []
        if buf:
            lines.append(" ".join(buf))
        return lines
