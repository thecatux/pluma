"""Capa de persistencia de Pluma.

Toda la aplicación guarda su estado en una única base de datos SQLite
ubicada en <directorio del programa o del ejecutable>/data/pluma.db (configurable vía
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

from pluma.core.paths import program_dir, user_data_dir


def _is_writable_dir(path: str) -> bool:
    """Comprueba de verdad si se puede escribir en `path`.

    `os.access` no es fiable en Windows (puede devolver True en carpetas
    protegidas por ACL/UAC), así que se prueba creando y borrando un
    archivo temporal.
    """
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".pluma_write_test")
        with open(probe, "w", encoding="utf-8"):
            pass
        os.remove(probe)
        return True
    except OSError:
        return False


def _default_db_path() -> str:
    """Calcula la ruta predeterminada de la base de datos SQLite."""
    env_path = os.environ.get("PLUMA_DB_PATH")
    if env_path:
        return env_path
    # El directorio junto al ejecutable puede ser de solo lectura (p. ej.
    # instalado en "Archivos de programa"): en ese caso se usa la carpeta
    # de datos del usuario en lugar de fallar al abrir la base.
    data_dir = os.path.join(program_dir(), "data")
    if _is_writable_dir(data_dir):
        return os.path.join(data_dir, "pluma.db")
    return os.path.join(user_data_dir(), "pluma.db")


_PROGRAM_DIR = program_dir()


def __getattr__(name: str):
    """`DEFAULT_DB_PATH` se calcula al pedirlo, no al importar el módulo:
    así PLUMA_DB_PATH (p. ej. fijada por una prueba tras importar) se
    respeta y no se crea la carpeta `data` como efecto secundario."""
    if name == "DEFAULT_DB_PATH":
        return _default_db_path()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _same_file(a: str, b: str) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


class DuplicateProjectError(ValueError, sqlite3.IntegrityError):
    """Ya existe un proyecto con ese nombre (compatible con quien captura
    ValueError, como la validación de nombre vacío, o IntegrityError)."""


# Columnas que `_update_row` acepta por tabla. Evita interpolar nombres
# arbitrarios en el SQL y que se pueda reescribir `id` o `project_id`.
_UPDATABLE_COLUMNS = {
    "projects": {"name", "title", "author", "genre", "synopsis", "page_count", "last_opened_at"},
    "chapters": {"title", "content", "synopsis", "order_index", "word_count"},
    "characters": {"name", "order_index"},
    "character_fields": {"field_name", "field_value", "order_index"},
    "scenes": {"title", "order_index"},
    "scene_fields": {"field_name", "field_value", "order_index"},
    "timeline_blocks": {"title", "date_label", "group_name", "description", "order_index",
                        "color", "is_milestone", "chapter_id"},
    "notes": {"title", "content", "updated_at", "order_index"},
}

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
    """Gestor de persistencia SQLite para proyectos, capítulos, personajes, escenas y notas."""

    def __init__(self, path: Optional[str] = None):
        self.path = path or _default_db_path()
        self._manual_save_enabled = False
        self._pending_transaction = False
        self._has_pending_changes = False
        self._pending_changes_callback = None
        self._pending_ui_states = {}
        os.makedirs(os.path.dirname(os.path.abspath(self.path)) or ".", exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        try:
            self._configure_connection()
        except BaseException:
            self._conn.close()
            raise

    def _configure_connection(self):
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
        """Cierra la conexión con la base de datos."""
        self._conn.close()

    @property
    def has_pending_changes(self) -> bool:
        """Indica si hay cambios de proyecto pendientes de confirmar."""
        return self._has_pending_changes

    @property
    def manual_save_enabled(self) -> bool:
        """Indica si las escrituras de proyecto se mantienen pendientes."""
        return self._manual_save_enabled

    def set_pending_changes_callback(self, callback):
        """Registra una función para notificar cambios en el estado pendiente."""
        self._pending_changes_callback = callback

    def set_manual_save_enabled(self, enabled: bool):
        """Activa o desactiva el almacenamiento transaccional pendiente."""
        self._manual_save_enabled = bool(enabled)

    def commit_pending_changes(self):
        """Confirma todos los cambios pendientes en una sola transacción."""
        if self._pending_transaction:
            self._conn.commit()
            self._pending_transaction = False
        self._set_pending_changes(False)
        self._flush_pending_ui_states()

    def discard_pending_changes(self):
        """Revierte todos los cambios pendientes de la transacción actual."""
        if self._pending_transaction:
            self._conn.rollback()
            self._pending_transaction = False
        self._set_pending_changes(False)
        self._flush_pending_ui_states()

    def _set_pending_changes(self, pending: bool):
        if self._has_pending_changes == pending:
            return
        self._has_pending_changes = pending
        if self._pending_changes_callback is not None:
            self._pending_changes_callback(pending)

    def _flush_pending_ui_states(self):
        states = self._pending_ui_states
        self._pending_ui_states = {}
        for project_id, state in states.items():
            self.save_project_ui_state(project_id, state)

    def backup_to(self, dest_path: str):
        """Copia íntegra y consistente de la base de datos a `dest_path`,
        usando la API de backup de SQLite (segura de usar con la app
        abierta y con WAL activo, a diferencia de copiar el fichero a
        mano con el sistema de archivos)."""
        if _same_file(dest_path, self.path):
            raise ValueError("El destino de la copia no puede ser la propia base de datos.")
        os.makedirs(os.path.dirname(os.path.abspath(dest_path)) or ".", exist_ok=True)
        dest = sqlite3.connect(dest_path)
        try:
            with dest:
                self._conn.backup(dest)
        finally:
            dest.close()

    def restore_from(self, src_path: str):
        """Sustituye el contenido de la base de datos abierta por el de la
        copia `src_path` (hecha con `backup_to`). Usa la API de backup de
        SQLite en sentido inverso, de modo que la conexión actual sigue
        siendo válida y no hay que cerrar ni reabrir nada con la app en
        marcha. Lanza ValueError si el archivo no es una copia de Pluma;
        si la copia falla a mitad, la base de datos actual queda intacta.
        """
        # sqlite3.connect() CREA un archivo vacío si la ruta no existe.
        if self._pending_transaction:
            raise RuntimeError("Resuelve los cambios pendientes antes de restaurar una copia.")
        if not os.path.isfile(src_path):
            raise ValueError("El archivo seleccionado no existe.")
        if _same_file(src_path, self.path):
            raise ValueError("No se puede restaurar la base de datos desde sí misma.")
        src = sqlite3.connect(src_path)
        try:
            try:
                tables = {row[0] for row in src.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'")}
                check = src.execute("PRAGMA quick_check").fetchone()
                foreign_key_errors = src.execute("PRAGMA foreign_key_check").fetchall()
                project_columns = {row[1] for row in src.execute("PRAGMA table_info(projects)")}
                chapter_columns = {row[1] for row in src.execute("PRAGMA table_info(chapters)")}
            except sqlite3.DatabaseError:  # no es un archivo SQLite, o está dañado
                tables, check, foreign_key_errors = set(), None, []
                project_columns, chapter_columns = set(), set()
            if not {"projects", "chapters"} <= tables:
                raise ValueError("El archivo seleccionado no es una copia de seguridad de Pluma.")
            if check is None or check[0] != "ok":
                raise ValueError("La copia de seguridad está dañada; no se ha restaurado nada.")
            if foreign_key_errors:
                raise ValueError("La copia de seguridad contiene referencias inválidas; no se ha restaurado nada.")
            if not {"id", "name", "created_at"} <= project_columns or not {
                "id", "project_id", "title", "content", "order_index"
            } <= chapter_columns:
                raise ValueError("La copia de seguridad no tiene un esquema compatible con Pluma.")
            src.backup(self._conn)
        finally:
            src.close()
        # Una copia hecha con una versión anterior puede carecer de
        # columnas añadidas después: las migraciones las completan.
        manual_save_enabled = self._manual_save_enabled
        self._manual_save_enabled = False
        try:
            self._init_schema()
        finally:
            self._manual_save_enabled = manual_save_enabled

    # ------------------------------------------------------------------ #
    # Esquema
    # ------------------------------------------------------------------ #
    def _init_schema(self):
        """Crea las tablas e índices necesarios si no existen y ejecuta migraciones."""
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

                CREATE TABLE IF NOT EXISTS project_ui_state (
                    project_id INTEGER PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
                    state_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL
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
            # Solo se rellena `title` con el nombre del proyecto cuando la
            # columna acaba de crearse; si ya existía, un `title` vacío es
            # una elección del usuario y no debe sobrescribirse en cada arranque.
            if "title" not in existing_columns:
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
    def _tx(self, track_pending: bool = True):
        """Ejecuta una operación atómica, dentro del guardado pendiente si está activo."""
        if self._manual_save_enabled and (track_pending or self._pending_transaction):
            started_transaction = not self._pending_transaction
            if started_transaction:
                self._conn.execute("BEGIN")
                self._pending_transaction = True
            cur = self._conn.cursor()
            cur.execute("SAVEPOINT pluma_operation")
            try:
                yield cur
                cur.execute("RELEASE SAVEPOINT pluma_operation")
                if track_pending:
                    self._set_pending_changes(True)
            except BaseException:
                cur.execute("ROLLBACK TO SAVEPOINT pluma_operation")
                cur.execute("RELEASE SAVEPOINT pluma_operation")
                if started_transaction and not self._has_pending_changes:
                    self._conn.rollback()
                    self._pending_transaction = False
                raise
            finally:
                cur.close()
            return

        cur = self._conn.cursor()
        try:
            yield cur
            self._conn.commit()
        except BaseException:
            self._conn.rollback()
            raise
        finally:
            cur.close()

    @staticmethod
    def _now() -> str:
        """Devuelve la marca temporal actual en formato YYYY-MM-DD HH:MM:SS."""
        return time.strftime("%Y-%m-%d %H:%M:%S")

    # ------------------------------------------------------------------ #
    # Proyectos
    # ------------------------------------------------------------------ #
    def list_projects(self) -> list[sqlite3.Row]:
        """Devuelve la lista de proyectos ordenados por fecha de última apertura o creación descendente."""
        cur = self._conn.execute(
            "SELECT * FROM projects ORDER BY COALESCE(last_opened_at, created_at) DESC"
        )
        return cur.fetchall()

    def create_project(self, name: str) -> int:
        """Crea un nuevo proyecto con el nombre dado y devuelve su identificador."""
        name = name.strip()
        if not name:
            raise ValueError("El nombre del proyecto no puede estar vacío.")
        now = self._now()
        try:
            with self._tx(track_pending=False) as cur:
                cur.execute(
                    "INSERT INTO projects (name, title, created_at, last_opened_at) VALUES (?, ?, ?, ?)",
                    (name, name, now, now),
                )
                return cur.lastrowid
        except sqlite3.IntegrityError as exc:
            raise DuplicateProjectError(f"Ya existe un proyecto llamado «{name}».") from exc

    def rename_project(self, project_id: int, new_name: str):
        """Modifica el nombre identificativo de un proyecto existente."""
        new_name = new_name.strip()
        if not new_name:
            raise ValueError("El nombre del proyecto no puede estar vacío.")
        try:
            with self._tx(track_pending=False) as cur:
                cur.execute("UPDATE projects SET name = ? WHERE id = ?", (new_name, project_id))
        except sqlite3.IntegrityError as exc:
            raise DuplicateProjectError(f"Ya existe un proyecto llamado «{new_name}».") from exc

    def touch_project(self, project_id: int):
        """Actualiza la fecha de última apertura del proyecto a la fecha y hora actual."""
        with self._tx(track_pending=False) as cur:
            cur.execute(
                "UPDATE projects SET last_opened_at = ? WHERE id = ?", (self._now(), project_id)
            )

    def delete_project(self, project_id: int):
        """Elimina un proyecto y todos sus datos vinculados en cascada."""
        with self._tx(track_pending=False) as cur:
            cur.execute("DELETE FROM projects WHERE id = ?", (project_id,))

    def get_project(self, project_id: int) -> Optional[sqlite3.Row]:
        """Obtiene la fila correspondiente al proyecto según su ID, o None si no existe."""
        cur = self._conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
        return cur.fetchone()

    def get_project_ui_state(self, project_id: int) -> dict[str, Any]:
        """Recupera el diccionario de estado de interfaz guardado para el proyecto."""
        cur = self._conn.execute(
            "SELECT state_json FROM project_ui_state WHERE project_id = ?", (project_id,)
        )
        row = cur.fetchone()
        if row is None:
            return {}
        try:
            state = json.loads(row["state_json"])
        except (TypeError, json.JSONDecodeError):
            return {}
        return state if isinstance(state, dict) else {}

    def save_project_ui_state(self, project_id: int, state: dict[str, Any]):
        """Guarda o actualiza el estado de la interfaz del proyecto en formato JSON."""
        if self._pending_transaction:
            self._pending_ui_states[project_id] = state
            return
        state_json = json.dumps(state, ensure_ascii=False)
        with self._tx(track_pending=False) as cur:
            cur.execute(
                "INSERT INTO project_ui_state (project_id, state_json, updated_at) "
                "VALUES (?, ?, ?) ON CONFLICT(project_id) DO UPDATE SET "
                "state_json = excluded.state_json, updated_at = excluded.updated_at",
                (project_id, state_json, self._now()),
            )

    def project_exists(self, project_id: int) -> bool:
        """Comprueba si un proyecto con el identificador dado existe en la base de datos."""
        cur = self._conn.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,))
        return cur.fetchone() is not None

    # ------------------------------------------------------------------ #
    # Datos generales de la novela (ficha del proyecto)
    # ------------------------------------------------------------------ #
    def get_project_info(self, project_id: int) -> Optional[sqlite3.Row]:
        """Devuelve los datos generales de la ficha de la novela (título, autor, género, sinopsis, extensión)."""
        cur = self._conn.execute(
            "SELECT id, name, title, author, genre, synopsis, page_count "
            "FROM projects WHERE id = ?",
            (project_id,),
        )
        return cur.fetchone()

    def update_project_info(self, project_id: int, **fields):
        """Actualiza los campos de la ficha general de la novela."""
        self._update_row("projects", project_id, fields)

    # ------------------------------------------------------------------ #
    # Capítulos
    # ------------------------------------------------------------------ #
    def list_chapters(self, project_id: int) -> list[sqlite3.Row]:
        """Obtiene todos los capítulos del proyecto ordenados secuencialmente."""
        cur = self._conn.execute(
            "SELECT * FROM chapters WHERE project_id = ? ORDER BY order_index, id",
            (project_id,),
        )
        return cur.fetchall()

    def get_chapter(self, chapter_id: int) -> Optional[sqlite3.Row]:
        """Devuelve la fila del capítulo según su identificador o None si no existe."""
        cur = self._conn.execute("SELECT * FROM chapters WHERE id = ?", (chapter_id,))
        return cur.fetchone()

    def count_chapters(self, project_id: int) -> int:
        """Devuelve el número total de capítulos del proyecto."""
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
        """Crea un nuevo capítulo al final del orden actual y devuelve su ID."""
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
        """Actualiza los campos especificados del capítulo (título, contenido, sinopsis, word_count)."""
        self._update_row("chapters", chapter_id, fields)

    def delete_chapter(self, chapter_id: int):
        """Elimina un capítulo por su ID (en cascada elimina enlaces con escenas y desenlaza bloques)."""
        with self._tx() as cur:
            cur.execute("DELETE FROM chapters WHERE id = ?", (chapter_id,))

    def reorder_chapters(self, ordered_ids: list[int], project_id: Optional[int] = None):
        """Recibe la lista completa de ids de capítulos en el nuevo orden
        deseado y reescribe `order_index` en consecuencia. Si se pasa
        `project_id`, solo se tocan capítulos de ese proyecto (como hacen
        el resto de `reorder_*`)."""
        with self._tx() as cur:
            for index, chapter_id in enumerate(ordered_ids):
                if project_id is None:
                    cur.execute("UPDATE chapters SET order_index = ? WHERE id = ?",
                                (index, chapter_id))
                else:
                    cur.execute("UPDATE chapters SET order_index = ? WHERE id = ? AND project_id = ?",
                                (index, chapter_id, project_id))

    # ------------------------------------------------------------------ #
    # Personajes (ficha con campos flexibles clave/valor)
    # ------------------------------------------------------------------ #
    def list_characters(self, project_id: int) -> list[sqlite3.Row]:
        """Devuelve la lista de personajes del proyecto en su orden actual."""
        cur = self._conn.execute(
            "SELECT * FROM characters WHERE project_id = ? ORDER BY order_index, id",
            (project_id,),
        )
        return cur.fetchall()

    def get_character(self, character_id: int) -> Optional[sqlite3.Row]:
        """Obtiene la fila del personaje por su identificador o None si no existe."""
        cur = self._conn.execute("SELECT * FROM characters WHERE id = ?", (character_id,))
        return cur.fetchone()

    def create_character(self, project_id: int, name: str = "Nuevo personaje") -> int:
        """Crea un personaje con la plantilla de campos por defecto y devuelve su ID."""
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
        """Actualiza los atributos del personaje (p. ej. nombre)."""
        self._update_row("characters", character_id, fields)

    def delete_character(self, character_id: int):
        """Elimina un personaje y sus campos asociados en cascada."""
        with self._tx() as cur:
            cur.execute("DELETE FROM characters WHERE id = ?", (character_id,))

    def reorder_characters(self, project_id: int, ordered_ids: list[int]):
        """Actualiza el orden de los personajes del proyecto según la lista de IDs recibida."""
        with self._tx() as cur:
            for index, character_id in enumerate(ordered_ids):
                cur.execute(
                    "UPDATE characters SET order_index = ? WHERE id = ? AND project_id = ?",
                    (index, character_id, project_id),
                )

    def list_character_fields(self, character_id: int) -> list[sqlite3.Row]:
        """Devuelve los campos de la ficha del personaje ordenados."""
        cur = self._conn.execute(
            "SELECT * FROM character_fields WHERE character_id = ? ORDER BY order_index, id",
            (character_id,),
        )
        return cur.fetchall()

    def add_character_field(self, character_id: int, field_name: str, field_value: str = "") -> int:
        """Añade un campo nuevo al final de la ficha del personaje y devuelve su ID."""
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
        """Actualiza el nombre o valor de un campo de personaje."""
        self._update_row("character_fields", field_id, fields)

    def update_character_with_fields(self, character_id: int, name: str, fields: list[dict]):
        """Guarda el nombre del personaje y todos sus campos en una sola transacción.

        Cada elemento de `fields` es un diccionario con las claves `id`,
        `field_name` y `field_value`. Evita el commit por campo que supone
        llamar a `update_character_field` en bucle.
        """
        with self._tx() as cur:
            cur.execute("UPDATE characters SET name = ? WHERE id = ?", (name, character_id))
            cur.executemany(
                "UPDATE character_fields SET field_name = :field_name, field_value = :field_value "
                "WHERE id = :id AND character_id = :owner_id",
                [{"id": f["id"], "field_name": f["field_name"], "field_value": f["field_value"],
                  "owner_id": character_id} for f in fields],
            )

    def delete_character_field(self, field_id: int):
        """Elimina un campo de la ficha de personaje por su ID."""
        with self._tx() as cur:
            cur.execute("DELETE FROM character_fields WHERE id = ?", (field_id,))

    def reorder_character_fields(self, character_id: int, ordered_ids: list[int]):
        """Reordena los campos de la ficha del personaje según la lista de IDs."""
        self._reorder_rows("character_fields", "character_id", character_id, ordered_ids)

    # ------------------------------------------------------------------ #
    # Escenas (ficha flexible + enlace con capítulos)
    # ------------------------------------------------------------------ #
    def list_scenes(self, project_id: int) -> list[sqlite3.Row]:
        """Devuelve todas las escenas del proyecto en su orden actual."""
        cur = self._conn.execute(
            "SELECT * FROM scenes WHERE project_id = ? ORDER BY order_index, id",
            (project_id,),
        )
        return cur.fetchall()

    def get_scene(self, scene_id: int) -> Optional[sqlite3.Row]:
        """Obtiene la fila de la escena por su identificador o None si no existe."""
        cur = self._conn.execute("SELECT * FROM scenes WHERE id = ?", (scene_id,))
        return cur.fetchone()

    def create_scene(self, project_id: int, title: str = "Nueva escena") -> int:
        """Crea una escena con los aspectos predeterminados y devuelve su ID."""
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
        """Actualiza el título u otros datos de la escena."""
        self._update_row("scenes", scene_id, fields)

    def delete_scene(self, scene_id: int):
        """Elimina una escena y sus campos y enlaces asociados en cascada."""
        with self._tx() as cur:
            cur.execute("DELETE FROM scenes WHERE id = ?", (scene_id,))

    def reorder_scenes(self, project_id: int, ordered_ids: list[int]):
        """Actualiza el orden de las escenas del proyecto según la lista de IDs."""
        with self._tx() as cur:
            for index, scene_id in enumerate(ordered_ids):
                cur.execute(
                    "UPDATE scenes SET order_index = ? WHERE id = ? AND project_id = ?",
                    (index, scene_id, project_id),
                )

    def list_scene_fields(self, scene_id: int) -> list[sqlite3.Row]:
        """Devuelve los aspectos/campos de la escena ordenados."""
        cur = self._conn.execute(
            "SELECT * FROM scene_fields WHERE scene_id = ? ORDER BY order_index, id",
            (scene_id,),
        )
        return cur.fetchall()

    def add_scene_field(self, scene_id: int, field_name: str, field_value: str = "") -> int:
        """Añade un aspecto a la escena y devuelve su identificador."""
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
        """Actualiza el nombre o valor de un aspecto de la escena."""
        self._update_row("scene_fields", field_id, fields)

    def update_scene_with_fields(self, scene_id: int, title: str, fields: list[dict]):
        """Guarda el título de la escena y todos sus campos en una sola transacción.

        Cada elemento de `fields` es un diccionario con las claves `id`,
        `field_name` y `field_value`. Evita el commit por campo que supone
        llamar a `update_scene_field` en bucle.
        """
        with self._tx() as cur:
            cur.execute("UPDATE scenes SET title = ? WHERE id = ?", (title, scene_id))
            cur.executemany(
                "UPDATE scene_fields SET field_name = :field_name, field_value = :field_value "
                "WHERE id = :id AND scene_id = :owner_id",
                [{"id": f["id"], "field_name": f["field_name"], "field_value": f["field_value"],
                  "owner_id": scene_id} for f in fields],
            )

    def delete_scene_field(self, field_id: int):
        """Elimina un aspecto de la escena por su ID."""
        with self._tx() as cur:
            cur.execute("DELETE FROM scene_fields WHERE id = ?", (field_id,))

    def reorder_scene_fields(self, scene_id: int, ordered_ids: list[int]):
        """Reordena los aspectos de la escena según la lista de IDs."""
        self._reorder_rows("scene_fields", "scene_id", scene_id, ordered_ids)

    def get_scene_chapter_links(self, scene_id: int) -> list[int]:
        """Devuelve la lista de IDs de capítulos vinculados a la escena."""
        cur = self._conn.execute(
            "SELECT chapter_id FROM scene_chapter_links WHERE scene_id = ?", (scene_id,)
        )
        return [row[0] for row in cur.fetchall()]

    def get_project_scene_chapter_links(self, project_id: int) -> dict[int, list[int]]:
        """Devuelve los capítulos vinculados a cada escena del proyecto.

        Es el equivalente en una sola consulta de llamar a
        `get_scene_chapter_links` por cada escena, para construir listas
        sin una consulta por fila. Solo incluye escenas con vínculos.
        """
        cur = self._conn.execute(
            """
            SELECT l.scene_id, l.chapter_id
            FROM scene_chapter_links AS l
            JOIN scenes AS s ON s.id = l.scene_id
            WHERE s.project_id = ?
            ORDER BY l.scene_id, l.chapter_id
            """,
            (project_id,),
        )
        links: dict[int, list[int]] = {}
        for scene_id, chapter_id in cur.fetchall():
            links.setdefault(scene_id, []).append(chapter_id)
        return links

    def set_scene_chapter_links(self, scene_id: int, chapter_ids: list[int]):
        """Establece la lista de capítulos vinculados a la escena reemplazando los anteriores."""
        with self._tx() as cur:
            cur.execute("SELECT project_id FROM scenes WHERE id = ?", (scene_id,))
            scene = cur.fetchone()
            if scene is not None:
                for chapter_id in chapter_ids:
                    cur.execute("SELECT project_id FROM chapters WHERE id = ?", (chapter_id,))
                    chapter = cur.fetchone()
                    if chapter is None or chapter["project_id"] != scene["project_id"]:
                        raise ValueError("La escena y el capítulo deben pertenecer al mismo proyecto.")
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
        """Devuelve todos los bloques de la línea temporal del proyecto ordenados."""
        cur = self._conn.execute(
            "SELECT * FROM timeline_blocks WHERE project_id = ? ORDER BY order_index, id",
            (project_id,),
        )
        return cur.fetchall()

    def create_timeline_block(self, project_id: int, title: str = "Nuevo evento") -> int:
        """Crea un bloque de evento al final de la línea temporal y devuelve su ID."""
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
        """Actualiza los campos de un bloque de evento en la línea temporal."""
        if "chapter_id" not in fields or fields["chapter_id"] is None:
            self._update_row("timeline_blocks", block_id, fields)
            return
        allowed = _UPDATABLE_COLUMNS["timeline_blocks"]
        invalid = set(fields) - allowed
        if invalid:
            raise ValueError(f"Columnas no permitidas en timeline_blocks: {sorted(invalid)}")
        with self._tx() as cur:
            cur.execute("SELECT project_id FROM timeline_blocks WHERE id = ?", (block_id,))
            block = cur.fetchone()
            cur.execute("SELECT project_id FROM chapters WHERE id = ?", (fields["chapter_id"],))
            chapter = cur.fetchone()
            if block is not None and (chapter is None or chapter["project_id"] != block["project_id"]):
                raise ValueError("El bloque y el capítulo deben pertenecer al mismo proyecto.")
            columns = ", ".join(f"{key} = ?" for key in fields)
            cur.execute(
                f"UPDATE timeline_blocks SET {columns} WHERE id = ?",
                list(fields.values()) + [block_id],
            )

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
        """Elimina un bloque de la línea temporal por su ID."""
        with self._tx() as cur:
            cur.execute("DELETE FROM timeline_blocks WHERE id = ?", (block_id,))

    def reorder_timeline_blocks(self, project_id: int, ordered_ids: list[int]):
        """Reordena los bloques de la línea temporal según la lista de IDs."""
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
        """Devuelve todas las notas del proyecto en su orden actual."""
        cur = self._conn.execute(
            "SELECT * FROM notes WHERE project_id = ? ORDER BY order_index, id",
            (project_id,),
        )
        return cur.fetchall()

    def get_note(self, note_id: int) -> Optional[sqlite3.Row]:
        """Obtiene una nota según su identificador o None si no existe."""
        cur = self._conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,))
        return cur.fetchone()

    def create_note(self, project_id: int, title: str = "Nueva nota") -> int:
        """Crea una nota al final de la lista del proyecto y devuelve su ID."""
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
        """Actualiza los campos de una nota y registra la fecha de última edición."""
        fields = dict(fields)
        fields["updated_at"] = self._now()
        self._update_row("notes", note_id, fields)

    def delete_note(self, note_id: int):
        """Elimina una nota por su ID."""
        with self._tx() as cur:
            cur.execute("DELETE FROM notes WHERE id = ?", (note_id,))

    def reorder_notes(self, project_id: int, ordered_ids: list[int]):
        """Reordena las notas del proyecto según la lista de IDs."""
        with self._tx() as cur:
            for index, note_id in enumerate(ordered_ids):
                cur.execute(
                    "UPDATE notes SET order_index = ? WHERE id = ? AND project_id = ?",
                    (index, note_id, project_id),
                )

    # ------------------------------------------------------------------ #
    # Utilidad genérica
    # ------------------------------------------------------------------ #
    def _update_row(self, table: str, row_id: int, fields: dict[str, Any]):
        """Ejecuta un UPDATE dinámico sobre la tabla y fila especificadas."""
        if not fields:
            return
        allowed = _UPDATABLE_COLUMNS.get(table)
        if allowed is None:
            raise ValueError(f"Tabla no actualizable: {table!r}")
        invalid = set(fields) - allowed
        if invalid:
            raise ValueError(f"Columnas no permitidas en {table}: {sorted(invalid)}")
        columns = ", ".join(f"{key} = ?" for key in fields)
        values = list(fields.values()) + [row_id]
        with self._tx() as cur:
            cur.execute(f"UPDATE {table} SET {columns} WHERE id = ?", values)

    def _reorder_rows(self, table: str, parent_column: str, parent_id: int, ordered_ids: list[int]):
        """Reescribe `order_index` de las filas hijas de `parent_id` según
        el orden recibido."""
        with self._tx() as cur:
            for index, row_id in enumerate(ordered_ids):
                cur.execute(
                    f"UPDATE {table} SET order_index = ? WHERE id = ? AND {parent_column} = ?",
                    (index, row_id, parent_id),
                )