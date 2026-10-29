# Changelog

## 0.11.0

- Se incorporó el guardado manual mediante el botón «Guardar», con icono adaptado al tema y atajo `Ctrl+S`. El botón solo se activa cuando hay cambios pendientes. Se añadió la opción `Activar autoguardado` en Ajustes: al desactivarla, los cambios quedan pendientes hasta guardarlos manualmente; al reactivarla, se guardan los cambios acumulados. Antes de cambiar de proyecto, gestionar proyectos, crear o restaurar copias de seguridad o cerrar la aplicación, Pluma pregunta si guardar los cambios, descartarlos o cancelar la operación.
- Se reforzó la validación para rechazar archivos dañados, incompatibles o ajenos a Pluma. También se impide copiar o restaurar una copia de seguridad sobre la base de datos en uso.
- Al crear o renombrar un proyecto con un nombre ya existente, se muestra un mensaje claro en lugar de un error genérico. Los archivos de configuración dañados o modificados manualmente se sustituyen por los valores predeterminados, y `Restaurar valores` aplica todos los ajustes de una sola vez.
- Se reparó el funcionamiento de los atajos de negrita (`Ctrl+B`), cursiva (`Ctrl+I`), subrayado (`Ctrl+U`) y tachado (`Ctrl+Shift+X`). También se corrigió el botón «Centrar», que ahora permanece marcado cuando el párrafo está centrado.
- Las escenas y los bloques de la línea temporal solo pueden vincularse a capítulos del mismo proyecto. Si los proyectos no coinciden, se muestra un aviso en lugar de crear un vínculo inválido.

## 0.10.2

- Se corrigió la ubicación de la base de datos en Windows: la comprobación de escritura no era fiable y podía elegir una carpeta de solo lectura.
- El registro de errores ahora guarda también los avisos, no solo los errores graves.
- La migración del título ya no sobrescribe un título vacío en cada arranque.
- Al exportar, la extensión del archivo se ajusta al formato elegido en lugar de duplicarse.
- El nombre automático de los capítulos ya no se repite al borrar capítulos.
- Los paneles con lista se cargan con una sola recarga al abrir un proyecto.
- El panel de escenas carga los capítulos vinculados en una sola consulta y se refresca al entrar en la sección.
- El guardado de fichas (personajes y escenas) agrupa todos los campos en una sola transacción.
- El tema predeterminado cambia de Material a Tinta.

## 0.10.1

- Se añadió un chevrón SVG propio a los campos desplegables.
- Se ajustó el trazo del icono de chevrón hacia abajo.
- Se añadió enlace (URL) hacia el repositorio.