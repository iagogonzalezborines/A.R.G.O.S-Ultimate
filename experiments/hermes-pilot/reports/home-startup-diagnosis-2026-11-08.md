# Diagnóstico del arranque en casa — 8 de noviembre de 2026

Informe de la fase inicial de solo lectura. La actualización y las pruebas posteriores están en [Integración en casa](home-integration-2026-11-08.md); las afirmaciones de instalación sin modificar describen únicamente esta fase previa.

**El fallo registrado no se ha reproducido. La causa raíz sigue sin determinarse y no se ha modificado el código de ejecución.** [Evidencia saneada](home-startup-diagnosis-2026-11-08.json).

## Incidencia concreta

El texto inglés que comienza con «Diagnose this recorded ARGOS execution error» es el objetivo de una propuesta automática, no la excepción original. El controlador lo prepara después de registrar un error de voz/arranque.

La incidencia del 8 de noviembre a las 13:46:08, hora de Madrid, es `3158d2ad2ce51aa063bbf847`: `voice.prepare` / `WorkerStartupError`, con mensaje `codex: readiness timed out after 45 seconds`. La traza registra `Conversation.prepare` y `Worker.start`. Hay otro registro con ese mismo mensaje el 6 de noviembre. El `TimeoutError` sin componente del día 5 es una evidencia anterior distinta.

La entrada de autoinicio actual ejecuta `/usr/bin/python ~/.local/share/argos-hermes-pilot/ui-workbench/launch.py`. Sigue apuntando a la instalación de casa anterior a los avances de proyectos del día 6; no se ha cambiado ni reemplazado durante esta investigación.

## Evidencia que faltaba en las propuestas anteriores

La copia editable de mantenimiento contiene `runtime/conversation.py`, pero no el trabajador lanzado `checks/desktop_runtime.py` ni su helper `checks/codex_startup.py`. La propuesta automática más reciente señaló precisamente esa ausencia. Además, el `Worker` instalado inicia el hijo con `stderr=DEVNULL`; no conserva su error interno para ese timeout.

El modelo respondió que no podía establecer un defecto y no cambió archivos. Después, la validación de mantenimiento rechazó la propuesta con `Codex produced no source change` y registró una incidencia de desarrollo. Eso explica la secuencia visible de diagnóstico sin parche; no establece la causa del timeout de arranque. No se ha convertido esa limitación en un cambio de permisos, una falsa reparación o una actualización instalada.

## Reproducciones acotadas

Se ejecutó el trabajador nativo de la instalación dentro del sandbox existente, con su fuente montada de solo lectura y una copia aislada del archivo de entrada. Configuración, autenticación e historial procedían exclusivamente del piloto, con almacenes privados desechables superpuestos a sus rutas habituales. La base SQLite se copió mediante su API de backup. No se usó la autenticación del IDE.

La segunda prueba añadió una copia del estado Codex y del rollout correspondiente al hilo guardado. No se inspeccionó ni publicó el contenido del historial. Los resultados solo recogen preparación, tiempo, recuperación del identificador y diagnóstico saneado. Ambas pruebas evitaron `turn/start`: cero inferencias, captura o reproducción de audio. No arrancaron STT/TTS ni reiniciaron la app visible.

| Prueba | Resultado |
|---|---|
| Historial copiado y hogar Codex nuevo | Listo en 4,979 s; el hilo no estaba en esa copia y se aplicó el fallback nativo a uno nuevo |
| Historial y hilo Codex guardado copiados | Listo en 4,306 s; recuperó el mismo identificador de hilo |

Las copias de credenciales y almacenes de sesión de ambas pruebas se eliminaron tras cerrar sus procesos. La app visible, sus sesiones, la configuración de voz/GPU y el autoinicio se conservaron.

## Conclusión y límite

La traza prueba que expiró el plazo de preparación de Codex. Las dos reproducciones muestran que puede prepararse ahora, incluida la recuperación del hilo existente, sin depender de abrir VS Code. No distinguen las condiciones que existían durante el inicio de sesión gráfico. Tampoco reproducen la competencia de recursos con la preparación simultánea de reconocimiento y síntesis.

No hay evidencia suficiente para afirmar que la causa sea red, OAuth, GPU, un servicio ausente o un plazo demasiado corto. No se han aumentado timeouts, añadido esperas/reintentos ni cambiado modelos, historial, permisos o autenticación para aparentar una solución.

**Siguiente evidencia necesaria:** conservar etapas y error interno saneado del trabajador durante un arranque que realmente falle. La implementación actual descarta ese error; introducir observabilidad sería un cambio separado, acotado y revisable. Este informe no prepara un parche de causa raíz porque esa causa no está establecida, conforme a la condición del usuario.
