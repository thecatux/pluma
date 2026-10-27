"""Ajustes de la aplicación (distintos del tema, que vive en `theme.py`).

Centraliza, con QSettings, todo lo que antes estaba fijo en el código:
el retardo del autoguardado, la velocidad de lectura usada para
estimar el tiempo de lectura de un capítulo, si se pide confirmación
antes de borrar elementos, y la fuente por defecto del editor de texto
enriquecido. Cualquier panel puede leer estos valores y suscribirse a
`signals.changed` para refrescarse en caliente cuando el usuario los
cambia desde el panel de Ajustes, sin tener que reiniciar Pluma ni
recibir el controlador por constructor.
"""

from contextlib import contextmanager

from PySide6.QtCore import QObject, Signal, QSettings

# Límites razonables para que un valor corrupto o escrito a mano en el
# QSettings no deje el autoguardado en un estado absurdo (por ejemplo,
# 0 ms golpeando la base de datos en cada pulsación).
MIN_AUTOSAVE_MS = 200
MAX_AUTOSAVE_MS = 5000
DEFAULT_AUTOSAVE_MS = 600

MIN_READING_SPEED = 100
MAX_READING_SPEED = 600
DEFAULT_READING_SPEED = 200

DEFAULT_EDITOR_FONT_FAMILY = "Segoe UI"
MIN_EDITOR_FONT_SIZE = 6
MAX_EDITOR_FONT_SIZE = 72
DEFAULT_EDITOR_FONT_SIZE = 12

_TRUE_STRINGS = {"true", "1", "yes", "on"}
_FALSE_STRINGS = {"false", "0", "no", "off"}


class _SettingsSignals(QObject):
    """Señales globales para notificar cambios en la configuración de la aplicación."""
    changed = Signal()


signals = _SettingsSignals()


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


class AppSettings:
    """Wrapper fino sobre QSettings con valores por defecto y validación.
    No mantiene estado propio en memoria (salvo el contador de lotes de
    `batch()`): cada lectura va a QSettings, así que distintas instancias
    (o el mismo objeto tras un cambio externo) siempre ven el valor vigente.
    """

    def __init__(self):
        self._batch_depth = 0
        self._batch_dirty = False

    @property
    def _settings(self) -> QSettings:
        # Se crea en cada acceso y no en __init__: `settings` (abajo) se
        # instancia al importar el módulo, normalmente ANTES de que la
        # aplicación llame a setOrganizationName/setApplicationName. Un
        # QSettings() creado tan pronto queda sin organización ni nombre
        # de aplicación y no puede leer ni escribir en disco (status
        # AccessError), de modo que los cambios se perdían al reiniciar.
        # Crearlo bajo demanda es barato y todas las instancias comparten
        # el mismo almacén.
        return QSettings()

    # -- Lectura/escritura tolerantes a valores corruptos ----------------- #
    def _read_int(self, key: str, default: int, low: int, high: int) -> int:
        """Lee un entero. Si el valor guardado no es numérico (corrupto o
        editado a mano) se devuelve `default`, no el límite inferior."""
        raw = self._settings.value(key, default)
        try:
            value = int(float(raw))
        except (TypeError, ValueError, OverflowError):
            return default
        return _clamp(value, low, high)

    def _read_bool(self, key: str, default: bool) -> bool:
        raw = self._settings.value(key, default)
        if isinstance(raw, bool):
            return raw
        text = str(raw).strip().lower()
        if text in _TRUE_STRINGS:
            return True
        if text in _FALSE_STRINGS:
            return False
        return default

    def _write(self, key: str, value, current) -> None:
        """Guarda `value` y notifica solo si realmente cambió."""
        self._settings.setValue(key, value)
        if value != current:
            self._notify()

    def _notify(self) -> None:
        if self._batch_depth:
            self._batch_dirty = True
        else:
            signals.changed.emit()

    @contextmanager
    def batch(self):
        """Agrupa varios cambios y emite `signals.changed` una sola vez
        al salir (y solo si algo cambió), para que los paneles no se
        refresquen con estados intermedios a medio escribir."""
        self._batch_depth += 1
        try:
            yield self
        finally:
            self._batch_depth -= 1
            if self._batch_depth == 0 and self._batch_dirty:
                self._batch_dirty = False
                signals.changed.emit()

    # -- Autoguardado -------------------------------------------------- #
    @property
    def autosave_interval_ms(self) -> int:
        return self._read_int("editing/autosave_ms", DEFAULT_AUTOSAVE_MS,
                              MIN_AUTOSAVE_MS, MAX_AUTOSAVE_MS)

    @autosave_interval_ms.setter
    def autosave_interval_ms(self, value: int):
        value = _clamp(int(value), MIN_AUTOSAVE_MS, MAX_AUTOSAVE_MS)
        self._write("editing/autosave_ms", value, self.autosave_interval_ms)

    # -- Velocidad de lectura (palabras por minuto) --------------------- #
    @property
    def reading_speed_wpm(self) -> int:
        return self._read_int("editing/reading_speed_wpm", DEFAULT_READING_SPEED,
                              MIN_READING_SPEED, MAX_READING_SPEED)

    @reading_speed_wpm.setter
    def reading_speed_wpm(self, value: int):
        value = _clamp(int(value), MIN_READING_SPEED, MAX_READING_SPEED)
        self._write("editing/reading_speed_wpm", value, self.reading_speed_wpm)

    # -- Confirmar antes de borrar --------------------------------------- #
    @property
    def confirm_before_delete(self) -> bool:
        return self._read_bool("editing/confirm_delete", True)

    @confirm_before_delete.setter
    def confirm_before_delete(self, value: bool):
        self._write("editing/confirm_delete", bool(value), self.confirm_before_delete)

    # -- Fuente por defecto del editor ------------------------------------ #
    @property
    def editor_font_family(self) -> str:
        value = str(self._settings.value("editor/font_family", DEFAULT_EDITOR_FONT_FAMILY) or "")
        return value.strip() or DEFAULT_EDITOR_FONT_FAMILY

    @editor_font_family.setter
    def editor_font_family(self, value: str):
        value = (value or "").strip() or DEFAULT_EDITOR_FONT_FAMILY
        self._write("editor/font_family", value, self.editor_font_family)

    @property
    def editor_font_size(self) -> int:
        return self._read_int("editor/font_size", DEFAULT_EDITOR_FONT_SIZE,
                              MIN_EDITOR_FONT_SIZE, MAX_EDITOR_FONT_SIZE)

    @editor_font_size.setter
    def editor_font_size(self, value: int):
        value = _clamp(int(value), MIN_EDITOR_FONT_SIZE, MAX_EDITOR_FONT_SIZE)
        self._write("editor/font_size", value, self.editor_font_size)

    def reset_to_defaults(self):
        """Restaura todos los valores de configuración a sus valores iniciales
        por defecto, emitiendo `signals.changed` una única vez."""
        with self.batch():
            self.autosave_interval_ms = DEFAULT_AUTOSAVE_MS
            self.reading_speed_wpm = DEFAULT_READING_SPEED
            self.confirm_before_delete = True
            self.editor_font_family = DEFAULT_EDITOR_FONT_FAMILY
            self.editor_font_size = DEFAULT_EDITOR_FONT_SIZE


# Instancia compartida: los ajustes son globales a la aplicación (no
# por proyecto), así que un único objeto es suficiente y evita crear
# QSettings repetidamente en cada panel.
settings = AppSettings()