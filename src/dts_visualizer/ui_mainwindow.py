from __future__ import annotations
import os
from typing import Optional, List, Dict

from PySide6.QtCore import Qt, QRectF, QPoint
from PySide6.QtGui import QAction, QStandardItemModel, QStandardItem, QBrush, QColor, QPen, QPainter
from PySide6.QtWidgets import (
    QMainWindow, QFileDialog, QMessageBox, QSplitter, QTreeView, QWidget, QVBoxLayout, QHBoxLayout,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QLabel, QFormLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QMenu, QInputDialog, QListWidget, QListWidgetItem, QDialog, QDialogButtonBox, QLineEdit
)

from .parser import DTSParser
from .model import DTNode
from .icon_map import node_icon
from .serializer import serialize
from .exporter import export_dtsi
from .bindings import load_bindings, BindingsIndex


class NodeGraphicsItem(QGraphicsPixmapItem):
    def __init__(self, node: DTNode):
        self.node = node
        icon = node_icon(node.name, node.properties.get("compatible"))
        pm = icon.pixmap(48, 48)
        # Overlay status indicator
        status = node.properties.get("status", "").strip().strip('"').lower()
        enabled = status != "disabled"
        painter = QPainter(pm)
        color = QColor("#16a34a") if enabled else QColor("#dc2626")  # green/red
        pen = QPen(QColor("white"))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.setBrush(QBrush(color))
        r = 10
        painter.drawEllipse(pm.width() - r - 4, pm.height() - r - 4, r, r)
        painter.end()
        super().__init__(pm)
        # Tooltip
        self.setToolTip(f"{node.name}\nstatus: {status or 'okay'}")


class GraphView(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.setRenderHints(self.renderHints())
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        factor = 1.15 if delta > 0 else 1/1.15
        self.scale(factor, factor)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DTS Visualizer")
        self.resize(1200, 800)

        self.parser = DTSParser()
        self.root_node: Optional[DTNode] = None
        self.PATH_ROLE = Qt.UserRole + 1
        self.current_file = None  # type: Optional[str]
        self.node_items: Dict[DTNode, QGraphicsPixmapItem] = {}
        self.highlight_items: List = []
        self.all_nodes: List[DTNode] = []
        self.phandle_map: Dict[int, DTNode] = {}
        self.bindings_index = None  # type: BindingsIndex | None
        # Search state
        self._search_query = ""
        self._search_results = []
        self._search_index = -1
        self._search_ring = None  # graphics item for search highlight

        # UI
        self._make_menu()

        splitter = QSplitter(self)
        self.setCentralWidget(splitter)

        # Left panel: search + tree
        left = QWidget()
        left_layout = QVBoxLayout(left)
        search_row = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search nodes by name...")
        btn_search = QPushButton("Search")
        search_row.addWidget(self.search_edit)
        search_row.addWidget(btn_search)
        left_layout.addLayout(search_row)

        self.tree = QTreeView()
        self.tree_model = QStandardItemModel()
        self.tree_model.setHorizontalHeaderLabels(["Node tree"])
        self.tree.setModel(self.tree_model)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._tree_context_menu)
        self.tree.clicked.connect(self._on_tree_clicked)
        left_layout.addWidget(self.tree)
        splitter.addWidget(left)
        # Wire search
        btn_search.clicked.connect(self._search_nodes)
        self.search_edit.returnPressed.connect(self._search_nodes)

        # Center graph
        center = QWidget()
        center_layout = QVBoxLayout(center)
        # Zoom controls
        controls = QHBoxLayout()
        btn_zoom_in = QPushButton("+")
        btn_zoom_out = QPushButton("-")
        btn_fit = QPushButton("Fit")
        btn_users = QPushButton("Users")
        btn_clear = QPushButton("Clear")
        btn_zoom_in.setToolTip("Zoom In")
        btn_zoom_out.setToolTip("Zoom Out")
        btn_fit.setToolTip("Fit to View")
        btn_users.setToolTip("Highlight nodes that reference the selected node")
        btn_clear.setToolTip("Clear highlight")
        controls.addWidget(btn_zoom_in)
        controls.addWidget(btn_zoom_out)
        controls.addWidget(btn_fit)
        controls.addWidget(btn_users)
        controls.addWidget(btn_clear)
        controls.addStretch(1)
        center_layout.addLayout(controls)
        self.scene = QGraphicsScene()
        self.view = GraphView()
        self.view.setScene(self.scene)
        center_layout.addWidget(self.view)
        splitter.addWidget(center)
        # Wire buttons
        btn_zoom_in.clicked.connect(lambda: self._zoom(1.15))
        btn_zoom_out.clicked.connect(lambda: self._zoom(1/1.15))
        btn_fit.clicked.connect(self._fit_view)
        btn_users.clicked.connect(self._show_users)
        btn_clear.clicked.connect(self._clear_highlight)

        # Right properties
        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.path_label = QLabel("Path: -")
        right_layout.addWidget(self.path_label)
        self.props_table = QTableWidget(0, 2)
        self.props_table.setHorizontalHeaderLabels(["Property", "Value"])
        self.props_table.horizontalHeader().setStretchLastSection(True)
        self.props_table.itemChanged.connect(self._on_prop_changed)
        right_layout.addWidget(self.props_table)
        # Add/Delete property controls
        prop_btns = QHBoxLayout()
        btn_add_prop = QPushButton("Add Property")
        btn_del_prop = QPushButton("Delete Property")
        prop_btns.addWidget(btn_add_prop)
        prop_btns.addWidget(btn_del_prop)
        prop_btns.addStretch(1)
        right_layout.addLayout(prop_btns)
        btn_add_prop.clicked.connect(self._add_property)
        btn_del_prop.clicked.connect(self._delete_property)
        splitter.addWidget(right)

        splitter.setSizes([300, 700, 300])

        # Load test file by default if exists
        tests_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "tests", "device_tree.dts")
        if os.path.exists(tests_path):
            self.load_file(tests_path)

    def _make_menu(self):
        file_menu = self.menuBar().addMenu("File")
        open_act = QAction("Open DTS...", self)
        open_act.triggered.connect(self._open_dts)
        file_menu.addAction(open_act)
        save_act = QAction("Save", self)
        save_act.setShortcut("Ctrl+S")
        save_act.triggered.connect(self._save_dts)
        file_menu.addAction(save_act)
        bindings_menu = self.menuBar().addMenu("Bindings")
        load_bind_act = QAction("Load Bindings Directory...", self)
        load_bind_act.triggered.connect(self._load_bindings_dir)
        bindings_menu.addAction(load_bind_act)

    def _open_dts(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open DTS file", os.getcwd(), "Device Tree (*.dts)")
        if path:
            self.load_file(path)

    def load_file(self, path: str):
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
            self.root_node = self.parser.parse(text)
            self.current_file = path
        except Exception as e:
            QMessageBox.critical(self, "Parse error", str(e))
            return

        self._build_index()
        # reset search state on new file load
        self._search_query = ""
        self._search_results = []
        self._search_index = -1
        self._populate_tree()
        self._render_graph()

    def _populate_tree(self):
        self.tree_model.removeRows(0, self.tree_model.rowCount())
        if not self.root_node:
            return
        root_item = QStandardItem("/")
        root_item.setData(self.root_node.path, self.PATH_ROLE)
        self.tree_model.appendRow(root_item)

        def add_items(parent_item: QStandardItem, node: DTNode):
            for c in node.children:
                label = c.name
                item = QStandardItem(label)
                item.setData(c.path, self.PATH_ROLE)
                status = c.properties.get("status", "").strip().strip('"').lower()
                enabled = status != "disabled"
                item.setForeground(QBrush(QColor("#16a34a" if enabled else "#dc2626")))
                parent_item.appendRow(item)
                add_items(item, c)

        add_items(root_item, self.root_node)
        self.tree.expandAll()
        # Select root node and show its properties
        root_index = self.tree_model.indexFromItem(root_item)
        if root_index.isValid():
            self.tree.setCurrentIndex(root_index)
            self._on_tree_clicked(root_index)

    def _render_graph(self):
        self.scene.clear()
        self.highlight_items = []
        self._search_ring = None
        if not self.root_node:
            return
        # Layout: simple top-down tree layout
        x_gap = 120
        y_gap = 120

        positions = {}
        levels = {}

        def traverse(n: DTNode, depth: int = 0):
            levels.setdefault(depth, []).append(n)
            for ch in n.children:
                traverse(ch, depth + 1)

        traverse(self.root_node)
        for depth, nodes in levels.items():
            for idx, n in enumerate(nodes):
                positions[n] = (idx * x_gap, depth * y_gap)

        # Draw items
        self.node_items = {}
        for n, (x, y) in positions.items():
            item = NodeGraphicsItem(n)
            item.setPos(x, y)
            self.scene.addItem(item)
            self.node_items[n] = item

        # Draw edges
        pen = QPen(QColor("#888"))
        for n in positions:
            for ch in n.children:
                if ch in positions:
                    x1, y1 = positions[n]
                    x2, y2 = positions[ch]
                    self.scene.addLine(x1 + 24, y1 + 48, x2 + 24, y2, pen)

        # auto fit
        self._fit_view()

    def _fit_view(self):
        if self.scene.items():
            rect = self.scene.itemsBoundingRect().adjusted(-40, -40, 40, 40)
            if rect.isValid():
                self.view.fitInView(rect, Qt.KeepAspectRatio)

    def _zoom(self, factor: float):
        self.view.scale(factor, factor)

    def _focus_node(self, node: DTNode, *, highlight: bool = False):
        # Select in tree and center in view if present
        self._select_tree_path(node.path)
        item = self.node_items.get(node)
        if item:
            self.view.centerOn(item)
            if highlight:
                self._set_search_highlight(item)

    def _set_search_highlight(self, item: QGraphicsPixmapItem):
        # remove previous search ring
        if self._search_ring is not None:
            try:
                self.scene.removeItem(self._search_ring)
            except Exception:
                pass
            self._search_ring = None
        # draw a blue ring around the item without dimming others
        x = item.x(); y = item.y()
        r = 56
        pen = QPen(QColor("#3b82f6"))  # blue
        pen.setWidth(3)
        ring = self.scene.addEllipse(x-4, y-4, r, r, pen)
        ring.setZValue(-1)
        self._search_ring = ring

    def _search_nodes(self):
        text = self.search_edit.text().strip()
        if not text:
            return
        q = text.lower()
        # Rebuild results if query changed or empty
        if q != self._search_query or not self._search_results:
            # Ensure index is available
            if not self.all_nodes:
                self._build_index()
            self._search_results = [n for n in self.all_nodes if q in n.name.lower()]
            self._search_query = q
            self._search_index = -1
        if not self._search_results:
            QMessageBox.information(self, "Search", f"No node found matching '{text}'.")
            return
        # Advance to next match
        self._search_index = (self._search_index + 1) % len(self._search_results)
        node = self._search_results[self._search_index]
        self._focus_node(node, highlight=True)

    def _build_index(self):
        # Collect all nodes and map phandle -> node
        self.all_nodes = []
        def collect(n: DTNode):
            self.all_nodes.append(n)
            for c in n.children:
                collect(c)
        if self.root_node:
            collect(self.root_node)
        self.phandle_map = {}
        for n in self.all_nodes:
            ph = self._parse_single_cell(n.properties.get("phandle"))
            if ph is not None:
                self.phandle_map[ph] = n
        # Build symbols map from __symbols__ node if present
        self.symbols_map: Dict[str, str] = {}
        if self.root_node:
            sym = next((c for c in self.root_node.children if c.name == "__symbols__"), None)
            if sym:
                for k, v in sym.properties.items():
                    # value is a quoted full path like "/path/to/node"
                    p = (v or "").strip().strip('"')
                    if p:
                        self.symbols_map[k] = p

    def _parse_cells(self, val: Optional[str]) -> List[int]:
        if not val:
            return []
        s = val
        # find numbers like 0x..., decimal digits inside < >
        import re
        nums: List[int] = []
        for grp in re.findall(r"<([^>]*)>", s):
            for tok in grp.strip().split():
                try:
                    nums.append(int(tok, 0))
                except Exception:
                    pass
        return nums

    def _extract_label_refs(self, val: Optional[str]) -> List[int]:
        if not val:
            return []
        import re
        labels = re.findall(r"&([A-Za-z_][A-Za-z0-9_]*)", val)
        phs: List[int] = []
        for lbl in labels:
            path = getattr(self, 'symbols_map', {}).get(lbl)
            if not path or not self.root_node:
                continue
            node = self.root_node.find_by_path(path)
            if not node:
                continue
            ph = self._parse_single_cell(node.properties.get("phandle"))
            if ph is not None:
                phs.append(ph)
        return phs

    def _extract_phandle_refs(self, val: Optional[str]) -> List[int]:
        # Combine numeric cells and &label resolved via __symbols__
        return list(dict.fromkeys(self._parse_cells(val) + self._extract_label_refs(val)))

    def _parse_single_cell(self, val: Optional[str]) -> Optional[int]:
        cells = self._parse_cells(val)
        return cells[0] if cells else None

    def _nodes_using(self, target: DTNode) -> List[DTNode]:
        users: List[DTNode] = []
        t_ph = self._parse_single_cell(target.properties.get("phandle"))
        if t_ph is None:
            return users
        for n in self.all_nodes:
            if n is target:
                continue
            for k, v in n.properties.items():
                if not self._node_prop_may_reference_phandle(n, k):
                    continue
                cells = self._extract_phandle_refs(v)
                if t_ph in cells:
                    users.append(n)
                    break
        return users

    def _node_prop_may_reference_phandle(self, node: DTNode, key: str) -> bool:
        # Prefer bindings if available and node compatible is known
        comp = (node.properties.get("compatible") or "").strip().strip('"')
        if self.bindings_index and comp:
            if self.bindings_index.may_reference_phandle(comp, key):
                return True
        # fallback heuristic
        return self._prop_may_reference_phandle(key)

    def _prop_may_reference_phandle(self, key: str) -> bool:
        # Common consumer properties that hold phandles or phandle-arrays
        if key == "phandle" or key == "linux,phandle":
            return False
        base_keys = {
            # per user rules
            "interrupt-parent",
            "clocks",  # names are not phandles; clocks themselves are
            "dmas",    # names are not phandles; dmas themselves are
            "pinctrl-0", "pinctrl-1", "pinctrl-2",
            "iommus",
            # Plus common ones
            "assigned-clocks", "assigned-clock-parents",
            "resets", "gpios", "interrupts-extended",
            "phys", "power-domains", "memory-region",
            "thermal-sensors", "remote-endpoint", "sound-dai",
        }
        if key in base_keys:
            return True
        # Regulator supplies and other pattern-based
        if key.endswith("-supply"):
            return True
        # PHY handle
        if key in ("phy-handle", "phy"):
            return True
        if key.endswith("-gpios") or key.endswith("-gpio"):
            return True
        if key.endswith("-phandle") or key.endswith("-phandles"):
            return True
        # pinctrl lists beyond 0..2
        if key.startswith("pinctrl-"):
            return True
        return False

    def _load_bindings_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Select Linux bindings directory (Documentation/devicetree/bindings)")
        if not path:
            return
        try:
            idx = load_bindings(path)
        except Exception as e:
            QMessageBox.critical(self, "Bindings error", str(e))
            return
        self.bindings_index = idx
        QMessageBox.information(self, "Bindings", "Bindings loaded. Users feature will use them when possible.")

    def _highlight_nodes(self, nodes: List[DTNode]):
        # Clear old
        self._clear_highlight()
        # Dim all
        for item in self.node_items.values():
            item.setOpacity(0.25)
        # Highlight these
        pen = QPen(QColor("#f59e0b"))  # amber
        pen.setWidth(3)
        for n in nodes:
            it = self.node_items.get(n)
            if not it:
                continue
            it.setOpacity(1.0)
            # draw ring around icon
            x = it.x(); y = it.y()
            r = 54
            ring = self.scene.addEllipse(x-3, y-3, r, r, pen)
            ring.setZValue(-1)
            self.highlight_items.append(ring)

    def _clear_highlight(self):
        # Remove rings
        for it in self.highlight_items:
            self.scene.removeItem(it)
        self.highlight_items = []
        # Restore opacity
        for item in self.node_items.values():
            item.setOpacity(1.0)

    def _show_users(self):
        node = self._current_selected_node()
        if not node:
            return
        users = self._nodes_using(node)
        self._highlight_nodes(users)
        # Show popup list
        dlg = QDialog(self)
        dlg.setWindowTitle("Users of selected node")
        v = QVBoxLayout(dlg)
        lst = QListWidget()
        for u in users:
            # Store path in item data for retrieval
            it = QListWidgetItem(f"{u.path} ({u.name})")
            it.setData(Qt.UserRole, u.path)
            lst.addItem(it)
        v.addWidget(lst)
        bb = QDialogButtonBox(QDialogButtonBox.Ok)
        bb.accepted.connect(dlg.accept)
        # Support double-click to accept
        lst.itemDoubleClicked.connect(lambda _item: dlg.accept())
        v.addWidget(bb)
        if dlg.exec() == QDialog.Accepted:
            item = lst.currentItem()
            if item:
                path = item.data(Qt.UserRole)
                if path:
                    self._select_tree_path(path)
                    # Also ensure properties panel updates
                    idx = self.tree.currentIndex()
                    if idx.isValid():
                        self._on_tree_clicked(idx)

    def _select_tree_path(self, path: str):
        # Find the item with PATH_ROLE == path and select it
        root_item = self.tree_model.item(0, 0)
        if not root_item:
            return

        def find_item(it: QStandardItem) -> QStandardItem | None:
            if it.data(self.PATH_ROLE) == path:
                return it
            for r in range(it.rowCount()):
                child = it.child(r, 0)
                if not child:
                    continue
                found = find_item(child)
                if found:
                    return found
            return None

        target = find_item(root_item)
        if target:
            index = self.tree_model.indexFromItem(target)
            if index.isValid():
                # Expand parents
                parent = index.parent()
                while parent.isValid():
                    self.tree.expand(parent)
                    parent = parent.parent()
                self.tree.setCurrentIndex(index)
                self.tree.scrollTo(index)

    def _on_tree_clicked(self, index):
        path = index.data(self.PATH_ROLE)
        if not self.root_node or not path:
            return
        node = self.root_node.find_by_path(path)
        if node:
            self._show_properties(node)

    def _tree_context_menu(self, pos: QPoint):
        index = self.tree.indexAt(pos)
        if not index.isValid() or not self.root_node:
            return
        path = index.data(self.PATH_ROLE)
        node = self.root_node.find_by_path(path)
        if not node:
            return
        menu = QMenu(self)
        rename_act = menu.addAction("Rename node...")
        delete_act = menu.addAction("Delete node")
        export_act = menu.addAction("Export to .dtsi...")
        action = menu.exec(self.tree.viewport().mapToGlobal(pos))
        if action == rename_act:
            self._rename_node(node, index)
        elif action == delete_act:
            self._delete_node(node, index)
        elif action == export_act:
            self._export_dtsi(node)

    def _export_dtsi(self, node: DTNode):
        text = export_dtsi(node)
        default_name = f"{node.name.split('@')[0] or 'node'}.dtsi"
        path, _ = QFileDialog.getSaveFileName(self, "Export .dtsi", default_name, "DTS Include (*.dtsi)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        except Exception as e:
            QMessageBox.critical(self, "Export error", str(e))

    def _rename_node(self, node: DTNode, index):
        new_name, ok = QInputDialog.getText(self, "Rename Node", "New name:", text=node.name)
        if not ok or not new_name:
            return
        node.name = new_name
        # update path for node and subtree
        def update_paths(n: DTNode):
            if n.parent:
                parent_path = n.parent.path
                n.path = (parent_path.rstrip('/') + '/' + n.name) if parent_path != '/' else '/' + n.name
            for ch in n.children:
                update_paths(ch)
        update_paths(node)
        # refresh tree and graph
        self._populate_tree()
        self._render_graph()
        # reselect renamed node by path
        it = self.root_node.find_by_path(node.path)
        if it:
            self._show_properties(it)

    def _delete_node(self, node: DTNode, index):
        parent = node.parent
        if not parent:
            QMessageBox.warning(self, "Delete node", "Cannot delete root node.")
            return
        parent.children = [c for c in parent.children if c is not node]
        self._populate_tree()
        self._render_graph()

    def _on_prop_changed(self, item: QTableWidgetItem):
        # Update property in model for current selected node
        node = self._current_selected_node()
        if not node:
            return
        # Rebuild properties from the table to support key rename
        new_props: dict[str, str] = {}
        for r in range(self.props_table.rowCount()):
            k_item = self.props_table.item(r, 0)
            v_item = self.props_table.item(r, 1)
            if k_item is None or v_item is None:
                continue
            k = k_item.text()
            v = v_item.text()
            if k:
                new_props[k] = v
        node.properties = new_props
        if "status" in node.properties:
            self._render_graph()

    def _save_dts(self):
        if not self.root_node:
            return
        text = serialize(self.root_node)
        path = self.current_file
        if not path:
            # if no current file, ask user where to save
            path, _ = QFileDialog.getSaveFileName(self, "Save DTS", os.getcwd(), "Device Tree (*.dts)")
            if not path:
                return
            self.current_file = path
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        except Exception as e:
            QMessageBox.critical(self, "Save error", str(e))

    def _show_properties(self, node: DTNode):
        self.path_label.setText(f"Path: {node.path}")
        props = node.properties
        self.props_table.blockSignals(True)
        self.props_table.setRowCount(0)
        for k, v in sorted(props.items()):
            r = self.props_table.rowCount()
            self.props_table.insertRow(r)
            self.props_table.setItem(r, 0, QTableWidgetItem(k))
            self.props_table.setItem(r, 1, QTableWidgetItem(v))
        self.props_table.blockSignals(False)

    def _current_selected_node(self) -> Optional[DTNode]:
        index = self.tree.currentIndex()
        if not index.isValid() or not self.root_node:
            return None
        path = index.data(self.PATH_ROLE)
        return self.root_node.find_by_path(path)

    def _add_property(self):
        node = self._current_selected_node()
        if not node:
            return
        key, ok = QInputDialog.getText(self, "Add Property", "Property name:")
        if not ok or not key:
            return
        if key in node.properties:
            QMessageBox.warning(self, "Add Property", "Property already exists.")
            return
        # Add with a sensible placeholder value (quoted empty string)
        node.properties[key] = '""'
        self._show_properties(node)

    def _delete_property(self):
        node = self._current_selected_node()
        if not node:
            return
        row = self.props_table.currentRow()
        if row < 0:
            return
        k_item = self.props_table.item(row, 0)
        if not k_item:
            return
        key = k_item.text()
        if key in node.properties:
            del node.properties[key]
        self._show_properties(node)
