from __future__ import annotations
import os
from typing import Optional

from PySide6.QtCore import Qt, QRectF, QPoint
from PySide6.QtGui import QAction, QStandardItemModel, QStandardItem, QBrush, QColor, QPen, QPainter
from PySide6.QtWidgets import (
    QMainWindow, QFileDialog, QMessageBox, QSplitter, QTreeView, QWidget, QVBoxLayout, QHBoxLayout,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QLabel, QFormLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QMenu, QInputDialog
)

from .parser import DTSParser
from .model import DTNode
from .icon_map import node_icon
from .serializer import serialize


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

        # UI
        self._make_menu()

        splitter = QSplitter(self)
        self.setCentralWidget(splitter)

        # Left tree
        self.tree = QTreeView()
        self.tree_model = QStandardItemModel()
        self.tree_model.setHorizontalHeaderLabels(["Node tree"])
        self.tree.setModel(self.tree_model)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._tree_context_menu)
        self.tree.clicked.connect(self._on_tree_clicked)
        splitter.addWidget(self.tree)

        # Center graph
        center = QWidget()
        center_layout = QVBoxLayout(center)
        # Zoom controls
        controls = QHBoxLayout()
        btn_zoom_in = QPushButton("+")
        btn_zoom_out = QPushButton("-")
        btn_fit = QPushButton("Fit")
        btn_zoom_in.setToolTip("Zoom In")
        btn_zoom_out.setToolTip("Zoom Out")
        btn_fit.setToolTip("Fit to View")
        controls.addWidget(btn_zoom_in)
        controls.addWidget(btn_zoom_out)
        controls.addWidget(btn_fit)
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
        node_items = {}
        for n, (x, y) in positions.items():
            item = NodeGraphicsItem(n)
            item.setPos(x, y)
            self.scene.addItem(item)
            node_items[n] = item

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
        action = menu.exec(self.tree.viewport().mapToGlobal(pos))
        if action == rename_act:
            self._rename_node(node, index)
        elif action == delete_act:
            self._delete_node(node, index)

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
