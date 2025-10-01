from __future__ import annotations
import os
from typing import Optional

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QAction, QStandardItemModel, QStandardItem, QBrush, QColor, QPen, QPainter
from PySide6.QtWidgets import (
    QMainWindow, QFileDialog, QMessageBox, QSplitter, QTreeView, QWidget, QVBoxLayout, QHBoxLayout,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QLabel, QFormLayout, QTableWidget, QTableWidgetItem,
    QPushButton
)

from .parser import DTSParser
from .model import DTNode
from .icon_map import node_icon


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

        # UI
        self._make_menu()

        splitter = QSplitter(self)
        self.setCentralWidget(splitter)

        # Left tree
        self.tree = QTreeView()
        self.tree_model = QStandardItemModel()
        self.tree_model.setHorizontalHeaderLabels(["Node tree"])
        self.tree.setModel(self.tree_model)
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
        right_layout.addWidget(self.props_table)
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

    def _open_dts(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open DTS file", os.getcwd(), "Device Tree (*.dts)")
        if path:
            self.load_file(path)

    def load_file(self, path: str):
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
            self.root_node = self.parser.parse(text)
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

    def _show_properties(self, node: DTNode):
        self.path_label.setText(f"Path: {node.path}")
        props = node.properties
        self.props_table.setRowCount(len(props))
        for r, (k, v) in enumerate(sorted(props.items())):
            self.props_table.setItem(r, 0, QTableWidgetItem(k))
            self.props_table.setItem(r, 1, QTableWidgetItem(v))
