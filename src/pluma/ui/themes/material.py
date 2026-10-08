"""Tema "material": Material Design 3, minimalista y plano.

Superficies planas con jerarquía tonal (sin degradados ni translúcidos),
contornos finos, botones en píldora y campos con esquina de 4 px.
Colores tipo M3 con semilla verde petróleo para conservar la identidad
de Pluma (ajustados a mano, no generados con Material Theme Builder).

Módulo de solo datos: no importa Qt ni `theme`. Ver `themes/__init__.py`
para el contrato que debe cumplir cualquier tema.
"""

LABEL = "Material"
FONT = "Roboto"   # si no está instalada, Qt usa FONT_FALLBACK de `theme`
# Solo lo que difiere de `theme.BASE_RADIUS`.
RADIUS = {"sm": 4, "button": 20, "field": 4, "chip": 8, "nav": 20}

# Los roles de cristal se reutilizan como alias ("@clave") de color plano:
# así el mismo QSS sirve para todos los temas y el acento del usuario se
# propaga (los alias se resuelven DESPUÉS de aplicar el acento).
_ROLES = {
    "primary_rim": "@primary",
    "bg_gradient": "@bg",
    "glass": "@surface_alt",
    "glass_subtle": "@surface_alt",
    "glass_border": "@border",
    "bar_glass": "@bg",
    "card_glass": "@surface",
    "button_glass": "transparent",          # botón "outlined"
    "button_glass_hover": "@primary_light", # capa de estado
    "rim_top": "@border",
    "sidebar_bg_hover": "@glass_hover",
    "sidebar_bg_selected": "@primary_light",
    "sidebar_text": "@text_secondary",
    "sidebar_text_muted": "@text_muted",
    "sidebar_text_selected": "@primary_text",
    "sidebar_title": "@text",
    "sidebar_glass": "@sidebar_bg",
    "sidebar_edge": "@border",
    "sidebar_item_hover": "@glass_hover",
    "sidebar_item_selected": "@primary_light",
    "sidebar_item_selected_border": "@primary_border",
    "sidebar_hover_bg": "@glass_hover",
    "sidebar_selected_bg": "@primary_light",  # pastilla de navegación activa
}

LIGHT = {**_ROLES,
    "bg": "#F4FBF8", "surface": "#FFFFFF", "surface_alt": "#E9F0ED",
    "border": "#D3DDD9", "border_strong": "#6F7976", "glass_hover": "#DDE5E2",
    "text": "#161D1B", "text_secondary": "#3F4946", "text_muted": "#6F7976",
    "primary": "#006A60", "primary_hover": "#005B52", "primary_pressed": "#004D45",
    "primary_light": "#CCE8E2", "primary_border": "#9FCBC4",
    "primary_text": "#05201C", "on_primary": "#FFFFFF",
    "danger": "#BA1A1A", "danger_hover": "#93000A", "danger_light": "#FFDAD6",
    "success": "#1B6D3A",
    "sidebar_bg": "#EEF5F2",
}

DARK = {**_ROLES,
    "bg": "#0E1513", "surface": "#161D1B", "surface_alt": "#212826",
    "border": "#3F4946", "border_strong": "#899390", "glass_hover": "#2B3230",
    "text": "#DEE4E1", "text_secondary": "#BEC9C5", "text_muted": "#899390",
    "primary": "#53DBC9", "primary_hover": "#74F8E5", "primary_pressed": "#3EC2B1",
    "primary_light": "#334B47", "primary_border": "#4B6360",
    "primary_text": "#CCE8E2", "on_primary": "#003731",
    "danger": "#FFB4AB", "danger_hover": "#FFDAD6", "danger_light": "#4A1F1C",
    "success": "#7FD99A",
    "sidebar_bg": "#121A18",
}