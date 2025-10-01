from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(eq=False)
class DTNode:
    name: str
    path: str
    properties: Dict[str, str] = field(default_factory=dict)
    children: List["DTNode"] = field(default_factory=list)
    parent: Optional["DTNode"] = None

    def add_child(self, child: "DTNode") -> None:
        child.parent = self
        self.children.append(child)

    def find_by_path(self, path: str) -> Optional["DTNode"]:
        if self.path == path:
            return self
        for c in self.children:
            found = c.find_by_path(path)
            if found:
                return found
        return None
