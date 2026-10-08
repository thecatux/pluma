"""Diálogo "Acerca de" de Pluma.

Estructura (de arriba abajo):
  1. Cabecera: logotipo, nombre, versión y lema.
  2. Tarjeta "Versión": datos de compilación y del entorno de ejecución.
  3. Tarjeta "Licencia": aviso GPLv3, copyright y enlaces.
  4. Pie: copiar información (útil para informes de errores) y cerrar.
"""

from pathlib import Path
from platform import python_version

from PySide6 import __version__ as PYSIDE_VERSION
from PySide6.QtCore import QSize, QSysInfo, Qt, QTimer, QUrl, qVersion
from PySide6.QtGui import QDesktopServices, QGuiApplication, QPainter
from PySide6.QtWidgets import (
    QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QPlainTextEdit,
    QPushButton, QVBoxLayout,
)

from pluma.core.resources import asset_path
from pluma.core.build_info import (
    APP_AUTHOR, APP_COPYRIGHT_YEAR, APP_LICENSE_NAME, APP_LICENSE_URL,
    APP_NAME, APP_SOURCE_URL, APP_VERSION, BUILD_DATE, BUILD_NUMBER,
)
from pluma.ui import icons, theme

TAGLINE = "Escribir es un arte"

# Aviso estándar de la GPLv3 (sección "How to Apply These Terms"),
# redactado en español. Si se quiere permitir también versiones
# posteriores, añadir "o (a su elección) cualquier versión posterior".
LICENSE_NOTICE = (
    f"{APP_NAME} es software libre: puede redistribuirlo y/o modificarlo "
    "bajo los términos de la Licencia Pública General de GNU, versión 3, "
    "publicada por la Free Software Foundation.\n\n"
    f"{APP_NAME} se distribuye con la esperanza de que sea útil, pero SIN "
    "NINGUNA GARANTÍA; ni siquiera la garantía implícita de "
    "COMERCIALIZACIÓN o IDONEIDAD PARA UN PROPÓSITO PARTICULAR. Consulte "
    "la Licencia Pública General de GNU para más detalles."
)

LICENSE_FILE = "LICENSE.txt"  # texto completo, incluido en los assets


def _build_rows():
    return [
        ("Build", BUILD_NUMBER),
        ("Fecha de compilación", BUILD_DATE),
    ]


def _runtime_rows():
    return [
        ("Sistema", QSysInfo.prettyProductName()),
        ("Python", python_version()),
        ("Qt / PySide6", f"{qVersion()} / {PYSIDE_VERSION}"),
    ]


def _copyright_line():
    if not APP_AUTHOR:
        return ""
    return f"© {APP_COPYRIGHT_YEAR} {APP_AUTHOR}"


class LicenseTextDialog(QDialog):
    """Visor de solo lectura del texto completo de la licencia."""

    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.setWindowTitle(APP_LICENSE_NAME)
        self.setModal(True)
        self.resize(660, 540)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)

        viewer = QPlainTextEdit(text)
        viewer.setReadOnly(True)
        viewer.setStyleSheet(
            "font-family: Consolas, 'Cascadia Mono', 'Courier New', monospace;"
            "font-size: 9.5pt;"
        )
        layout.addWidget(viewer, 1)

        row = QHBoxLayout()
        row.addStretch(1)
        close_button = QPushButton("Cerrar")
        close_button.setProperty("variant", "primary")
        close_button.setDefault(True)
        close_button.clicked.connect(self.accept)
        row.addWidget(close_button)
        layout.addLayout(row)


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Acerca de {APP_NAME}")
        self.setModal(True)
        self.setFixedWidth(500)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 26, 28, 20)
        root.setSpacing(16)

        root.addLayout(self._build_header())
        root.addWidget(self._build_version_card())
        root.addWidget(self._build_license_card())
        root.addLayout(self._build_footer())
        # Con QLabel(wordWrap) dentro de un diálogo de ancho fijo, Qt puede
        # calcular la altura con otra anchura y recortar el texto: se fija
        # la altura exacta para la anchura real.
        self.setFixedHeight(root.totalHeightForWidth(self.width()))

        self._copy_timer = QTimer(self)
        self._copy_timer.setSingleShot(True)
        self._copy_timer.timeout.connect(self._reset_copy_button)

        self._refresh_icons()
        theme.signals.changed.connect(self._on_theme_changed)

    # ------------------------------------------------------------------ #
    # Construcción
    # ------------------------------------------------------------------ #
    def _build_header(self):
        row = QHBoxLayout()
        row.setSpacing(16)

        self.app_icon = QLabel()
        self.app_icon.setFixedSize(56, 56)
        row.addWidget(self.app_icon, 0, Qt.AlignmentFlag.AlignTop)

        text = QVBoxLayout()
        text.setSpacing(2)
        name = QLabel(APP_NAME)
        name.setStyleSheet("font-size: 22pt; font-weight: 700;")
        text.addWidget(name)

        version = QLabel(f"Versión {APP_VERSION}")
        version.setProperty("role", "muted")
        text.addWidget(version)

        tagline = QLabel(f"<i>{TAGLINE}</i>")
        tagline.setProperty("role", "hint")
        text.addWidget(tagline)

        row.addLayout(text, 1)
        return row

    @staticmethod
    def _card(title):
        card = QFrame()
        card.setProperty("role", "card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 16)
        layout.setSpacing(8)
        heading = QLabel(title)
        heading.setProperty("role", "section-title")
        layout.addWidget(heading)
        return card, layout

    @staticmethod
    def _rows_grid(rows):
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(7)
        grid.setColumnStretch(1, 1)
        for index, (label_text, value_text) in enumerate(rows):
            label = QLabel(label_text)
            label.setProperty("role", "muted")
            value = QLabel(value_text)
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            grid.addWidget(label, index, 0)
            grid.addWidget(value, index, 1)
        return grid

    def _build_version_card(self):
        card, layout = self._card("Versión")
        layout.addLayout(self._rows_grid(_build_rows()))

        divider = QFrame()
        divider.setProperty("role", "divider")
        divider.setFixedHeight(1)
        layout.addWidget(divider)

        layout.addLayout(self._rows_grid(_runtime_rows()))
        return card

    def _build_license_card(self):
        card, layout = self._card("Licencia")

        license_name = QLabel(APP_LICENSE_NAME)
        license_name.setStyleSheet("font-weight: 600;")
        layout.addWidget(license_name)

        copyright_text = _copyright_line()
        if copyright_text:
            copyright_label = QLabel(copyright_text)
            copyright_label.setProperty("role", "muted")
            layout.addWidget(copyright_label)

        notice = QLabel(LICENSE_NOTICE)
        notice.setWordWrap(True)
        notice.setProperty("role", "hint")
        notice.setStyleSheet("font-size: 9.5pt;")
        notice.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(notice)

        links = QHBoxLayout()
        links.setSpacing(4)
        full_license = QPushButton("Leer la licencia completa")
        full_license.setProperty("variant", "flat")
        full_license.setCursor(Qt.CursorShape.PointingHandCursor)
        full_license.clicked.connect(self._show_full_license)
        links.addWidget(full_license)

        if APP_SOURCE_URL:
            source = QPushButton("Código fuente")
            source.setProperty("variant", "flat")
            source.setCursor(Qt.CursorShape.PointingHandCursor)
            source.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(APP_SOURCE_URL)))
            links.addWidget(source)
        links.addStretch(1)
        layout.addLayout(links)
        return card

    def _build_footer(self):
        row = QHBoxLayout()
        self.copy_button = QPushButton("Copiar información")
        self.copy_button.setProperty("variant", "flat")
        self.copy_button.setToolTip("Copia versión, build y entorno para adjuntarlos a un informe de error")
        self.copy_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_button.setIconSize(QSize(16, 16))
        self.copy_button.clicked.connect(self._copy_info)
        row.addWidget(self.copy_button)
        row.addStretch(1)

        close_button = QPushButton("Cerrar")
        close_button.setProperty("variant", "primary")
        close_button.setDefault(True)
        close_button.clicked.connect(self.accept)
        row.addWidget(close_button)
        return row

    # ------------------------------------------------------------------ #
    # Acciones
    # ------------------------------------------------------------------ #
    def _info_text(self):
        lines = [f"{APP_NAME} {APP_VERSION}"]
        lines += [f"{label}: {value}" for label, value in _build_rows() + _runtime_rows()]
        return "\n".join(lines)

    def _copy_info(self):
        QGuiApplication.clipboard().setText(self._info_text())
        self._copied = True
        self.copy_button.setText("Copiado")
        self._refresh_icons()
        self._copy_timer.start(1800)

    def _reset_copy_button(self):
        self._copied = False
        self.copy_button.setText("Copiar información")
        self._refresh_icons()

    def _show_full_license(self):
        try:
            path = Path(asset_path(LICENSE_FILE))
        except FileNotFoundError:
            QDesktopServices.openUrl(QUrl(APP_LICENSE_URL))
            return
        if path.is_file():
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                text = ""
            if text:
                LicenseTextDialog(text, self).exec()
                return
        # Sin copia local del texto: se abre la versión oficial.
        QDesktopServices.openUrl(QUrl(APP_LICENSE_URL))

    # ------------------------------------------------------------------ #
    # Tema
    # ------------------------------------------------------------------ #
    _copied = False

    def _refresh_icons(self):
        self.app_icon.setPixmap(icons.brand_pixmap(56))
        colors = theme.colors()
        if self._copied:
            self.copy_button.setIcon(icons.icon("check", colors["success"], 16))
        else:
            self.copy_button.setIcon(icons.icon("copy", colors["text_secondary"], 16))

    def _on_theme_changed(self, *_args):
        self._refresh_icons()
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setClipRect(event.rect())
        theme.paint_backdrop(painter, self.rect())
        painter.end()