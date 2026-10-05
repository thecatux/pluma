"""Panel "Línea temporal".

Traduce las señales de alto nivel de `TimelineCanvas` (crear, editar,
eliminar, duplicar, reordenar) a operaciones sobre `timeline_blocks` en
SQLite, y reconstruye el lienzo con los bloques guardados al abrir un
proyecto.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QMessageBox

from pluma.core.app_settings import settings
from pluma.ui import theme
from pluma.ui.outline_canvas import TimelineCanvas


class OutlinePanel(QWidget):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.project_id = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.hint = QLabel(
            "Doble clic en el lienzo o «+» entre nodos para añadir eventos  ·  "
            "Arrastra un evento para reordenarlo (en carriles, a otro carril para cambiar de grupo)  ·  "
            "Ctrl + rueda para zoom, arrastra el fondo para desplazarte  ·  Clic derecho para más opciones"
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
        self.canvas.blockDuplicateRequested.connect(self._on_block_duplicate_requested)
        self.canvas.blocksReordered.connect(self._on_blocks_reordered)

    def _apply_theme(self, *_args):
        c = theme.colors()
        self.hint.setStyleSheet(
            f"padding: 8px 14px; background: {c['glass_subtle']}; border-bottom: 1px solid {c['glass_border']};"
        )

    def load_project(self, project_id: int):
        self.project_id = project_id
        self._reload(reset_view=True)

    def refresh(self):
        self._reload()

    def _reload(self, reset_view=False, select_id=None, focus_title=False):
        self.canvas.flush_pending_saves()
        if self.project_id:
            rows = self.db.list_timeline_blocks(self.project_id)
            chapters = [(r["id"], r["title"]) for r in self.db.list_chapters(self.project_id)]
        else:
            rows, chapters = [], []
        self.canvas.set_blocks(rows, chapters, reset_view=reset_view)
        if select_id is not None:
            self.canvas.select_block(select_id, center=True, focus_title=focus_title)

    # ------------------------------------------------------------------ #
    # Traducción de señales del lienzo -> SQLite
    # ------------------------------------------------------------------ #
    def _on_add_requested(self, index: int, group: str):
        if self.project_id is None:
            return
        self.canvas.flush_pending_saves()
        new_id = self.db.create_timeline_block(self.project_id)
        if group:
            self.db.update_timeline_block(new_id, group_name=group)
        existing = [r["id"] for r in self.db.list_timeline_blocks(self.project_id) if r["id"] != new_id]
        if 0 <= index < len(existing):
            existing.insert(index, new_id)
            self.db.reorder_timeline_blocks(self.project_id, existing)
        self._reload(select_id=new_id, focus_title=True)

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
        self.canvas.flush_pending_saves()
        self.db.delete_timeline_block(block_id)
        self._reload()

    def _on_block_duplicate_requested(self, block_id):
        new_id = self.db.duplicate_timeline_block(block_id)
        self._reload(select_id=new_id)

    def _on_blocks_reordered(self, ordered_ids):
        self.db.reorder_timeline_blocks(self.project_id, ordered_ids)

    def _flush_pending_save(self):
        self.canvas.flush_pending_saves()