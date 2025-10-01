from typing import Optional
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont


class IconFactory:
    cache = {}

    @classmethod
    def make_icon(cls, label: str, color: QColor) -> QIcon:
        key = (label, color.name())
        if key in cls.cache:
            return cls.cache[key]
        pm = QPixmap(48, 48)
        pm.fill(QColor("white"))
        painter = QPainter(pm)
        painter.setBrush(color)
        painter.setPen(QColor("black"))
        painter.drawRoundedRect(2, 2, 44, 44, 6, 6)
        painter.setPen(QColor("white"))
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pm.rect(), 0x84, label)  # Qt.AlignCenter = 0x84
        painter.end()
        icon = QIcon(pm)
        cls.cache[key] = icon
        return icon


def node_icon(name: str, compatible: Optional[str]) -> QIcon:
    n = name.lower()
    comp = (compatible or "").lower()

    def has(sub: str) -> bool:
        return sub in n or sub in comp

    if has("cpu") or has("cortex"):
        return IconFactory.make_icon("CPU", QColor("#2d6cdf"))
    if has("mmc") or has("sdhci") or has("sdmmc"):
        return IconFactory.make_icon("SD", QColor("#7b61ff"))
    if has("i2c"):
        return IconFactory.make_icon("I2C", QColor("#07a0c3"))
    if has("spi"):
        return IconFactory.make_icon("SPI", QColor("#f39c12"))
    if has("uart") or has("serial"):
        return IconFactory.make_icon("UART", QColor("#e74c3c"))
    if has("gpio"):
        return IconFactory.make_icon("GPIO", QColor("#27ae60"))
    if has("dsi") or has("display") or has("hdmi") or has("edp") or has("rgb") or has("lvds"):
        return IconFactory.make_icon("DISP", QColor("#8e44ad"))
    if has("usb"):
        return IconFactory.make_icon("USB", QColor("#3498db"))
    if has("sata"):
        return IconFactory.make_icon("SATA", QColor("#16a085"))
    if has("ethernet") or has("gmac"):
        return IconFactory.make_icon("ETH", QColor("#0f766e"))
    if has("ddr") or has("ram") or has("memory"):
        return IconFactory.make_icon("RAM", QColor("#3b82f6"))
    if has("flash") or has("nor") or has("nand"):
        return IconFactory.make_icon("FLASH", QColor("#ef4444"))
    return IconFactory.make_icon("NODE", QColor("#6b7280"))
