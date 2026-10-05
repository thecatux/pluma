"""About dialog for Pluma."""

from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter

from pluma.ui import glass, icons, theme
from pluma.core.build_info import APP_NAME, APP_VERSION, BUILD_DATE, BUILD_NUMBER


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Acerca de Pluma")
        self.setModal(True)
        self.setFixedWidth(420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(14)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(12)
        self.app_icon = QLabel()
        self.app_icon.setFixedSize(36, 36)
        brand_row.addWidget(self.app_icon)

        brand_text = QVBoxLayout()
        brand_text.setSpacing(1)
        app_name = QLabel(APP_NAME)
        app_name.setStyleSheet("font-size: 19pt; font-weight: 700;")
        brand_text.addWidget(app_name)
        version = QLabel(APP_VERSION)
        version.setProperty("role", "muted")
        brand_text.addWidget(version)
        brand_row.addLayout(brand_text)
        brand_row.addStretch(1)
        layout.addLayout(brand_row)

        details = QVBoxLayout()
        details.setSpacing(8)
        self._add_detail(details, "Build", BUILD_NUMBER)
        self._add_detail(details, "Fecha de compilación", BUILD_DATE)
        layout.addLayout(details)

        tagline = QLabel("<i>Escribir es un arte</i>")
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline.setProperty("role", "hint")
        layout.addWidget(tagline)

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        close_button = QPushButton("Cerrar")
        close_button.setDefault(True)
        close_button.clicked.connect(self.accept)
        close_row.addWidget(close_button)
        layout.addLayout(close_row)

        self._refresh_icon()
        theme.signals.changed.connect(self._on_theme_changed)

    @staticmethod
    def _add_detail(layout, label_text, value_text):
        row = QHBoxLayout()
        label = QLabel(label_text)
        label.setProperty("role", "muted")
        value = QLabel(value_text)
        value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(label)
        row.addStretch(1)
        row.addWidget(value)
        layout.addLayout(row)

    def _refresh_icon(self):
        self.app_icon.setPixmap(icons.pixmap("pen", theme.colors()["primary_text"], size=36))

    def _on_theme_changed(self, *_args):
        self._refresh_icon()
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setClipRect(event.rect())
        glass.paint_backdrop(painter, self.rect())
        painter.end()