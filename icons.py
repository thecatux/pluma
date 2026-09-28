"""Iconos vectoriales de Pluma.

Sustituye los emoji (📄📖🧑🎬🕒🗒️⚙️✒️📚) y los símbolos Unicode sueltos
que se usaban como iconos improvisados (✕, ✓, ▸/▾, ⤢, ◇☰◈▤) por un
conjunto de iconos SVG propios, coherentes entre sí: trazo simple
("stroke", sin relleno salvo un par de detalles puntuales), esquinas
redondeadas y una rejilla de 24×24, en línea con el resto del lenguaje
visual de la app (bordes redondeados, sin sombras duras, paleta
definida en `theme.py`).

Los iconos no llevan un color fijo "de fábrica": cada icono se pide
con el color que corresponda según el tema activo (`theme.colors()`),
igual que ya hace el resto de la interfaz con `theme.signals.changed`.
Por eso este módulo expone únicamente funciones (`icon`, `pixmap`,
`dual_icon`) en lugar de una colección de QIcon precalculados: no hay
un color "correcto" sin conocer antes el tema.

Se renderizan con QSvgRenderer sobre un QPixmap el doble de grande y
`setDevicePixelRatio(2)`, para que se vean nítidos en pantallas de
alta densidad en vez de reescalar un pixmap pequeño.
"""

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer

_SVG_WRAPPER = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
    'fill="none" stroke="{color}" stroke-width="{stroke_width}" '
    'stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
)


def _gear_teeth() -> str:
    # Ocho dientes iguales, cada uno un rectángulo pequeño rotado
    # alrededor del centro (12,12): más fácil de mantener correcto a
    # mano que una silueta de engranaje dibujada como un único path.
    return "".join(
        f'<rect x="11" y="1.3" width="2" height="4.2" rx="0.6" transform="rotate({i * 45} 12 12)"/>'
        for i in range(8)
    )


# Cada entrada es el contenido interior de un <svg viewBox="0 0 24 24">.
# Los pocos elementos con relleno (los puntos de "timeline" o el punto
# de la "i" de "info") usan fill="{color}" stroke="none" para no
# heredar el trazo hueco del resto del icono.
_ICON_BODIES = {
    # -- Secciones de la barra lateral -------------------------------- #
    "info": (
        '<circle cx="12" cy="12" r="9"/>'
        '<line x1="12" y1="11" x2="12" y2="16.3"/>'
        '<circle cx="12" cy="7.6" r="0.95" fill="{color}" stroke="none"/>'
    ),
    "book": (
        '<path d="M12 6.6C10.3 5.3 7.6 4.8 5 5.3v13.3c2.6-.5 5.3 0 7 1.2 '
        '1.7-1.2 4.4-1.7 7-1.2V5.3c-2.6-.5-5.3 0-7 1.3z"/>'
        '<line x1="12" y1="6.6" x2="12" y2="19.8"/>'
    ),
    "user": (
        '<circle cx="12" cy="8.2" r="3.6"/>'
        '<path d="M5 20c0-3.7 3.1-6.3 7-6.3s7 2.6 7 6.3"/>'
    ),
    "clapper": (
        '<rect x="3.5" y="5.2" width="17" height="13.8" rx="2"/>'
        '<line x1="3.5" y1="9.2" x2="20.5" y2="9.2"/>'
        '<line x1="7.6" y1="5.2" x2="6.2" y2="9.2"/>'
        '<line x1="12.3" y1="5.2" x2="10.9" y2="9.2"/>'
        '<line x1="17" y1="5.2" x2="15.6" y2="9.2"/>'
    ),
    "timeline": (
        '<line x1="3" y1="12" x2="21" y2="12"/>'
        '<circle cx="7" cy="12" r="1.7" fill="{color}" stroke="none"/>'
        '<circle cx="12" cy="12" r="1.7" fill="{color}" stroke="none"/>'
        '<circle cx="17" cy="12" r="1.7" fill="{color}" stroke="none"/>'
    ),
    "note": (
        '<rect x="5" y="3.5" width="14" height="17" rx="2"/>'
        '<line x1="8.5" y1="3.5" x2="8.5" y2="1.6"/>'
        '<line x1="12" y1="3.5" x2="12" y2="1.6"/>'
        '<line x1="15.5" y1="3.5" x2="15.5" y2="1.6"/>'
        '<line x1="8" y1="9.2" x2="16" y2="9.2"/>'
        '<line x1="8" y1="13" x2="16" y2="13"/>'
        '<line x1="8" y1="16.8" x2="13" y2="16.8"/>'
    ),
    "settings": _gear_teeth() + '<circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="2.6"/>',

    # -- Identidad / diálogo de proyectos ------------------------------ #
    "pen": (
        '<path d="M4 20l1-4.2L15.8 5c.8-.8 2.1-.8 2.9 0l1.3 1.3c.8.8.8 2.1 0 2.9L9.2 19 4 20z"/>'
        '<line x1="14" y1="6.8" x2="17.2" y2="10"/>'
    ),
    "library": (
        '<rect x="4" y="5" width="4.2" height="15" rx="1"/>'
        '<rect x="9.4" y="3" width="4.2" height="17" rx="1"/>'
        '<rect x="14.8" y="7" width="4.2" height="13" rx="1"/>'
    ),

    # -- Iconos funcionales pequeños ------------------------------------ #
    "x": '<line x1="6" y1="6" x2="18" y2="18"/><line x1="18" y1="6" x2="6" y2="18"/>',
    "check": '<polyline points="5,13 9.5,17.5 19,7"/>',
    "chevron-right": '<polyline points="9,5 15,12 9,19"/>',
    "chevron-down": '<polyline points="5,9 12,15 19,9"/>',
    "expand": (
        '<polyline points="8,3 3,3 3,8"/><polyline points="16,3 21,3 21,8"/>'
        '<polyline points="3,16 3,21 8,21"/><polyline points="21,16 21,21 16,21"/>'
    ),

    # -- Alineación del editor de texto ---------------------------------- #
    "align-left": (
        '<line x1="4" y1="5" x2="20" y2="5"/><line x1="4" y1="10" x2="14" y2="10"/>'
        '<line x1="4" y1="15" x2="18" y2="15"/><line x1="4" y1="20" x2="11" y2="20"/>'
    ),
    "align-center": (
        '<line x1="4" y1="5" x2="20" y2="5"/><line x1="7" y1="10" x2="17" y2="10"/>'
        '<line x1="5" y1="15" x2="19" y2="15"/><line x1="8.5" y1="20" x2="15.5" y2="20"/>'
    ),
    "align-right": (
        '<line x1="4" y1="5" x2="20" y2="5"/><line x1="10" y1="10" x2="20" y2="10"/>'
        '<line x1="6" y1="15" x2="20" y2="15"/><line x1="13" y1="20" x2="20" y2="20"/>'
    ),
    "align-justify": (
        '<line x1="4" y1="5" x2="20" y2="5"/><line x1="4" y1="10" x2="20" y2="10"/>'
        '<line x1="4" y1="15" x2="20" y2="15"/><line x1="4" y1="20" x2="20" y2="20"/>'
    ),
}


def svg_markup(name: str, color: str, stroke_width: float = 1.8) -> str:
    """Devuelve el `<svg>...</svg>` completo de `name` en el color dado."""
    body = _ICON_BODIES[name].format(color=color)
    return _SVG_WRAPPER.format(color=color, stroke_width=stroke_width, body=body)


def pixmap(name: str, color: str, size: int = 20, stroke_width: float = 1.8) -> QPixmap:
    """Renderiza `name` a un QPixmap transparente de `size`x`size` px,
    con supersampling x2 (`setDevicePixelRatio`) para que se vea nítido
    también en pantallas de alta densidad."""
    scale = 2
    renderer = QSvgRenderer(QByteArray(svg_markup(name, color, stroke_width).encode("utf-8")))
    pm = QPixmap(size * scale, size * scale)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    renderer.render(painter)
    painter.end()
    pm.setDevicePixelRatio(scale)
    return pm


def icon(name: str, color: str, size: int = 20, stroke_width: float = 1.8) -> QIcon:
    """QIcon de un solo color, para botones y iconos sueltos."""
    return QIcon(pixmap(name, color, size, stroke_width))


def dual_icon(name: str, normal_color: str, selected_color: str, size: int = 20,
              stroke_width: float = 1.8) -> QIcon:
    """QIcon con un pixmap distinto para el modo `QIcon.Selected`, para
    listas donde el icono debe seguir al color de texto del estado
    seleccionado (p. ej. la barra lateral, blanca sobre azul al
    seleccionar una sección en vez de gris sobre azul)."""
    result = QIcon()
    result.addPixmap(pixmap(name, normal_color, size, stroke_width), QIcon.Normal, QIcon.Off)
    result.addPixmap(pixmap(name, selected_color, size, stroke_width), QIcon.Selected, QIcon.Off)
    return result