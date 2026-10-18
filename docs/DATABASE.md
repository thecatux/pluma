# Estructura de la base de datos

Pluma guarda todo su estado en una única base de datos **SQLite**. La capa de
acceso a datos vive en [`src/pluma/core/db.py`](../src/pluma/core/db.py) y no
depende de Qt, por lo que puede probarse sin interfaz gráfica.

## Ubicación y configuración

- Ruta predeterminada: `data/pluma.db` junto a la aplicación.
- Si esa carpeta no admite escritura, se usa el directorio de datos del usuario.
- La variable de entorno `PLUMA_DB_PATH` permite fijar otra ruta (útil en pruebas).
- Se activan `PRAGMA foreign_keys = ON`, `PRAGMA journal_mode = WAL` y
  `PRAGMA synchronous = NORMAL`.

La base aloja varios **proyectos** (novelas). Todas las tablas de contenido
cuelgan de `projects.id` mediante `project_id`, con borrado en cascada: al
eliminar un proyecto se limpian automáticamente sus capítulos, personajes,
escenas, notas y bloques de la línea temporal.

## Diagrama de relaciones

```text
projects ─┬─< chapters ──< scene_chapter_links >── scenes
          ├─< characters ──< character_fields      │
          ├─< scenes ──────< scene_fields           │
          ├─< timeline_blocks ──────────────────────┘ (chapter_id, ON DELETE SET NULL)
          ├─< notes
          └── project_ui_state (1:1)
```

## Tablas

### `projects`

Proyecto (novela) y sus datos generales.

| Columna | Tipo | Clave | Descripción |
| --- | --- | --- | --- |
| `id` | INTEGER | PK, AUTOINCREMENT | Identificador del proyecto. |
| `name` | TEXT | UNIQUE, NOT NULL | Nombre identificativo del proyecto. |
| `created_at` | TEXT | NOT NULL | Fecha de creación (`YYYY-MM-DD HH:MM:SS`). |
| `last_opened_at` | TEXT | | Fecha de última apertura. |
| `title` | TEXT | NOT NULL, DEFAULT `''` | Título de la novela. |
| `author` | TEXT | NOT NULL, DEFAULT `''` | Autoría. |
| `genre` | TEXT | NOT NULL, DEFAULT `''` | Género (lista en `DEFAULT_GENRES`). |
| `synopsis` | TEXT | NOT NULL, DEFAULT `''` | Sinopsis. |
| `page_count` | INTEGER | NOT NULL, DEFAULT `0` | Extensión estimada en páginas. |

### `project_ui_state`

Estado de la interfaz por proyecto, en formato JSON (1:1 con `projects`).

| Columna | Tipo | Clave | Descripción |
| --- | --- | --- | --- |
| `project_id` | INTEGER | PK, FK → `projects.id` ON DELETE CASCADE | Proyecto asociado. |
| `state_json` | TEXT | NOT NULL, DEFAULT `'{}'` | Estado serializado (sección activa, etc.). |
| `updated_at` | TEXT | NOT NULL | Fecha de última actualización. |

### `chapters`

Capítulos del manuscrito.

| Columna | Tipo | Clave | Descripción |
| --- | --- | --- | --- |
| `id` | INTEGER | PK, AUTOINCREMENT | Identificador del capítulo. |
| `project_id` | INTEGER | NOT NULL, FK → `projects.id` ON DELETE CASCADE | Proyecto al que pertenece. |
| `title` | TEXT | NOT NULL, DEFAULT `'Nuevo capítulo'` | Título del capítulo. |
| `content` | TEXT | NOT NULL, DEFAULT `''` | Contenido en HTML enriquecido. |
| `synopsis` | TEXT | NOT NULL, DEFAULT `''` | Sinopsis del capítulo. |
| `order_index` | INTEGER | NOT NULL, DEFAULT `0` | Orden dentro del proyecto. |
| `word_count` | INTEGER | NOT NULL, DEFAULT `0` | Conteo de palabras cacheado. |

> `word_count` se añadió mediante migración y se recalcula al guardar o abrir
> cada capítulo.

### `characters`

Fichas de personajes.

| Columna | Tipo | Clave | Descripción |
| --- | --- | --- | --- |
| `id` | INTEGER | PK, AUTOINCREMENT | Identificador del personaje. |
| `project_id` | INTEGER | NOT NULL, FK → `projects.id` ON DELETE CASCADE | Proyecto al que pertenece. |
| `name` | TEXT | NOT NULL, DEFAULT `'Nuevo personaje'` | Nombre del personaje. |
| `order_index` | INTEGER | NOT NULL, DEFAULT `0` | Orden dentro del proyecto. |

### `character_fields`

Campos clave/valor de cada personaje (ficha flexible).

| Columna | Tipo | Clave | Descripción |
| --- | --- | --- | --- |
| `id` | INTEGER | PK, AUTOINCREMENT | Identificador del campo. |
| `character_id` | INTEGER | NOT NULL, FK → `characters.id` ON DELETE CASCADE | Personaje asociado. |
| `field_name` | TEXT | NOT NULL | Nombre del campo. |
| `field_value` | TEXT | NOT NULL, DEFAULT `''` | Valor del campo. |
| `order_index` | INTEGER | NOT NULL, DEFAULT `0` | Orden dentro de la ficha. |

### `scenes`

Fichas de escenas.

| Columna | Tipo | Clave | Descripción |
| --- | --- | --- | --- |
| `id` | INTEGER | PK, AUTOINCREMENT | Identificador de la escena. |
| `project_id` | INTEGER | NOT NULL, FK → `projects.id` ON DELETE CASCADE | Proyecto al que pertenece. |
| `title` | TEXT | NOT NULL, DEFAULT `'Nueva escena'` | Título de la escena. |
| `order_index` | INTEGER | NOT NULL, DEFAULT `0` | Orden dentro del proyecto. |

### `scene_fields`

Aspectos clave/valor de cada escena (ficha flexible).

| Columna | Tipo | Clave | Descripción |
| --- | --- | --- | --- |
| `id` | INTEGER | PK, AUTOINCREMENT | Identificador del aspecto. |
| `scene_id` | INTEGER | NOT NULL, FK → `scenes.id` ON DELETE CASCADE | Escena asociada. |
| `field_name` | TEXT | NOT NULL | Nombre del aspecto. |
| `field_value` | TEXT | NOT NULL, DEFAULT `''` | Valor del aspecto. |
| `order_index` | INTEGER | NOT NULL, DEFAULT `0` | Orden dentro de la ficha. |

### `scene_chapter_links`

Relación N:M entre escenas y capítulos.

| Columna | Tipo | Clave | Descripción |
| --- | --- | --- | --- |
| `scene_id` | INTEGER | PK, FK → `scenes.id` ON DELETE CASCADE | Escena vinculada. |
| `chapter_id` | INTEGER | PK, FK → `chapters.id` ON DELETE CASCADE | Capítulo vinculado. |

> Clave primaria compuesta `(scene_id, chapter_id)`.

### `timeline_blocks`

Bloques de la línea temporal (eventos ordenables y agrupables).

| Columna | Tipo | Clave | Descripción |
| --- | --- | --- | --- |
| `id` | INTEGER | PK, AUTOINCREMENT | Identificador del bloque. |
| `project_id` | INTEGER | NOT NULL, FK → `projects.id` ON DELETE CASCADE | Proyecto al que pertenece. |
| `title` | TEXT | NOT NULL, DEFAULT `'Nuevo evento'` | Título del evento. |
| `date_label` | TEXT | NOT NULL, DEFAULT `''` | Etiqueta de fecha/momento. |
| `group_name` | TEXT | NOT NULL, DEFAULT `''` | Grupo o hilo al que pertenece. |
| `description` | TEXT | NOT NULL, DEFAULT `''` | Descripción del evento. |
| `order_index` | INTEGER | NOT NULL, DEFAULT `0` | Orden dentro del proyecto. |
| `color` | TEXT | NOT NULL, DEFAULT `''` | Color manual del bloque. |
| `is_milestone` | INTEGER | NOT NULL, DEFAULT `0` | Marca de hito (0/1). |
| `chapter_id` | INTEGER | FK → `chapters.id` ON DELETE SET NULL | Capítulo vinculado (opcional). |

> `color`, `is_milestone` y `chapter_id` se añadieron mediante migración. Si se
> borra el capítulo vinculado, el bloque se conserva y `chapter_id` pasa a NULL.

### `notes`

Notas libres del proyecto.

| Columna | Tipo | Clave | Descripción |
| --- | --- | --- | --- |
| `id` | INTEGER | PK, AUTOINCREMENT | Identificador de la nota. |
| `project_id` | INTEGER | NOT NULL, FK → `projects.id` ON DELETE CASCADE | Proyecto al que pertenece. |
| `title` | TEXT | NOT NULL, DEFAULT `'Nueva nota'` | Título de la nota. |
| `content` | TEXT | NOT NULL, DEFAULT `''` | Contenido de la nota. |
| `updated_at` | TEXT | NOT NULL, DEFAULT `''` | Fecha de última edición. |
| `order_index` | INTEGER | NOT NULL, DEFAULT `0` | Orden dentro del proyecto. |

## Índices

Los índices cubren las columnas por las que se filtra en cada pantalla
(`project_id` y el orden, o el padre en las tablas de campos y enlaces).

| Índice | Tabla | Columnas |
| --- | --- | --- |
| `idx_chapters_project` | `chapters` | `project_id, order_index` |
| `idx_characters_project` | `characters` | `project_id, order_index` |
| `idx_character_fields_character` | `character_fields` | `character_id, order_index` |
| `idx_scenes_project` | `scenes` | `project_id, order_index` |
| `idx_scene_fields_scene` | `scene_fields` | `scene_id, order_index` |
| `idx_scene_links_scene` | `scene_chapter_links` | `scene_id` |
| `idx_scene_links_chapter` | `scene_chapter_links` | `chapter_id` |
| `idx_timeline_blocks_project` | `timeline_blocks` | `project_id, order_index` |
| `idx_notes_project` | `notes` | `project_id, order_index` |

## Migraciones

`Database._init_schema()` crea las tablas e índices si no existen y, después,
aplica migraciones sobre bases de datos de versiones anteriores:

- `_migrate_project_info_columns()`: añade `title`, `author`, `genre`,
  `synopsis` y `page_count` a `projects` y rellena `title` con `name` solo al
  crear la columna.
- `_migrate_chapter_word_count()`: añade `word_count` a `chapters`.
- `_migrate_timeline_columns()`: añade `color`, `is_milestone` y `chapter_id`
  a `timeline_blocks`.

Las copias de seguridad y restauración usan la API de *backup* de SQLite
(`backup_to` / `restore_from`), segura de usar con la aplicación abierta.
