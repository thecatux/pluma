"""Temas de Pluma: un módulo de solo datos por tema.

Añadir un tema nuevo = crear `themes/<nombre>.py` y añadirlo a `MODULES`
(abajo). No hay que tocar `theme.py`: allí viven los cimientos (registro,
controlador, acento, plantilla QSS) y el puente con el resto de la app.

Contrato de un módulo de tema (todo en nivel de módulo; NO debe importar
`theme`, que es quien lo importa a él):

    LABEL   str   Nombre visible.                               (obligatorio)
    LIGHT   dict  Paleta del esquema claro.   (al menos una de LIGHT / DARK)
    DARK    dict  Paleta del esquema oscuro.  Si falta una, el modo
                  claro/oscuro se adapta a la que exista.
    FONT    str   Familia principal. Por defecto "Segoe UI".
    RADIUS  dict  Solo los radios que difieren de `theme.BASE_RADIUS`.

Ganchos de pintura (opcionales; un tema plano no define ninguno y su
código de pintura, si lo hubiera, nunca se ejecuta con otro tema activo).
Reciben `c` (la paleta activa) y `dark` (bool) y pintan con QPainter:

    paint_backdrop(p, rect, c, dark)                    fondo de la ventana
    paint_panel(p, bounds, body, radius, c, dark)       `theme.Panel`
    paint_pill(p, body, selected, c, dark)              `theme.SidebarItemDelegate`
    paint_sheen(p, body, radius, strength, c, dark)     reflejos de tarjetas
    SHEEN   dict  rol/"groupbox" -> (clave de RADIUS, intensidad), qué
                  widgets reciben `paint_sheen` (ver `themes/crystal.py`).
Sin gancho, `theme` pinta plano: sin fondo extra, panel con `surface` y
`border`, sin pastilla (la pinta el QSS con `sidebar_*_bg`) y sin reflejos.

Una paleta debe tener las mismas claves que la del tema por defecto (ver
`theme.DEFAULT_THEME`); si le falta alguna, el tema se omite y se avisa
en el log. Notas:
  * Las claves "clásicas" (bg, surface, border, primary...) deben ser
    colores hexadecimales planos: otros módulos (p. ej. el lienzo de la
    línea temporal) las pasan a QColor y el acento las lee como hex.
  * Un valor "@clave" es un alias a otra clave de la misma paleta (un
    solo nivel; `surface`, `text`, `on_primary` y las claves de acento no
    deben ser alias).
"""

from . import crystal, marfil, material, tinta

# Orden de registro. El nombre del tema es el nombre del módulo.
MODULES = (tinta, material, crystal, marfil)