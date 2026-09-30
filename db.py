"""Capa de persistencia de Pluma.

Toda la aplicación guarda su estado en una única base de datos SQLite
ubicada en <directorio del programa>/data/pluma.db (configurable vía
la variable de entorno PLUMA_DB_PATH, útil para pruebas). La base de
datos aloja varios "proyectos" (novelas); todas las tablas de
contenido cuelgan de `project_id` con borrado en cascada, de modo que
eliminar un proyecto limpia automáticamente sus capítulos, personajes,
escenas, notas y esquema.

Esta clase no depende de Qt: es pura lógica de acceso a datos, lo que
permite probarla o reutilizarla sin levantar una interfaz gráfica.
"""

import json
import os
import sqlite3
import time
from contextlib import contextmanager
from typing import Any, Optional

# Directorio del propio programa (donde vive este archivo), no el
# directorio de trabajo desde el que se lance Pluma. Así "/data" queda
# siempre junto al ejecutable/código fuente, sea cual sea el sistema
# operativo o desde dónde se inicie la aplicación.
_PROGRAM_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB_PATH = os.environ.get("PLUMA_DB_PATH", os.path.join(_PROGRAM_DIR, "data", "pluma.db"))

# Campos habituales de una ficha de personaje. El usuario puede añadir
# más libremente; estos solo sirven como plantilla inicial al crear un
# personaje nuevo.
DEFAULT_CHARACTER_FIELDS = [
    "Nombre completo",
    "Apodo",
    "Edad",
    "Género",
    "Ocupación",
    "Apariencia física",
    "Personalidad",
    "Motivación / objetivo",
    "Conflicto interno",
    "Relaciones",
    "Historia / trasfondo",
    "Notas",
]

# Aspectos habituales de una escena, con mayor libertad que el personaje:
# solo se usan como punto de partida sugerido.
DEFAULT_SCENE_FIELDS = [
    "Lugar",
    "Momento / tiempo",
    "Personajes presentes",
    "Objetivo de la escena",
    "Conflicto / tensión",
    "Resumen",
]

# Lista cerrada de géneros para la ficha de datos generales de la
# novela. Se ofrece como desplegable (en vez de texto libre) para que
# rellenarla sea tan rápido como seleccionar una opción.
DEFAULT_GENRES = [
    "Ficción literaria",
    "Fantasía",
    "Ciencia ficción",
    "Romance",
    "Misterio",
    "Thriller / Suspense",
    "Terror",
    "Aventura",
    "Histórica",
    "Drama",
    "Distopía",
    "Juvenil (YA)",
    "Infantil",
    "Poesía",
    "Biografía / memorias",
    "Ensayo / no ficción",
    "Otro",
]


class Database:
    def __init__(self, path: str = DEFAULT_DB_PATH):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        # WAL permite que las lecturas (listar capítulos, etc.) no se
        # bloqueen con las escrituras del autoguardado, y "synchronous =
        # NORMAL" es seguro con WAL y bastante más rápido que el modo
        # FULL por defecto para las escrituras frecuentes y pequeñas que
        # hace Pluma constantemente.
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA synchronous = NORMAL")
        self._init_schema()

    def close(self):
        self._conn.close()

    def backup_to(self, dest_path: str):
        """Copia íntegra y consistente de la base de datos a `dest_path`,
        usando la API de backup de SQLite (segura de usar con la app
        abierta y con WAL activo, a diferencia de copiar el fichero a
        mano con el sistema de archivos)."""
        os.makedirs(os.path.dirname(os.path.abspath(dest_path)) or ".", exist_ok=True)
        dest = sqlite3.connect(dest_path)
        try:
            with dest:
                self._conn.backup(dest)
        finally:
            dest.close()

    # ------------------------------------------------------------------ #
    # Esquema
    # ------------------------------------------------------------------ #
    def _init_schema(self):
        with self._tx() as cur:
            cur.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    last_opened_at TEXT,
                    title TEXT NOT NULL DEFAULT '',
                    author TEXT NOT NULL DEFAULT '',
                    genre TEXT NOT NULL DEFAULT '',
                    synopsis TEXT NOT NULL DEFAULT '',
                    page_count INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS chapters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    title TEXT NOT NULL DEFAULT 'Nuevo capítulo',
                    content TEXT NOT NULL DEFAULT '',
                    synopsis TEXT NOT NULL DEFAULT '',
                    order_index INTEGER NOT NULL DEFAULT 0,
                    word_count INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS characters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    name TEXT NOT NULL DEFAULT 'Nuevo personaje',
                    order_index INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS character_fields (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
                    field_name TEXT NOT NULL,
                    field_value TEXT NOT NULL DEFAULT '',
                    order_index INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS scenes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    title TEXT NOT NULL DEFAULT 'Nueva escena',
                    order_index INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS scene_fields (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scene_id INTEGER NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
                    field_name TEXT NOT NULL,
                    field_value TEXT NOT NULL DEFAULT '',
                    order_index INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS scene_chapter_links (
                    scene_id INTEGER NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
                    chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
                    PRIMARY KEY (scene_id, chapter_id)
                );

                CREATE TABLE IF NOT EXISTS timeline_blocks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    title TEXT NOT NULL DEFAULT 'Nuevo evento',
                    date_label TEXT NOT NULL DEFAULT '',
                    group_name TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    order_index INTEGER NOT NULL DEFAULT 0,
                    color TEXT NOT NULL DEFAULT '',
                    is_milestone INTEGER NOT NULL DEFAULT 0,
                    chapter_id INTEGER REFERENCES chapters(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    title TEXT NOT NULL DEFAULT 'Nueva nota',
                    content TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT '',
                    order_index INTEGER NOT NULL DEFAULT 0
                );

                -- Índices sobre las columnas por las que se filtra en
                -- cada pantalla (siempre project_id, más el padre en las
                -- tablas de campos/enlaces). Sin ellos, cada listado
                -- recorre la tabla entera; con proyectos grandes esto es
                -- la diferencia entre una consulta instantánea y una
                -- perceptible al cambiar de sección o de elemento.
                CREATE INDEX IF NOT EXISTS idx_chapters_project ON chapters(project_id, order_index);
                CREATE INDEX IF NOT EXISTS idx_characters_project ON characters(project_id, order_index);
                CREATE INDEX IF NOT EXISTS idx_character_fields_character ON character_fields(character_id, order_index);
                CREATE INDEX IF NOT EXISTS idx_scenes_project ON scenes(project_id, order_index);
                CREATE INDEX IF NOT EXISTS idx_scene_fields_scene ON scene_fields(scene_id, order_index);
                CREATE INDEX IF NOT EXISTS idx_scene_links_scene ON scene_chapter_links(scene_id);
                CREATE INDEX IF NOT EXISTS idx_scene_links_chapter ON scene_chapter_links(chapter_id);
                CREATE INDEX IF NOT EXISTS idx_timeline_blocks_project ON timeline_blocks(project_id, order_index);
                CREATE INDEX IF NOT EXISTS idx_notes_project ON notes(project_id, order_index);
                """
            )
        self._migrate_project_info_columns()
        self._migrate_chapter_word_count()
        self._migrate_timeline_columns()

    def _migrate_project_info_columns(self):
        """Añade a `projects` las columnas de la ficha de la novela si la
        base de datos es de una versión anterior a esta función (las
        bases de datos nuevas ya las traen en el CREATE TABLE). También
        rellena `title` con el nombre del proyecto en los proyectos que
        aún no tengan uno, para que el título de la novela nazca con el
        mismo valor que el proyecto.
        """
        with self._tx() as cur:
            cur.execute("PRAGMA table_info(projects)")
            existing_columns = {row[1] for row in cur.fetchall()}
            missing_columns = {
                "title": "TEXT NOT NULL DEFAULT ''",
                "author": "TEXT NOT NULL DEFAULT ''",
                "genre": "TEXT NOT NULL DEFAULT ''",
                "synopsis": "TEXT NOT NULL DEFAULT ''",
                "page_count": "INTEGER NOT NULL DEFAULT 0",
            }
            for column, ddl in missing_columns.items():
                if column not in existing_columns:
                    cur.execute(f"ALTER TABLE projects ADD COLUMN {column} {ddl}")
            cur.execute("UPDATE projects SET title = name WHERE title = ''")

    def _migrate_chapter_word_count(self):
        """Añade `word_count` a `chapters` si la base de datos es de una
        versión anterior. No recalcula el HTML aquí (sería lento y
        depende de Qt, que esta capa deliberadamente no importa); se
        recalcula la primera vez que cada capítulo se guarda o se abre
        desde la interfaz."""
        with self._tx() as cur:
            cur.execute("PRAGMA table_info(chapters)")
            existing_columns = {row[1] for row in cur.fetchall()}
            if "word_count" not in existing_columns:
                cur.execute("ALTER TABLE chapters ADD COLUMN word_count INTEGER NOT NULL DEFAULT 0")

    def _migrate_timeline_columns(self):
        """Añade a `timeline_blocks` las columnas del lienzo (color
        manual, hito y capítulo vinculado) si la base de datos es de una
        versión anterior. Si se borra el capítulo vinculado, el bloque
        se conserva y `chapter_id` pasa a NULL."""
        with self._tx() as cur:
            cur.execute("PRAGMA table_info(timeline_blocks)")
            existing_columns = {row[1] for row in cur.fetchall()}
            missing_columns = {
                "color": "TEXT NOT NULL DEFAULT ''",
                "is_milestone": "INTEGER NOT NULL DEFAULT 0",
                "chapter_id": "INTEGER REFERENCES chapters(id) ON DELETE SET NULL",
            }
            for column, ddl in missing_columns.items():
                if column not in existing_columns:
                    cur.execute(f"ALTER TABLE timeline_blocks ADD COLUMN {column} {ddl}")

    @contextmanager
    def _tx(self):
        cur = self._conn.cursor()
        try:
            yield cur
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    @staticmethod
    def _now() -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S")

    # ------------------------------------------------------------------ #
    # Proyectos
    # ------------------------------------------------------------------ #
    def list_projects(self) -> list[sqlite3.Row]:
        cur = self._conn.execute(
            "SELECT * FROM projects ORDER BY COALESCE(last_opened_at, created_at) DESC"
        )
        return cur.fetchall()

    def create_project(self, name: str) -> int:
        name = name.strip()
        if not name:
            raise ValueError("El nombre del proyecto no puede estar vacío.")
        with self._tx() as cur:
            cur.execute(
                "INSERT INTO projects (name, title, created_at, last_opened_at) VALUES (?, ?, ?, ?)",
                (name, name, self._now(), self._now()),
            )
            return cur.lastrowid

    def rename_project(self, project_id: int, new_name: str):
        new_name = new_name.strip()
        if not new_name:
            raise ValueError("El nombre del proyecto no puede estar vacío.")
        with self._tx() as cur:
            cur.execute("UPDATE projects SET name = ? WHERE id = ?", (new_name, project_id))

    def touch_project(self, project_id: int):
        with self._tx() as cur:
            cur.execute(
                "UPDATE projects SET last_opened_at = ? WHERE id = ?", (self._now(), project_id)
            )

    def delete_project(self, project_id: int):
        with self._tx() as cur:
            cur.execute("DELETE FROM projects WHERE id = ?", (project_id,))

    def get_project(self, project_id: int) -> Optional[sqlite3.Row]:
        cur = self._conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
        return cur.fetchone()

    def project_exists(self, project_id: int) -> bool:
        cur = self._conn.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,))
        return cur.fetchone() is not None

    # ------------------------------------------------------------------ #
    # Datos generales de la novela (ficha del proyecto)
    # ------------------------------------------------------------------ #
    def get_project_info(self, project_id: int) -> Optional[sqlite3.Row]:
        cur = self._conn.execute(
            "SELECT id, name, title, author, genre, synopsis, page_count "
            "FROM projects WHERE id = ?",
            (project_id,),
        )
        return cur.fetchone()

    def update_project_info(self, project_id: int, **fields):
        self._update_row("projects", project_id, fields)

    # ------------------------------------------------------------------ #
    # Capítulos
    # ------------------------------------------------------------------ #
    def list_chapters(self, project_id: int) -> list[sqlite3.Row]:
        cur = self._conn.execute(
            "SELECT * FROM chapters WHERE project_id = ? ORDER BY order_index, id",
            (project_id,),
        )
        return cur.fetchall()

    def get_chapter(self, chapter_id: int) -> Optional[sqlite3.Row]:
        cur = self._conn.execute("SELECT * FROM chapters WHERE id = ?", (chapter_id,))
        return cur.fetchone()

    def count_chapters(self, project_id: int) -> int:
        cur = self._conn.execute("SELECT COUNT(*) FROM chapters WHERE project_id = ?", (project_id,))
        return cur.fetchone()[0]

    def total_word_count(self, project_id: int) -> int:
        """Suma agregada en SQL a partir del `word_count` cacheado de cada
        capítulo, en vez de traer todo el contenido y reparsear el HTML
        de cada capítulo en la interfaz."""
        cur = self._conn.execute(
            "SELECT COALESCE(SUM(word_count), 0) FROM chapters WHERE project_id = ?", (project_id,)
        )
        return cur.fetchone()[0]

    def create_chapter(self, project_id: int, title: str = "Nuevo capítulo") -> int:
        with self._tx() as cur:
            cur.execute(
                "SELECT COALESCE(MAX(order_index), -1) + 1 FROM chapters WHERE project_id = ?",
                (project_id,),
            )
            next_order = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO chapters (project_id, title, content, order_index) VALUES (?, ?, '', ?)",
                (project_id, title, next_order),
            )
            return cur.lastrowid

    def update_chapter(self, chapter_id: int, **fields):
        self._update_row("chapters", chapter_id, fields)

    def delete_chapter(self, chapter_id: int):
        with self._tx() as cur:
            cur.execute("DELETE FROM chapters WHERE id = ?", (chapter_id,))

    def reorder_chapters(self, ordered_ids: list[int]):
        """Recibe la lista completa de ids de capítulos en el nuevo orden
        deseado y reescribe `order_index` en consecuencia."""
        with self._tx() as cur:
            for index, chapter_id in enumerate(ordered_ids):
                cur.execute(
                    "UPDATE chapters SET order_index = ? WHERE id = ?", (index, chapter_id)
                )

    # ------------------------------------------------------------------ #
    # Personajes (ficha con campos flexibles clave/valor)
    # ------------------------------------------------------------------ #
    def list_characters(self, project_id: int) -> list[sqlite3.Row]:
        cur = self._conn.execute(
            "SELECT * FROM characters WHERE project_id = ? ORDER BY order_index, id",
            (project_id,),
        )
        return cur.fetchall()

    def get_character(self, character_id: int) -> Optional[sqlite3.Row]:
        cur = self._conn.execute("SELECT * FROM characters WHERE id = ?", (character_id,))
        return cur.fetchone()

    def create_character(self, project_id: int, name: str = "Nuevo personaje") -> int:
        with self._tx() as cur:
            cur.execute(
                "SELECT COALESCE(MAX(order_index), -1) + 1 FROM characters WHERE project_id = ?",
                (project_id,),
            )
            next_order = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO characters (project_id, name, order_index) VALUES (?, ?, ?)",
                (project_id, name, next_order),
            )
            character_id = cur.lastrowid
            for i, field_name in enumerate(DEFAULT_CHARACTER_FIELDS):
                cur.execute(
                    "INSERT INTO character_fields (character_id, field_name, field_value, order_index) "
                    "VALUES (?, ?, '', ?)",
                    (character_id, field_name, i),
                )
            return character_id

    def update_character(self, character_id: int, **fields):
        self._update_row("characters", character_id, fields)

    def delete_character(self, character_id: int):
        with self._tx() as cur:
            cur.execute("DELETE FROM characters WHERE id = ?", (character_id,))

    def list_character_fields(self, character_id: int) -> list[sqlite3.Row]:
        cur = self._conn.execute(
            "SELECT * FROM character_fields WHERE character_id = ? ORDER BY order_index, id",
            (character_id,),
        )
        return cur.fetchall()

    def add_character_field(self, character_id: int, field_name: str, field_value: str = "") -> int:
        with self._tx() as cur:
            cur.execute(
                "SELECT COALESCE(MAX(order_index), -1) + 1 FROM character_fields WHERE character_id = ?",
                (character_id,),
            )
            next_order = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO character_fields (character_id, field_name, field_value, order_index) "
                "VALUES (?, ?, ?, ?)",
                (character_id, field_name, field_value, next_order),
            )
            return cur.lastrowid

    def update_character_field(self, field_id: int, **fields):
        self._update_row("character_fields", field_id, fields)

    def delete_character_field(self, field_id: int):
        with self._tx() as cur:
            cur.execute("DELETE FROM character_fields WHERE id = ?", (field_id,))

    # ------------------------------------------------------------------ #
    # Escenas (ficha flexible + enlace con capítulos)
    # ------------------------------------------------------------------ #
    def list_scenes(self, project_id: int) -> list[sqlite3.Row]:
        cur = self._conn.execute(
            "SELECT * FROM scenes WHERE project_id = ? ORDER BY order_index, id",
            (project_id,),
        )
        return cur.fetchall()

    def get_scene(self, scene_id: int) -> Optional[sqlite3.Row]:
        cur = self._conn.execute("SELECT * FROM scenes WHERE id = ?", (scene_id,))
        return cur.fetchone()

    def create_scene(self, project_id: int, title: str = "Nueva escena") -> int:
        with self._tx() as cur:
            cur.execute(
                "SELECT COALESCE(MAX(order_index), -1) + 1 FROM scenes WHERE project_id = ?",
                (project_id,),
            )
            next_order = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO scenes (project_id, title, order_index) VALUES (?, ?, ?)",
                (project_id, title, next_order),
            )
            scene_id = cur.lastrowid
            for i, field_name in enumerate(DEFAULT_SCENE_FIELDS):
                cur.execute(
                    "INSERT INTO scene_fields (scene_id, field_name, field_value, order_index) "
                    "VALUES (?, ?, '', ?)",
                    (scene_id, field_name, i),
                )
            return scene_id

    def update_scene(self, scene_id: int, **fields):
        self._update_row("scenes", scene_id, fields)

    def delete_scene(self, scene_id: int):
        with self._tx() as cur:
            cur.execute("DELETE FROM scenes WHERE id = ?", (scene_id,))

    def list_scene_fields(self, scene_id: int) -> list[sqlite3.Row]:
        cur = self._conn.execute(
            "SELECT * FROM scene_fields WHERE scene_id = ? ORDER BY order_index, id",
            (scene_id,),
        )
        return cur.fetchall()

    def add_scene_field(self, scene_id: int, field_name: str, field_value: str = "") -> int:
        with self._tx() as cur:
            cur.execute(
                "SELECT COALESCE(MAX(order_index), -1) + 1 FROM scene_fields WHERE scene_id = ?",
                (scene_id,),
            )
            next_order = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO scene_fields (scene_id, field_name, field_value, order_index) VALUES (?, ?, ?, ?)",
                (scene_id, field_name, field_value, next_order),
            )
            return cur.lastrowid

    def update_scene_field(self, field_id: int, **fields):
        self._update_row("scene_fields", field_id, fields)

    def delete_scene_field(self, field_id: int):
        with self._tx() as cur:
            cur.execute("DELETE FROM scene_fields WHERE id = ?", (field_id,))

    def get_scene_chapter_links(self, scene_id: int) -> list[int]:
        cur = self._conn.execute(
            "SELECT chapter_id FROM scene_chapter_links WHERE scene_id = ?", (scene_id,)
        )
        return [row[0] for row in cur.fetchall()]

    def set_scene_chapter_links(self, scene_id: int, chapter_ids: list[int]):
        with self._tx() as cur:
            cur.execute("DELETE FROM scene_chapter_links WHERE scene_id = ?", (scene_id,))
            for chapter_id in chapter_ids:
                cur.execute(
                    "INSERT OR IGNORE INTO scene_chapter_links (scene_id, chapter_id) VALUES (?, ?)",
                    (scene_id, chapter_id),
                )

    # ------------------------------------------------------------------ #
    # Esquema (línea temporal: bloques ordenables y agrupables)
    # ------------------------------------------------------------------ #
    def list_timeline_blocks(self, project_id: int) -> list[sqlite3.Row]:
        cur = self._conn.execute(
            "SELECT * FROM timeline_blocks WHERE project_id = ? ORDER BY order_index, id",
            (project_id,),
        )
        return cur.fetchall()

    def create_timeline_block(self, project_id: int, title: str = "Nuevo evento") -> int:
        with self._tx() as cur:
            cur.execute(
                "SELECT COALESCE(MAX(order_index), -1) + 1 FROM timeline_blocks WHERE project_id = ?",
                (project_id,),
            )
            next_order = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO timeline_blocks (project_id, title, order_index) VALUES (?, ?, ?)",
                (project_id, title, next_order),
            )
            return cur.lastrowid

    def update_timeline_block(self, block_id: int, **fields):
        self._update_row("timeline_blocks", block_id, fields)

    def duplicate_timeline_block(self, block_id: int) -> Optional[int]:
        """Copia un bloque justo detrás del original y devuelve el id de la copia."""
        with self._tx() as cur:
            cur.execute("SELECT * FROM timeline_blocks WHERE id = ?", (block_id,))
            row = cur.fetchone()
            if row is None:
                return None
            cur.execute(
                "UPDATE timeline_blocks SET order_index = order_index + 1 "
                "WHERE project_id = ? AND order_index > ?",
                (row["project_id"], row["order_index"]),
            )
            cur.execute(
                "INSERT INTO timeline_blocks (project_id, title, date_label, group_name, description, "
                "order_index, color, is_milestone, chapter_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (row["project_id"], f"{row['title']} (copia)", row["date_label"], row["group_name"],
                 row["description"], row["order_index"] + 1, row["color"], row["is_milestone"],
                 row["chapter_id"]),
            )
            return cur.lastrowid

    def delete_timeline_block(self, block_id: int):
        with self._tx() as cur:
            cur.execute("DELETE FROM timeline_blocks WHERE id = ?", (block_id,))

    def reorder_timeline_blocks(self, project_id: int, ordered_ids: list[int]):
        with self._tx() as cur:
            for index, block_id in enumerate(ordered_ids):
                cur.execute(
                    "UPDATE timeline_blocks SET order_index = ? WHERE id = ? AND project_id = ?",
                    (index, block_id, project_id),
                )

    # ------------------------------------------------------------------ #
    # Notas
    # ------------------------------------------------------------------ #
    def list_notes(self, project_id: int) -> list[sqlite3.Row]:
        cur = self._conn.execute(
            "SELECT * FROM notes WHERE project_id = ? ORDER BY order_index, id",
            (project_id,),
        )
        return cur.fetchall()

    def get_note(self, note_id: int) -> Optional[sqlite3.Row]:
        cur = self._conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,))
        return cur.fetchone()

    def create_note(self, project_id: int, title: str = "Nueva nota") -> int:
        with self._tx() as cur:
            cur.execute(
                "SELECT COALESCE(MAX(order_index), -1) + 1 FROM notes WHERE project_id = ?",
                (project_id,),
            )
            next_order = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO notes (project_id, title, content, updated_at, order_index) "
                "VALUES (?, ?, '', ?, ?)",
                (project_id, title, self._now(), next_order),
            )
            return cur.lastrowid

    def update_note(self, note_id: int, **fields):
        fields = dict(fields)
        fields["updated_at"] = self._now()
        self._update_row("notes", note_id, fields)

    def delete_note(self, note_id: int):
        with self._tx() as cur:
            cur.execute("DELETE FROM notes WHERE id = ?", (note_id,))

    # ------------------------------------------------------------------ #
    # Utilidad genérica
    # ------------------------------------------------------------------ #
    def _update_row(self, table: str, row_id: int, fields: dict[str, Any]):
        if not fields:
            return
        columns = ", ".join(f"{key} = ?" for key in fields)
        values = list(fields.values()) + [row_id]
        with self._tx() as cur:
            cur.execute(f"UPDATE {table} SET {columns} WHERE id = ?", values)