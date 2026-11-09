# Arranque de ARGOS en casa: orden de carga y recuperación

9 de noviembre de 2026. El cambio está instalado y ARGOS está abierto con Codex, voz, micrófono y renderer preparados. [Evidencia saneada](startup-recovery-2026-11-09.json).

## Fallo observado

El arranque del PC terminó en `WorkerStartupError`: `codex: readiness timed out after 45 seconds at runtime_import`. La etapa precede a la apertura de App Server y a la autenticación. No demuestra un fallo de login ni dependencia de VS Code.

El import nativo aislado funcionó después en aproximadamente un segundo, incluso sin red. Un reinicio completo con el código anterior llegó a Codex listo a los 23,705 s y a voz lista a los 149,807 s. Durante esa carga se observó el proceso de voz en espera de disco y presión de E/S. La aplicación lanzaba simultáneamente Hermes, Whisper y Qwen. Esto demuestra las condiciones actuales de carga y un timeout transitorio previo; **no identifica retrospectivamente la función exacta bloqueada durante el encendido**.

Había además un defecto concreto de observabilidad: el parser exigía `line N, in`, mientras `faulthandler` emite `line N in`. Descartaba las ubicaciones de esas trazas, dejando `frames: []`.

## Corrección

- Preparar primero la conversación nativa de Hermes/Codex y después iniciar Whisper y Qwen en paralelo. Los modelos de audio no compiten con la importación, la base de sesiones y el handshake inicial de Codex. La conversación por texto queda disponible mientras carga la voz.
- Reintentar **una sola vez** si expira el plazo durante la importación de Hermes. El proceso anterior debe quedar cerrado antes del segundo intento. No se reintentan automáticamente autenticación, registro de capacidades, turnos del usuario ni herramientas. El plazo individual de 45 s permanece igual; un segundo fallo queda visible.
- Permitir reintento manual desde el botón de micrófono cuando falla la preparación. El servidor y Electron lo aceptan exclusivamente por la ruta de control existente y el renderer confiable. Se bloquean duplicados mientras prepara, durante cierre o cuando la conversación ya está lista.
- Cancelar el consumidor de la cola si se interrumpe la preparación después de conectar Codex, para que otro inicio no deje consumidores antiguos. El reinicio de preparación no reproduce mensajes pendientes.
- Registrar las importaciones por separado y reconocer las ubicaciones de `faulthandler`, conservando solo archivo, línea y función. No se guardan stderr íntegro, credenciales, audio ni razonamiento.

Se conservan Hermes, modelo/esfuerzo, autenticación del piloto, permisos, herramientas, personalidad, captura y síntesis. No se cambió el proveedor ni el vendor. No se implementó Agent Desktop ni se modificó God's Eye View. La causa interna exacta del atasco inicial sigue sin establecerse: esta entrega corrige el orden de inicialización, su recuperación y el diagnóstico que faltaba.

## Validación

- **366 tests del repositorio**, correctos, incluidos procesos reales con timeout, recolección del proceso antes de reintentar, límite de intentos, orden de carga, cancelación y ausencia de duplicados. El timeout de autenticación conserva el fallo sin reintento automático.
- **10 comprobaciones del ciclo de arranque** y **11 del renderer Electron**, correctas. El botón de error envía el control `retry` a través del IPC real; vuelve a deshabilitarse durante la preparación. Se conservan las pruebas de borrado de errores anteriores y captions de voz.
- Reinicio de la app normal: **Codex listo en 4,505 s; aplicación con voz lista en 23,464 s**, sin reintento y con micrófono habilitado. El endpoint confirmó agente, voz y renderer conectados, sin error.
- Dos turnos nativos con almacenes y copia de autenticación desechables: «Yes, I’m here.» y «Sí, estoy aquí.», correctos. Primer texto a 1,816 y 0,791 s; respuesta completa a 1,967 y 0,921 s. Preparación con cero inferencias, ocho herramientas registradas y ninguna llamada de acción. El broker de la prueba responde solo a disponibilidad y rechaza acciones; **no es una validación nueva de esas ocho herramientas**. No se capturó ni reprodujo audio. Las copias privadas se eliminaron al cerrar la prueba.

La primera ejecución del harness aislado omitía el socket de disponibilidad; el registro obligatorio rechazó el inicio. Se corrigió el montaje con un broker desechable que rechaza acciones. Ese error de montaje del test no se presentó como defecto del producto ni se deshabilitó la comprobación de capacidades.

Los tiempos antes/después tienen cachés distintas y no prueban una aceleración cuantificada atribuible al parche. No se reinició el sistema operativo ni se ha validado todavía otro arranque en frío del PC. El autoinicio usa la misma instalación corregida. No se afirma una medida acústica micrófono-altavoz ni una corrección definitiva de un import que no pudo reconstruirse.

Fuentes: [orden y recuperación](../ui-workbench/runtime/conversation.py), [diagnóstico](../ui-workbench/runtime/startup.py), [etapas nativas](../checks/desktop_runtime.py), [prueba nativa aislada](../ui-workbench/qa-startup-native.py), [tests](../../../tests/test_pilot_startup.py).
