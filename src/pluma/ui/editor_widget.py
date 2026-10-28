"""Widget de edición de texto enriquecido reutilizable para Pluma.

Proporciona soporte completo para estilos tipográficos (negrita, cursiva,
subrayado, tachado), alineación de párrafos, tipografía, tamaño de fuente,
color y caracteres especiales/literarios.

Expone la señal contentChanged para que el anfitrión autoguarde en la base de
datos SQLite sin necesidad de sondeo activo.

Principios de diseño:
  - Un bloque puede quedarse sin ningún carácter del que Qt tome el
    charFormat de dos formas: segundo Enter seguido sobre un bloque ya
    vacío, o Backspace/Delete borrando el último carácter que le quedaba
    a un bloque. En ambos casos Qt cae al formato por defecto del
    documento — pero solo AL EJECUTAR esa tecla: el charFormat del
    cursor es correcto un instante antes. _FormatCarryingTextEdit por
    eso captura el charFormat justo antes de Enter/Backspace/Delete y lo
    reaplica después con mergeCurrentCharFormat(). Es un valor local a
    esa posición exacta del cursor, no un registro global ni el default
    de la app, así que editar una zona vieja del documento con otra
    fuente nunca se ve afectado por cambios hechos en otra parte. Enter
    también conserva la alineación del bloque actual en el nuevo bloque,
    sin usar setAlignment() dentro de keyPressEvent.
  - Los combos de fuente y tamaño se actualizan visualmente desde
    currentCharFormatChanged, bloqueando sus señales para que la
    sincronización no dispare una escritura en el documento.
  - La señal activated del combo de fuente (solo se emite cuando el
    usuario selecciona un ítem manualmente) se usa para aplicar el
    cambio al documento, en lugar de currentFontChanged que también
    se dispara con actualizaciones programáticas.
"""

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Optional

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QTextEdit, QFontComboBox,
                                QComboBox, QColorDialog, QToolBar, QToolButton, QMenu)
from PySide6.QtGui import (QAction, QKeySequence, QFont, QTextCharFormat, QActionGroup, QTextCursor, QIcon,
                           QShortcut)
from PySide6.QtCore import Qt, QSize, Signal

from pluma.ui import icons, theme
from pluma.ui.find_replace import FindReplaceBar


@dataclass(frozen=True)
class _CharFormatToggle:
    """Configuración descriptiva de una acción de conmutación de formato de carácter."""
    key: str
    label: str
    shortcut: Any
    status_tip: str
    getter: Callable[[QTextCharFormat], bool]
    setter: Callable[[QTextCharFormat, bool], None]


@dataclass(frozen=True)
class _AlignmentOption:
    """Configuración de una opción de alineación de texto."""
    label: str
    alignment: Qt.AlignmentFlag
    status_tip: str


@dataclass(frozen=True)
class _SpecialChar:
    """Una entrada del menú de caracteres especiales.

    close_text vacío significa insertar solo open_text en el cursor;
    si tiene valor, se trata como un par que envuelve la selección
    actual (o, sin selección, se insertan ambos y el cursor queda
    entre medias, listo para escribir dentro).
    """
    key: str
    menu_label: str
    status_tip: str
    open_text: str
    close_text: str = ""


class _FormatCarryingTextEdit(QTextEdit):
    """QTextEdit que nunca deja que Enter, Backspace o Delete tiren el
    formato al default del documento.

    Qt hereda el charFormat correctamente cuando hay un carácter del que
    tomarlo, pero se rompe justo en el instante en que una operación deja
    el bloque sin ningún carácter: el segundo Enter seguido sobre un
    bloque ya vacío, o Backspace/Delete borrando el último carácter que
    le quedaba a un bloque. Verificado con Qt real: el charFormat del
    cursor es correcto un instante ANTES de esa tecla, y es Qt quien lo
    resetea al default durante la propia operación (insertBlock /
    borrado). Por eso alcanza con capturar el charFormat del cursor justo
    antes de la tecla y reaplicarlo después con mergeCurrentCharFormat().

    Es un valor puramente local y momentáneo (el que ya estaba ahí mismo,
    en esa posición exacta del documento) — no un valor global ni el
    default de la app — así que nunca puede "pisar" con un formato ajeno
    una zona distinta del documento, sea cual sea el orden en que el
    usuario edite.

    La alineación se restaura modificando el formato del bloque con el
    cursor, no mediante setAlignment(), que puede hacer que Qt ignore
    silenciosamente el siguiente Enter.
    """

    _DELETE_LIKE_KEYS = (Qt.Key_Backspace, Qt.Key_Delete)

    def keyPressEvent(self, event):
        """Maneja pulsaciones de teclado asegurando la preservación del formato al saltar líneas o borrar."""
        key = event.key()
        if key in (Qt.Key_Return, Qt.Key_Enter):
            self._insert_block_carrying_format()
            return
        if key not in self._DELETE_LIKE_KEYS:
            super().keyPressEvent(event)
            return
        cursor = self.textCursor()
        fmt = cursor.charFormat()
        if key == Qt.Key_Delete and not cursor.hasSelection() and not cursor.atBlockEnd():
            next_char = QTextCursor(cursor)
            next_char.movePosition(QTextCursor.NextCharacter, QTextCursor.KeepAnchor)
            fmt = next_char.charFormat()
        cursor.beginEditBlock()
        try:
            super().keyPressEvent(event)
            if not self.textCursor().block().text():
                self.mergeCurrentCharFormat(fmt)
        finally:
            cursor.endEditBlock()

    def _insert_block_carrying_format(self):
        """Inserta el salto de parrafo de forma atomica, con el
        charFormat y la alineacion ya fijados en la misma llamada.

        Nunca delega en QTextEdit para Enter: dejar que Qt cree el
        bloque y "arreglarlo" despues (mergeCurrentCharFormat +
        cursor.setBlockFormat sobre el bloque ya vacio) deja el
        control de texto en un estado roto que ignora en silencio
        todo Enter posterior. cursor.insertBlock(blockFormat,
        charFormat) evita ese estado por completo y de paso borra la
        seleccion si la habia, igual que el Enter nativo.
        """
        cursor = self.textCursor()
        cursor.insertBlock(cursor.blockFormat(), cursor.charFormat())
        self.setTextCursor(cursor)


class RichTextEditor(QWidget):
    """Widget de edición de texto enriquecido, reutilizable como componente."""

    modificationChanged = Signal(bool)
    contentChanged = Signal()

    MIN_FONT_SIZE = 1
    MAX_FONT_SIZE = 400

    _CHAR_FORMATS = (
        _CharFormatToggle("bold", "Negrita", QKeySequence.Bold, "Aplicar negrita",
                           lambda f: f.fontWeight() >= QFont.Bold,
                           lambda f, on: f.setFontWeight(QFont.Bold if on else QFont.Normal)),
        _CharFormatToggle("italic", "Cursiva", QKeySequence.Italic, "Aplicar cursiva",
                           lambda f: f.fontItalic(),
                           lambda f, on: f.setFontItalic(on)),
        _CharFormatToggle("underline", "Subrayado", QKeySequence.Underline, "Aplicar subrayado",
                           lambda f: f.fontUnderline(),
                           lambda f, on: f.setFontUnderline(on)),
        _CharFormatToggle("strike", "Tachado", "Ctrl+Shift+X", "Aplicar tachado",
                           lambda f: f.fontStrikeOut(),
                           lambda f, on: f.setFontStrikeOut(on)),
    )

    _ALIGNMENTS = (
        _AlignmentOption("Alinear izquierda", Qt.AlignLeft, "Alinear a la izquierda"),
        _AlignmentOption("Centrar", Qt.AlignCenter, "Centrar texto"),
        _AlignmentOption("Alinear derecha", Qt.AlignRight, "Alinear a la derecha"),
        _AlignmentOption("Justificar", Qt.AlignJustify, "Justificar texto"),
    )

    _ALIGN_ICON_NAMES = {
        "Alinear izquierda": "align-left",
        "Centrar": "align-center",
        "Alinear derecha": "align-right",
        "Justificar": "align-justify",
    }

    # La raya de diálogo es la acción por defecto del botón (ver
    # create_special_chars_button); el resto vive en el desplegable.
    DEFAULT_SPECIAL_CHAR_KEY = "dash_em"

    _SPECIAL_CHARS = (
        _SpecialChar("dash_em", "—   Raya (diálogo)", "Raya de diálogo", "—"),
        _SpecialChar("dash_en", "–   Guion medio", "Guion medio (incisos, rangos de páginas o años)", "–"),
        _SpecialChar("ellipsis", "…   Puntos suspensivos", "Puntos suspensivos", "…"),
        _SpecialChar("quotes_angular", "« »   Comillas angulares", "Comillas angulares (uso habitual en narrativa)", "«", "»"),
        _SpecialChar("quotes_double", "“ ”   Comillas inglesas", "Comillas tipográficas dobles", "“", "”"),
        _SpecialChar("quotes_single", "‘ ’   Comillas simples", "Comillas tipográficas simples", "‘", "’"),
        _SpecialChar("inverted_question", "¿ ?   Interrogación", "Envuelve la pregunta con ¿ y ?", "¿", "?"),
        _SpecialChar("inverted_exclamation", "¡ !   Exclamación", "Envuelve la frase con ¡ y !", "¡", "!"),
        _SpecialChar("n_tilde_lower", "ñ", "Eñe minúscula", "ñ"),
        _SpecialChar("n_tilde_upper", "Ñ", "Eñe mayúscula", "Ñ"),
        _SpecialChar("u_diaeresis_lower", "ü", "U con diéresis (güe, güi...)", "ü"),
        _SpecialChar("u_diaeresis_upper", "Ü", "Ü mayúscula", "Ü"),
        _SpecialChar("a_acute", "á", "A con tilde", "á"),
        _SpecialChar("e_acute", "é", "E con tilde", "é"),
        _SpecialChar("i_acute", "í", "I con tilde", "í"),
        _SpecialChar("o_acute", "ó", "O con tilde", "ó"),
        _SpecialChar("u_acute", "ú", "U con tilde", "ú"),
    )

    def __init__(self, parent=None, *, placeholder: str = ""):
        """Inicializa el editor de texto enriquecido, sus atajos de teclado y la barra de búsqueda."""
        super().__init__(parent)
        self._char_format_by_key = {fmt.key: fmt for fmt in self._CHAR_FORMATS}

        self.text_edit = _FormatCarryingTextEdit(self)
        self.text_edit.setAcceptRichText(True)
        if placeholder:
            self.text_edit.setPlaceholderText(placeholder)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.text_edit)

        self._create_actions()

        # Panel flotante de buscar/reemplazar: hijo del editor, fuera del
        # layout (no altera la interfaz). Ctrl+F / Ctrl+H solo actúan con
        # el foco dentro de este editor.
        self.find_bar = FindReplaceBar(self, self.text_edit)
        for sequence, replace in (("Ctrl+F", False), ("Ctrl+H", True)):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(lambda replace=replace: self.find_bar.open_bar(replace))

        self.text_edit.document().modificationChanged.connect(self.modificationChanged)
        self.text_edit.textChanged.connect(self.contentChanged)

        # currentCharFormatChanged solo se dispara cuando el formato en el cursor
        # cambia de verdad (negrita, fuente, tamano...). Asi los combos se
        # actualizan unicamente cuando hay un cambio real, sin procesamiento
        # extra en cada pulsacion de tecla.
        # La alineacion se comprueba en cada movimiento del cursor porque
        # consultarla es barato (una sola llamada a alignment()).
        self.text_edit.currentCharFormatChanged.connect(self._sync_format_actions)
        self.text_edit.cursorPositionChanged.connect(self._sync_alignment_action)

        self._sync_format_actions()
        self._sync_alignment_action()

        self._refresh_align_icons()
        theme.signals.changed.connect(self._refresh_align_icons)

    # ------------------------------------------------------------------ #
    # Creacion de acciones
    # ------------------------------------------------------------------ #
    def _make_action(self, text, shortcut=None, status_tip=None, triggered=None, checkable=False):
        """Crea y configura una instancia de QAction con atajos y pistas de estado."""
        action = QAction(text, self)
        if shortcut is not None:
            action.setShortcut(shortcut)
            action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            self.addAction(action)
        if status_tip is not None:
            action.setStatusTip(status_tip)
            tooltip = status_tip
            if shortcut is not None:
                seq = QKeySequence(shortcut)
                if not seq.isEmpty():
                    tooltip = f"{status_tip} ({seq.toString()})"
            action.setToolTip(tooltip)
        if checkable:
            action.setCheckable(True)
        if triggered is not None:
            action.triggered.connect(triggered)
        return action

    def _create_actions(self):
        """Crea las acciones de formato de texto, alineación, color y búsqueda."""
        self.char_format_actions = {}
        for fmt in self._CHAR_FORMATS:
            self.char_format_actions[fmt.key] = self._make_action(
                fmt.label, fmt.shortcut, fmt.status_tip,
                lambda checked, key=fmt.key: self._apply_char_format(key, checked),
                checkable=True)

        self.align_group = QActionGroup(self)
        self.align_group.setExclusive(True)
        self.align_actions = {}
        for opt in self._ALIGNMENTS:
            action = self._make_action(
                opt.label, None, opt.status_tip,
                lambda checked, alignment=opt.alignment: self.set_alignment(alignment),
                checkable=True)
            self.align_group.addAction(action)
            self.align_actions[opt.alignment] = action

        self.color_action = self._make_action("Color de fuente…", None,
                                               "Cambiar el color de la fuente", self.choose_font_color)

        self.search_action = self._make_action("Buscar", None, "Buscar y reemplazar (Ctrl+F)",
                                               lambda *_: self.find_bar.open_bar())

        self.font_combo = QFontComboBox()
        self.font_combo.setStatusTip("Seleccione tipo de fuente")
        self.font_combo.setMinimumWidth(170)
        self.font_combo.setMinimumHeight(32)
        self.font_combo.setMaximumWidth(220)
        # Se usa activated (solo emitida por accion del usuario, nunca por cambios
        # programaticos) en lugar de currentFontChanged (que tambien se dispararia
        # al sincronizar el combo desde codigo y causaria que la sincronizacion
        # escribiera en el documento, revirtiendo la fuente a un valor incorrecto).
        self.font_combo.activated.connect(
            lambda _index: self.set_font_family(self.font_combo.currentFont())
        )

        self.size_combo = QComboBox()
        self.size_combo.setStatusTip("Selecciona tamano de fuente")
        self.size_combo.setEditable(True)
        self.size_combo.setMinimumWidth(76)
        self.size_combo.setMinimumHeight(32)
        self.size_combo.addItems([str(i) for i in range(6, 73, 2)])
        self.size_combo.setCurrentText("12")
        # textActivated tambien es una senal de solo-usuario; no se emite al
        # cambiar el texto programaticamente con setCurrentText.
        self.size_combo.textActivated.connect(self.set_font_size)
        self.size_combo.lineEdit().editingFinished.connect(
            lambda: self.set_font_size(self.size_combo.currentText())
        )

    _TOOLBAR_GLYPHS = {"bold": "N", "italic": "C", "underline": "S", "strike": "T"}

    def create_format_toolbar(self, parent=None) -> QToolBar:
        """Construye y devuelve una barra de herramientas lista con todos los controles de formato."""
        toolbar = QToolBar("Formato de caracteres", parent)
        toolbar.setIconSize(QSize(16, 16))
        toolbar.setToolButtonStyle(Qt.ToolButtonTextOnly)

        for fmt in self._CHAR_FORMATS:
            action = self.char_format_actions[fmt.key]
            action.setText(self._TOOLBAR_GLYPHS[fmt.key])
            toolbar.addWidget(self._glyph_button(action, fmt.key))

        toolbar.addSeparator()
        for opt in self._ALIGNMENTS:
            action = self.align_actions[opt.alignment]
            action.setText("")
            toolbar.addWidget(self._icon_only_button(action))
        toolbar.addSeparator()
        toolbar.addWidget(self.create_special_chars_button(toolbar))
        toolbar.addSeparator()
        toolbar.addWidget(self.font_combo)
        toolbar.addWidget(self.size_combo)
        toolbar.addWidget(self._icon_only_button(self.color_action))
        toolbar.addWidget(self._icon_only_button(self.search_action))
        return toolbar

    def _icon_only_button(self, action: QAction) -> QToolButton:
        """Crea un botón de barra de herramientas que solo muestra su icono."""
        button = QToolButton()
        button.setDefaultAction(action)
        button.setToolButtonStyle(Qt.ToolButtonIconOnly)
        return button

    def _refresh_align_icons(self, *_args):
        """Actualiza los iconos de alineación, paleta y búsqueda según el tema activo."""
        c = theme.colors()
        for opt in self._ALIGNMENTS:
            action = self.align_actions[opt.alignment]
            name = self._ALIGN_ICON_NAMES[opt.label]
            align_icon = QIcon()
            align_icon.addPixmap(icons.pixmap(name, c["text"], size=16), QIcon.Normal, QIcon.Off)
            align_icon.addPixmap(icons.pixmap(name, c["primary_text"], size=16), QIcon.Normal, QIcon.On)
            action.setIcon(align_icon)
        self.color_action.setIcon(icons.icon("palette", c["text"], size=16))
        self.search_action.setIcon(icons.icon("search", c["text"], size=16))

    def _glyph_button(self, action: QAction, key: str):
        """Crea un botón tipográfico con estilo propio (negrita, cursiva, subrayado o tachado)."""
        button = QToolButton()
        button.setDefaultAction(action)
        font = button.font()
        font.setBold(key == "bold")
        font.setItalic(key == "italic")
        font.setUnderline(key == "underline")
        font.setStrikeOut(key == "strike")
        font.setPointSize(11)
        button.setFont(font)
        return button

    # ------------------------------------------------------------------ #
    # Caracteres especiales
    # ------------------------------------------------------------------ #
    def create_special_chars_button(self, parent=None) -> QToolButton:
        """Botón con menú desplegable para insertar caracteres que no
        están a mano en muchos teclados: comillas tipográficas, rayas,
        signos de apertura y vocales/eñe acentuadas. Pulsar el cuerpo
        del botón inserta directamente la raya de diálogo (—), que es
        la acción por defecto; la flechita abre el resto de opciones.
        """
        default_spec = self._special_char_by_key(self.DEFAULT_SPECIAL_CHAR_KEY)

        button = QToolButton(parent)
        button.setPopupMode(QToolButton.MenuButtonPopup)
        button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        button.setCursor(Qt.PointingHandCursor)

        default_action = self._make_action(
            default_spec.open_text, None,
            f"{default_spec.status_tip} — botón: inserta directamente; flecha: más caracteres",
            lambda checked=False, s=default_spec: self._insert_special_char(s))
        button.setDefaultAction(default_action)

        menu = QMenu(button)
        self.special_char_actions = {}
        for spec in self._SPECIAL_CHARS:
            action = QAction(spec.menu_label, self)
            action.setStatusTip(spec.status_tip)
            action.setToolTip(spec.status_tip)
            action.triggered.connect(lambda checked=False, s=spec: self._insert_special_char(s))
            menu.addAction(action)
            self.special_char_actions[spec.key] = action
        button.setMenu(menu)

        return button

    def _special_char_by_key(self, key: str) -> _SpecialChar:
        """Busca y devuelve la definición de un carácter especial por su clave."""
        return next(spec for spec in self._SPECIAL_CHARS if spec.key == key)

    def _insert_special_char(self, spec: _SpecialChar):
        """Inserta el carácter especial o envuelve la selección actual."""
        cursor = self.text_edit.textCursor()
        if spec.close_text:
            # Caracteres emparejados (comillas, ¿?, ¡!): si hay texto seleccionado
            # lo envuelven; si no, se insertan los dos y el cursor queda listo
            # entre medias para escribir dentro.
            if cursor.hasSelection():
                selection_start = cursor.selectionStart()
                selection_end = cursor.selectionEnd()
                cursor.setPosition(selection_end)
                cursor.insertText(spec.close_text)
                cursor.setPosition(selection_start)
                cursor.insertText(spec.open_text)
                cursor.setPosition(selection_end + len(spec.open_text) + len(spec.close_text))
            else:
                start = cursor.position()
                cursor.insertText(f"{spec.open_text}{spec.close_text}")
                cursor.setPosition(start + len(spec.open_text))
        else:
            cursor.insertText(spec.open_text)
        # insertText sobre una copia del cursor edita el documento,
        # pero hay que reasignarla explicitamente para que el cursor
        # parpadeante del widget adopte la posicion resultante.
        self.text_edit.setTextCursor(cursor)
        self.text_edit.setFocus()

    # ------------------------------------------------------------------ #
    # Aplicacion de formato
    # ------------------------------------------------------------------ #
    def _merge_format(self, configure: Callable[[QTextCharFormat], None]):
        """Aplica un fragmento de formato al cursor actual.

        Si hay seleccion, el formato se aplica sobre ella; si no, queda
        como formato del proximo caracter que se escriba. En ningun caso
        se toca el resto del documento.
        """
        fmt = QTextCharFormat()
        configure(fmt)
        self.text_edit.mergeCurrentCharFormat(fmt)
        if not self._format_control_has_focus():
            self.text_edit.setFocus()

    def _apply_char_format(self, key, checked):
        """Aplica o desaplica un formato de carácter específico (negrita, cursiva, etc.)."""
        fmt_spec = self._char_format_by_key[key]
        self._merge_format(lambda f: fmt_spec.setter(f, checked))

    def set_alignment(self, alignment):
        """Alinea el párrafo o bloque actual según el indicador Qt especificado."""
        self.text_edit.setAlignment(alignment)
        self.text_edit.setFocus()

    def set_font_family(self, font: QFont):
        """Establece la familia tipográfica en la selección o posición del cursor."""
        # setFontFamilies es la API correcta en Qt6; setFontFamily esta
        # marcado como obsoleto y puede ignorarse en versiones futuras.
        self._merge_format(lambda f: f.setFontFamilies([font.family()]))

    def set_font_size(self, size_text):
        """Aplica un nuevo tamaño en puntos a la selección o cursor si es válido."""
        text = str(size_text).strip() if size_text is not None else ""
        if not text:
            return
        try:
            size = float(text)
        except ValueError:
            return
        if not (self.MIN_FONT_SIZE <= size <= self.MAX_FONT_SIZE):
            return
        self._merge_format(lambda f: f.setFontPointSize(size))

    def _format_control_has_focus(self) -> bool:
        """Comprueba si alguno de los controles de selección de fuente o tamaño tiene el foco."""
        controls = (self.font_combo, self.size_combo)
        return any(
            control.hasFocus()
            or (control.lineEdit() is not None and control.lineEdit().hasFocus())
            for control in controls
        )

    def choose_font_color(self):
        """Abre un diálogo selector de color y aplica el color escogido al texto."""
        color = QColorDialog.getColor(self.text_edit.textColor(), self, "Seleccionar color de fuente")
        if color.isValid():
            self._merge_format(lambda f: f.setForeground(color))

    def _sync_format_actions(self, char_format: Optional[QTextCharFormat] = None):
        """Actualiza los controles de la barra de formato para que reflejen
        el formato en la posicion actual del cursor.

        Se llama desde currentCharFormatChanged (con el formato ya resuelto)
        o manualmente sin argumento (lee el formato del cursor). En ambos
        casos el formato es el efectivo, heredado del bloque o del documento
        si el caracter no fija uno propio.
        """
        if char_format is None:
            char_format = self.text_edit.currentCharFormat()

        for fmt in self._CHAR_FORMATS:
            self.char_format_actions[fmt.key].setChecked(fmt.getter(char_format))

        # currentFont() y fontPointSize() del QTextEdit ya tienen en cuenta la
        # fuente por defecto del documento cuando el caracter no fija una propia,
        # evitando saltos bruscos a una familia o tamano de sistema al moverse
        # por texto sin formato explicito.
        # Las senales de los combos se bloquean (capa de seguridad extra) para
        # que la actualizacion visual no dispare ningun slot de escritura, aunque
        # ya estan conectados solo a senales de usuario (activated/textActivated).
        if not self.font_combo.hasFocus():
            with self._signals_blocked(self.font_combo):
                self.font_combo.setCurrentFont(self.text_edit.currentFont())

        if not self.size_combo.hasFocus():
            size = self.text_edit.fontPointSize()
            if size > 0:
                with self._signals_blocked(self.size_combo):
                    self.size_combo.setCurrentText(format(size, "g"))

    def _sync_alignment_action(self):
        """Sincroniza los botones de alineación con la alineación del bloque actual."""
        alignment = self.text_edit.alignment()
        for opt in self._ALIGNMENTS:
            self.align_actions[opt.alignment].setChecked(alignment == opt.alignment)

    @staticmethod
    @contextmanager
    def _signals_blocked(*widgets):
        """Context manager para bloquear temporalmente las señales de uno o más widgets."""
        previous = [(widget, widget.blockSignals(True)) for widget in widgets]
        try:
            yield
        finally:
            for widget, was_blocked in previous:
                widget.blockSignals(was_blocked)

    # ------------------------------------------------------------------ #
    # Fuente por defecto (configurable desde Ajustes)
    # ------------------------------------------------------------------ #
    def apply_default_font(self, family: str, size: int):
        """Fija la fuente con la que arranca el editor (para texto nuevo
        o vacio). El texto ya escrito conserva su propio formato de
        caracter, asi que esto no reescribe el documento existente."""
        font = QFont(family)
        font.setPointSize(size)
        self.text_edit.setFont(font)
        with self._signals_blocked(self.font_combo, self.size_combo):
            self.font_combo.setCurrentFont(font)
            self.size_combo.setCurrentText(str(size))

    # ------------------------------------------------------------------ #
    # Contenido (HTML) - usado por el anfitrión para cargar/guardar en BD
    # ------------------------------------------------------------------ #
    def to_html(self) -> str:
        """Devuelve el contenido actual del editor en formato HTML."""
        return self.text_edit.toHtml()

    def set_html(self, html: str):
        """Carga contenido HTML en el editor reseteando el estado de modificación."""
        with self._signals_blocked(self.text_edit):
            self.text_edit.setHtml(html or "")
        self.text_edit.document().setModified(False)
        self._sync_format_actions()
        self._sync_alignment_action()

    def word_count(self) -> int:
        """Calcula el número de palabras en el documento actual."""
        text = self.text_edit.toPlainText()
        return len(text.split())