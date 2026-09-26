"""Panel "Esquema".

Traduce las señales de alto nivel de `OutlineCanvas` (crear forma,
mover, renombrar, recolorear, borrar, conectar) a operaciones sobre
`outline_shapes` / `outline_connections` en SQLite, y reconstruye el
lienzo con las formas y conexiones guardadas al abrir un proyecto.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

import theme
from outline_canvas import OutlineCanvas


class OutlinePanel(QWidget):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.project_id = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.hint = QLabel(
            "Elige una herramienta y haz clic en el lienzo para añadir una forma  ·  "
            "Arrastra para moverla, tira de la esquina para redimensionarla, doble clic para renombrarla  ·  "
            "Usa \"Conectar\" y haz clic en dos formas para unirlas con una flecha"
        )
        self.hint.setWordWrap(True)
        self.hint.setProperty("role", "hint")
        layout.addWidget(self.hint)

        self.canvas = OutlineCanvas(self)
        layout.addWidget(self.canvas)

        self._apply_theme()
        theme.signals.changed.connect(self._apply_theme)

        self.canvas.shapeCreated.connect(self._on_shape_created)
        self.canvas.shapeMoved.connect(self._on_shape_moved)
        self.canvas.shapeRenamed.connect(self._on_shape_renamed)
        self.canvas.shapeRecolored.connect(self._on_shape_recolored)
        self.canvas.shapeDeleted.connect(self._on_shape_deleted)
        self.canvas.connectionCreated.connect(self._on_connection_created)
        self.canvas.connectionDeleted.connect(self._on_connection_deleted)

    def _apply_theme(self, *_args):
        c = theme.colors()
        self.hint.setStyleSheet(
            f"padding: 8px 14px; background: {c['surface_alt']}; border-bottom: 1px solid {c['border']};"
        )
        self.canvas.apply_theme(c)

    def load_project(self, project_id: int):
        self.project_id = project_id
        self.canvas.clear_canvas()
        if project_id is None:
            return
        for shape in self.db.list_outline_shapes(project_id):
            self.canvas.add_shape_item(
                shape["id"], shape["shape_type"], shape["x"], shape["y"],
                shape["w"], shape["h"], shape["text"], shape["color"],
            )
        for conn in self.db.list_outline_connections(project_id):
            self.canvas.add_connection_item(conn["id"], conn["from_shape_id"], conn["to_shape_id"])

    # ------------------------------------------------------------------ #
    # Traducción de señales del lienzo -> SQLite
    # ------------------------------------------------------------------ #
    def _on_shape_created(self, shape_type, x, y):
        if self.project_id is None:
            return
        default_text = {"rect": "Idea", "ellipse": "Idea", "diamond": "Decisión", "note": "Nota"}[shape_type]
        shape_id = self.db.create_outline_shape(self.project_id, shape_type, x, y, text=default_text)
        row = self.db.get_outline_shape(shape_id)
        self.canvas.add_shape_item(row["id"], row["shape_type"], row["x"], row["y"],
                                    row["w"], row["h"], row["text"], row["color"])

    def _on_shape_moved(self, item):
        if item.shape_id is None:
            return
        pos = item.pos()
        rect = item.shape_rect()
        self.db.update_outline_shape(item.shape_id, x=pos.x(), y=pos.y(), w=rect.width(), h=rect.height())

    def _on_shape_renamed(self, item, text):
        if item.shape_id is None:
            return
        self.db.update_outline_shape(item.shape_id, text=text)

    def _on_shape_recolored(self, item, color_hex):
        if item.shape_id is None:
            return
        self.db.update_outline_shape(item.shape_id, color=color_hex)

    def _on_shape_deleted(self, item):
        if item.shape_id is not None:
            self.db.delete_outline_shape(item.shape_id)

    def _on_connection_created(self, from_item, to_item):
        if self.project_id is None or from_item.shape_id is None or to_item.shape_id is None:
            return
        connection_id = self.db.create_outline_connection(
            self.project_id, from_item.shape_id, to_item.shape_id)
        self.canvas.add_connection_item(connection_id, from_item.shape_id, to_item.shape_id)

    def _on_connection_deleted(self, conn):
        if conn.connection_id is not None:
            self.db.delete_outline_connection(conn.connection_id)