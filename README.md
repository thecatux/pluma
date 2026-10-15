# Pluma

Pluma es una aplicación de escritorio para planificar y escribir novelas por capítulos. Reúne el manuscrito y las herramientas de organización del proyecto en un mismo lugar, con una interfaz en español.

## Características

- Organiza la historia en capítulos que puedes reordenar.
- Escribe con formato de texto y guardado automático.
- Consulta el recuento de palabras y el tiempo estimado de lectura.
- Mantén fichas de personajes y escenas vinculadas a la historia.
- Organiza los acontecimientos en una línea de tiempo y guarda notas de la historia.
- Busca y reemplaza texto en el editor.
- Elige entre temas claros y oscuros.
- Exporta capítulos seleccionados a Markdown (`.md`), texto plano (`.txt`), OpenDocument (`.odt`), PDF (`.pdf`) o Word (`.docx`).

## Requisitos

- Python 3.10 o posterior.
- PySide6.
- python-docx (opcional, habilita la exportación a `.docx`).

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

Actualiza `pip` e instala Pluma en modo editable:

```bash
python -m pip install --upgrade pip
python -m pip install -e .
```

Si también quieres exportar documentos DOCX, instala la dependencia opcional:

```bash
python -m pip install -e ".[docx]"
```

Si prefieres instalar desde el archivo de dependencias del proyecto:

```bash
python -m pip install -r requirements.txt
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

## Compilación

Pluma se compila con [Nuitka](https://github.com/nuitka/nuitka) en modo onefile desde la raíz del proyecto. Los pasos recomendados son los siguientes:

### 1) Preparar el entorno

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r .\requirements.txt
```

Si no tienes un archivo `requirements.txt`, instala primero las dependencias del proyecto:

```powershell
python -m pip install -e .
python -m pip install nuitka
```

### 2) Generar el sello de build

Antes de compilar, genera el archivo `src/pluma/core/_build_stamp.py` con la fecha y el número de build del repositorio. Esto evita que el ejecutable quede con metadatos antiguos o vacíos.

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
python .\stamp_build.py
```

### 3) Limpiar salidas anteriores

Para evitar que cualquiera de los datos o artefactos antiguos afecten a la compilación nueva, borra la salida anterior de Nuitka antes de volver a compilar:

```powershell
$old = @(
    ".\dist-onefile\Pluma.exe",
    ".\dist-onefile\main.build",
    ".\dist-onefile\main.dist",
    ".\dist-onefile\main.onefile-build",
    ".\dist-onefile\nuitka-report.xml"
)
Remove-Item -LiteralPath $old -Recurse -Force -ErrorAction SilentlyContinue

# Si quieres una compilación limpia y sin datos previos:
Remove-Item -LiteralPath .\dist-onefile\data -Recurse -Force -ErrorAction SilentlyContinue
```

> Nota: si la aplicación usa una base de datos en `data/pluma.db`, conservar esa carpeta puede hacer que una ejecución anterior deje datos viejos. Bórrala si quieres probar un entorno totalmente limpio.

### 4) Compilar con Nuitka

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
.\.venv\Scripts\nuitka.cmd --onefile --enable-plugin=pyside6 --include-package=pluma --include-data-dir=assets=assets --windows-icon-from-ico=assets/icon_256.ico --output-dir=dist-onefile --output-filename=Pluma.exe --report=dist-onefile\nuitka-report.xml --windows-console-mode=disable .\main.py
```

### 5) Verificar que Nuitka use `src` y no lo ignore

El comando anterior fuerza la inclusión del paquete `pluma` y establece `PYTHONPATH` con `src`, así que Nuitka no depende de que el proyecto se encuentre en otra ruta. Para comprobar el informe de compilación:

```powershell
if (Select-String -Path .\dist-onefile\nuitka-report.xml -Pattern 'src[\\/]+pluma' -Quiet) {
    "OK: el informe registra módulos bajo src/pluma"
} else {
    throw "No se encontró src/pluma en el informe de Nuitka"
}
```

### 6) Notas importantes y problemas frecuentes

- Si la ventana del programa no muestra el icono esperado, no basta con incluir `assets`; el ejecutable también debe recibir `--windows-icon-from-ico=assets/icon_256.ico`.
- Si el programa se compila pero no arranca, revisa que el paquete `pluma` aparezca en el informe y que el entorno tenga `PySide6` instalado.
- Si se reutiliza una base de datos antigua, borra `dist-onefile\data` o la ruta configurada en `PLUMA_DB_PATH` antes de probar una versión nueva.
- Si el proyecto se ejecuta desde otra carpeta, `PYTHONPATH` ayuda a garantizar que el import `pluma` resuelva desde `src`.
- En Windows, un `onefile` puede generar archivos temporales bajo `%TEMP%`; si se quiere una prueba más limpia, borra los directorios de compilación previos antes de volver a crear el binario.

## Datos del proyecto

Pluma almacena proyectos en una base de datos SQLite. De forma predeterminada, usa `data/pluma.db` junto a la aplicación. Si esa ubicación no permite escritura, utiliza el directorio de datos del usuario del sistema operativo. Para elegir otra ruta, configura la variable de entorno `PLUMA_DB_PATH` antes de iniciar la aplicación.

## Licencia

Pluma se distribuye bajo la licencia GNU GPL versión 3. Consulta el texto completo en [`LICENSE`](LICENSE).
