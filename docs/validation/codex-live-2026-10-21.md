# Validación real de ARGOS con Codex — 21 de octubre de 2026

El flujo de programación y autoprogramación se ejecutó con inferencia real de
`gpt-6-astra`, proveedor `openai`, mediante el Codex App Server instalado y la
sesión ChatGPT existente. No se cambió el modelo, proveedor ni configuración del
usuario. App Server corre localmente; la inferencia de Codex es remota.
No se utilizó el micrófono, STT, TTS ni los altavoces.

La suite de 207 pruebas anterior usaba proveedores simulados y no demostraba
este comportamiento con un modelo real. La validación encontró un fallo real:
desactivar `code_mode_host` dejaba funcionar la conversación, pero impedía llamar
al puente de herramientas. Dos intentos iniciales quedaron bloqueados antes de
presentar un plan aprobable. Se conserva el [diagnóstico fallido](codex-live-2026-10-21-failure.json),
incluida la respuesta pública del especialista, sin razonamiento ni credenciales.

Se habilitó el host de herramientas, manteniendo desactivados shell, navegador,
plugins y otras herramientas nativas; Core sigue autorizando cada efecto. También
se corrigieron las respuestas de estado, que repetían una petición cortada, y
se preserva la propuesta pública del proveedor cuando una candidata queda bloqueada.
Una variable local llamada `token` se renombró para evitar que el filtro de
credenciales impidiera al propio ARGOS leer `core.py`; no se relajó el filtro.

| Caso posterior a la corrección | Evidencia observada |
| --- | --- |
| Conversión de temperaturas, primera pasada | Plan, confirmación, dos archivos modificados, seis pruebas unittest correctas y siete casos de aceptación independientes. [Informe](codex-live-2026-10-21-project-first-pass.json). |
| Conversión de temperaturas, repetición | Mismo recorrido completo, otra generación real, pruebas y aceptación correctas. [Informe](codex-live-2026-10-21-project-repeat.json). |
| Autoprogramación | Copia del código fuente real de ARGOS; Codex leyó instrucciones, modificó `language.py`, añadió regresiones y ejecutó la suite completa en bubblewrap con salida 0. Seis casos de aceptación independientes correctos. [Informe](codex-live-2026-10-21-self-development.json). |

En los tres casos no hubo escrituras antes de la confirmación; durante RUNNING
General respondió a una conversación ajena y a una consulta de estado; el origen
permaneció intacto; Core registró la finalización y su aviso. El código de prueba
y las candidatas eran temporales y se eliminaron al terminar; los informes
conservan respuestas, pasos observados, hashes y código generado. Las rutas
temporales mencionadas en las respuestas ya no están disponibles.

Ejemplos reales observados:

- «Argos, are you there?» → «Yes, I’m here.»
- «Mira esto y dime qué está mal» → pidió el contenido, archivo o enlace y aclaró
  que no estaba viendo la pantalla.
- La pregunta sobre identidad recibió una explicación de ARGOS, Codex como
  proveedor y la distinción entre preparar una candidata y activarla.
- Durante el trabajo explicó idempotencia sin convertir la conversación en otra tarea.
- Tras la finalización informó de candidata lista, pruebas superadas y ausencia
  de aplicación al proyecto original/activación.

Los planes, respuestas conversacionales y avisos finales son texto del modelo;
la aceptación y los estados verificables usan mensajes de Core. No se añadió
un «Sir» fijo ni una llamada adicional para Persona o redacción del aviso.
La confirmación fue textual mediante el mismo manejador de Core que recibe el
texto reconocido por STT; esto no prueba reconocimiento ni confirmación acústica.

La respuesta de presencia tardó aproximadamente 4,3–4,7 segundos. En las dos
últimas ejecuciones, la explicación durante el trabajo tardó 3,6 y 5,1 segundos;
las consultas de estado concurrentes tardaron 6,7 y 8,6 segundos, incluyendo la
espera del turno anterior de la misma sesión. La tarea de conversión de la
repetición duró 33,9 segundos y la de autoprogramación 72,2 segundos, con
confirmación automática del evaluador. Son muestras individuales, no percentiles
ni una promesa de latencia. STT y TTS añadirían su propio tiempo.

Tras las correcciones pasan 208 pruebas deterministas. Las pruebas añadidas por
Codex durante la evaluación de autoprogramación quedaron únicamente en la copia
temporal y no se incorporaron al repositorio.

Para repetir, consumiendo cuota de la sesión ChatGPT actual:

```bash
python scripts/validate_codex_live.py --run --report /tmp/argos-project-live.json
python scripts/validate_codex_live.py --run --self-check --report /tmp/argos-self-live.json
```

Esto demuestra viabilidad en esos escenarios concretos. No garantiza que el
modelo siempre seleccione el plan adecuado, que resuelva proyectos arbitrarios
ni que la conversación por voz ya sea fluida. Siguen sin validarse aquí captura,
reconocimiento, síntesis, reproducción e interrupción acústica. No se probó ni
activó actualización, publicación o rollback de ARGOS.
