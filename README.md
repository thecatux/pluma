# Pluma

Pluma es una aplicación de escritorio para planificar y escribir novelas por capítulos. Reúne el manuscrito y las herramientas de organización del proyecto en un mismo lugar, con una interfaz en español.

## Características

- Organiza la historia en capítulos que puedes reordenar.
- Escribe con formato de texto y guardado automático.
- Consulta el recuento de palabras y el tiempo estimado de lectura.
- Mantén fichas de personajes y escenas vinculadas a la historia.
- Organiza los acontecimientos en una línea de tiempo y guarda notas del proyecto.
- Busca y reemplaza texto en el editor.
- Elige entre temas claros y oscuros.
- Exporta capítulos seleccionados a Markdown (`.md`), texto plano (`.txt`), OpenDocument (`.odt`), PDF (`.pdf`) o Word (`.docx`). La exportación a DOCX requiere la dependencia opcional `python-docx`.

## Requisitos

- Python 3.10 o posterior.
- PySide6, instalado automáticamente con Pluma.

## Instalación desde el código fuente

Desde la carpeta del proyecto, crea y activa un entorno virtual.

Windows (PowerShell):

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS o Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Instala Pluma con el soporte opcional para DOCX:

```bash
python -m pip install -e ".[docx]"
```

Si no necesitas exportar a DOCX, puedes omitir la dependencia opcional:

```bash
python -m pip install -e .
```

## Ejecutar

Con el entorno virtual activado, inicia la aplicación desde la carpeta del proyecto:

```bash
python main.py
```

También puedes iniciar el comando instalado por el paquete:

```bash
pluma
```

Al iniciar, Pluma permite crear un proyecto o abrir uno existente.

## Datos del proyecto

Pluma almacena proyectos en una base de datos SQLite. De forma predeterminada, usa `data/pluma.db` junto a la aplicación. Si esa ubicación no permite escritura, utiliza el directorio de datos del usuario del sistema operativo. Para elegir otra ruta, configura la variable de entorno `PLUMA_DB_PATH` antes de iniciar la aplicación.

## Licencia

Pluma se distribuye bajo la licencia GNU GPL versión 3. Consulta el texto completo en [`LICENSE.txt`](LICENSE).