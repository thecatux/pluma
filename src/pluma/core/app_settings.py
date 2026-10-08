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
DEFAULT_EDITOR_FONT_SIZE = 12


class _SettingsSignals(QObject):
    """Señales globales para notificar cambios en la configuración de la aplicación."""
    changed = Signal()


signals = _SettingsSignals()


class AppSettings:
    """Wrapper fino sobre QSettings con valores por defecto y validación.
    No mantiene estado propio en memoria: cada lectura va a QSettings,
    así que distintas instancias (o el mismo objeto tras un cambio
    externo) siempre ven el valor vigente.
    """

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

    # -- Autoguardado -------------------------------------------------- #
    @property
    def autosave_interval_ms(self) -> int:
        value = self._settings.value("editing/autosave_ms", DEFAULT_AUTOSAVE_MS, type=int)
        return max(MIN_AUTOSAVE_MS, min(MAX_AUTOSAVE_MS, value))

    @autosave_interval_ms.setter
    def autosave_interval_ms(self, value: int):
        value = max(MIN_AUTOSAVE_MS, min(MAX_AUTOSAVE_MS, int(value)))
        self._settings.setValue("editing/autosave_ms", value)
        signals.changed.emit()

    # -- Velocidad de lectura (palabras por minuto) --------------------- #
    @property
    def reading_speed_wpm(self) -> int:
        value = self._settings.value("editing/reading_speed_wpm", DEFAULT_READING_SPEED, type=int)
        return max(MIN_READING_SPEED, min(MAX_READING_SPEED, value))

    @reading_speed_wpm.setter
    def reading_speed_wpm(self, value: int):
        value = max(MIN_READING_SPEED, min(MAX_READING_SPEED, int(value)))
        self._settings.setValue("editing/reading_speed_wpm", value)
        signals.changed.emit()

    # -- Confirmar antes de borrar --------------------------------------- #
    @property
    def confirm_before_delete(self) -> bool:
        return self._settings.value("editing/confirm_delete", True, type=bool)

    @confirm_before_delete.setter
    def confirm_before_delete(self, value: bool):
        self._settings.setValue("editing/confirm_delete", bool(value))
        signals.changed.emit()

    # -- Fuente por defecto del editor ------------------------------------ #
    @property
    def editor_font_family(self) -> str:
        return self._settings.value("editor/font_family", DEFAULT_EDITOR_FONT_FAMILY, type=str)

    @editor_font_family.setter
    def editor_font_family(self, value: str):
        self._settings.setValue("editor/font_family", value or DEFAULT_EDITOR_FONT_FAMILY)
        signals.changed.emit()

    @property
    def editor_font_size(self) -> int:
        value = self._settings.value("editor/font_size", DEFAULT_EDITOR_FONT_SIZE, type=int)
        return max(6, min(72, value))

    @editor_font_size.setter
    def editor_font_size(self, value: int):
        value = max(6, min(72, int(value)))
        self._settings.setValue("editor/font_size", value)
        signals.changed.emit()

    def reset_to_defaults(self):
        """Restaura todos los valores de configuración a sus valores iniciales por defecto."""
        self.autosave_interval_ms = DEFAULT_AUTOSAVE_MS
        self.reading_speed_wpm = DEFAULT_READING_SPEED
        self.confirm_before_delete = True
        self.editor_font_family = DEFAULT_EDITOR_FONT_FAMILY
        self.editor_font_size = DEFAULT_EDITOR_FONT_SIZE


# Instancia compartida: los ajustes son globales a la aplicación (no
# por proyecto), así que un único objeto es suficiente y evita crear
# QSettings repetidamente en cada panel.
settings = AppSettings()