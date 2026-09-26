"""Panel "Línea temporal".

Traduce las señales de alto nivel de `TimelineCanvas` (crear, editar,
eliminar, reordenar) a operaciones sobre `timeline_blocks` en SQLite,
y reconstruye el lienzo con los bloques guardados al abrir un
proyecto.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QMessageBox

import theme
from outline_canvas import TimelineCanvas
from app_settings import settings


class OutlinePanel(QWidget):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.project_id = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.hint = QLabel(
            "Cada bloque es un evento de tu historia  ·  "
            "Ponle un grupo (capítulo, escena o lo que prefieras) para colorearlo y filtrarlo  ·  "
            "Arrastra un bloque para reordenarlo en la línea"
        )
        self.hint.setWordWrap(True)
        self.hint.setProperty("role", "hint")
        layout.addWidget(self.hint)

        self.canvas = TimelineCanvas(self)
        layout.addWidget(self.canvas, 1)

        self._apply_theme()
        theme.signals.changed.connect(self._apply_theme)

        self.canvas.addRequested.connect(self._on_add_requested)
        self.canvas.blockChanged.connect(self._on_block_changed)
        self.canvas.blockDeleteRequested.connect(self._on_block_delete_requested)
        self.canvas.blocksReordered.connect(self._on_blocks_reordered)

    def _apply_theme(self, *_args):
        c = theme.colors()
        self.hint.setStyleSheet(
            f"padding: 8px 14px; background: {c['surface_alt']}; border-bottom: 1px solid {c['border']};"
        )

    def load_project(self, project_id: int):
        self.project_id = project_id
        self._reload()

    def _reload(self):
        rows = self.db.list_timeline_blocks(self.project_id) if self.project_id else []
        self.canvas.set_blocks(rows)

    # ------------------------------------------------------------------ #
    # Traducción de señales del lienzo -> SQLite
    # ------------------------------------------------------------------ #
    def _on_add_requested(self):
        if self.project_id is None:
            return
        self.db.create_timeline_block(self.project_id)
        self._reload()

    def _on_block_changed(self, block_id, fields):
        self.db.update_timeline_block(block_id, **fields)

    def _on_block_delete_requested(self, block_id):
        if settings.confirm_before_delete:
            ret = QMessageBox.question(
                self, "Eliminar evento",
                "¿Seguro que quieres eliminar este evento de la línea temporal?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if ret != QMessageBox.Yes:
                return
        self.db.delete_timeline_block(block_id)
        self._reload()

    def _on_blocks_reordered(self, ordered_ids):
        self.db.reorder_timeline_blocks(self.project_id, ordered_ids)

    def _flush_pending_save(self):
        self.canvas.flush_pending_saves()