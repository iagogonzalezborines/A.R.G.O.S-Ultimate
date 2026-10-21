# Inferencia local por equipo — 21 de octubre de 2026

## Punto de continuación en casa

El usuario pidió detener la validación de oficina y subir los cambios para seguir
en casa. Última suite: **225 tests correctos**, en 9,638 segundos. No se ha
seleccionado todavía un modelo por defecto ni activado voz. Ollama y sus pesos
instalados en la oficina no viajan con Git.

Los [ensayos parciales posteriores](local-first-2026-10-21-partial.json) conservan
las respuestas y los fallos. Con el formato corregido, Qwen 3 4B contestó los
tres turnos de presencia en 108,519 / 42,488 / 41,630 segundos. Solo CPU tardó
127,611 / 45,408 / 48,016 segundos; la primera broma obtuvo una pregunta genérica
sobre la carpeta, sin captar la ironía. No se ha validado la personalidad deseada.
La comparación se detuvo; no se completó la evaluación de herramientas con 4B.
La prueba previa con 1.7B quedó bloqueada sin ejecutar las operaciones.

Siguiente paso: en casa, instalar Ollama y probar Qwen 3 8B con los evaluadores de
abajo, comprobando uso real de VRAM, latencia, continuidad y herramientas antes
de elegirlo con `./argos configure-providers --ollama-model qwen3:8b --codex on`.
Si no cabe con margen o es lento, comparar también Qwen 3 4B Instruct. No se ha
validado todavía el desarrollo local completo ni su escalada con ambos modelos
reales tras esta separación; el traspaso a Codex sí está cubierto con sustitutos
en los tests. No se consumió inferencia real de Codex en esta comparación.

## Alcance

La política implementada separa conversación local y escaladas de tareas a Codex.
La validación funcional del enrutamiento y la calidad de un modelo son resultados
distintos. Los informes anteriores de personalidad con Codex son históricos y
no demuestran la personalidad de Ollama.

## Equipos y selección

Oficina observada: Intel Core i7-4790, cuatro núcleos/ocho hilos, aproximadamente
24 GB de RAM y NVIDIA GT 1030 de 2 GB. Las mediciones se realizan con el escritorio
del usuario abierto; no son benchmarks de una máquina desocupada.

Casa, según el usuario: Ryzen 7 5800X, RTX 4060 de 8 GB, 32 GB de RAM. No se ha
accedido ni ejecutado inferencia en ese equipo. El primer candidato para comparar
allí es [Qwen 3 8B Q4_K_M](https://ollama.com/library/qwen3:8b), cuyo artefacto ocupa
unos 5,2 GB; necesita memoria adicional para contexto, ejecución y escritorio.
Es una recomendación de prueba, no una garantía de que quepa cualquier contexto
ni de latencia. No se descarga el modelo de casa en el PC de oficina.

La selección se guarda en `inference.json` dentro de la carpeta de estado de cada
instalación, fuera del repositorio. `configure-providers` no reinicia un Core
activo. Las tareas conservan su proveedor y modelo; cambiar de modelo exige
revisar las tareas pendientes, sin reutilizar hilos de otro proveedor.

## Instalación deliberada

Con la autorización del usuario para elegir e instalar Ollama:

- Ollama 0.40.7 en `~/.local/share/argos/ollama-runtime`, con enlace en
  `~/.local/bin/ollama`, siguiendo la [instalación manual oficial](https://docs.ollama.com/linux).
- Modelos en `~/.local/share/argos/ollama-models`, fuera de Git.
- Servicio local en `127.0.0.1:11434`, `OLLAMA_NO_CLOUD=1`, una inferencia simultánea.
  No se instala un servicio de arranque del sistema.
- Descargados para comparar: `qwen3.5:4b` (3,32 GB),
  `qwen3:4b-instruct-2507-q4_K_M` (2,50 GB) y `qwen3:1.7b` (1,36 GB).
- Perfil adicional `argos-office-cpu:4b`, creado con
  [office-cpu.Modelfile](../../config/ollama/office-cpu.Modelfile). Reutiliza los
  pesos de Qwen 3 4B e impone `num_gpu=0` para comparar CPU frente a la descarga
  parcial en la GT 1030. No duplica ni descarga pesos. Este parámetro forma parte
  de las [opciones oficiales del motor](https://github.com/ollama/ollama/blob/v0.40.7/api/types.go).

El adaptador comprueba metadatos locales antes de enviar conversación, rechaza
alias remotos y conexiones fuera de loopback, y deshabilita redirecciones/proxies.
Usa `think=false`, contexto de 16.384 tokens y salida estructurada. Solo recoge
respuesta pública y tiempos de la [API de chat](https://docs.ollama.com/api/chat).
No guarda razonamiento ni audio. El esquema restringe las herramientas al rol y
separa respuestas de operaciones. Los nombres del formato local sitúan `kind`
antes de agente/herramienta incluso cuando el motor ordena alfabéticamente las
propiedades; Core conserva su formato interno común.

## Política comprobada

Conversación, presencia, estado y operaciones conocidas no consumen Codex. Un
fallo, timeout, modelo ausente o límite de pasos tampoco lo activa. El agente
local puede ejecutar hasta doce decisiones/herramientas por tramo de tarea.

Solo Engineering/Research pueden justificar una escalada, tras una lectura real
registrada y antes de aprobar un plan o intentar efectos. Core conserva evidencia,
limpia el hilo anterior y registra atómicamente el proveedor de esa tarea. La
conversación continúa local. La justificación de dificultad la propone el modelo;
las comprobaciones estructurales no prueban que evalúe siempre bien su capacidad.

Los tests usan un sustituto de Codex para verificar el traspaso y la continuidad
del chat. No se ha ejecutado inferencia real de Codex durante esta comparación.
Las pruebas de inferencia local usan Core real y estado temporal, sin audio,
sin aplicaciones externas y sin alterar proyectos del usuario. La prueba de
herramientas solo permite archivos/directorios de su propia carpeta temporal.

Ollama procesa una inferencia a la vez: una tarea local puede retrasar un turno
de conversación hasta que termine su generación actual. El trabajo escalado a
Codex usa otro proveedor, pero la fluidez del chat sigue dependiendo del modelo
local. La ejecución en segundo plano no garantiza por sí sola baja latencia.

## Fallos conservados

Qwen 3.5 4B con el contexto original agotó 180 segundos en una pregunta de
presencia. Con contrato compacto, compartiendo la misma fuente de personalidad,
respondió en 134,728 y 132,811 segundos. No sirve como opción conversacional de
oficina en estas condiciones.

Qwen 3 4B Instruct con el primer esquema produjo campos de operación en respuestas
conversacionales: cuatro turnos fallidos, entre 39,561 y 114,626 segundos. El
esquema condicionado eliminó esa combinación inválida, pero eligió herramientas
innecesarias en cuatro de seis turnos (39,869–68,181 segundos), incluyendo una
propuesta de carpeta durante una broma. El evaluador la bloqueó antes de crear
tareas o ejecutar herramientas. Esto motivó corregir el orden del discriminador
y explicitar la separación entre conversación y órdenes.

Estas ejecuciones cambiaron contrato/esquema; no constituyen una clasificación
controlada de los modelos. Se conservan también los ensayos fallidos, sin presentar
los tests deterministas como evidencia de personalidad ni de fluidez.

Los [informes iniciales completos](local-first-2026-10-21-rejected.json) incluyen
el primer ensayo de Qwen 3 1.7B: nueve turnos, estructura válida pero respuestas
repetidas, eco del usuario y ubicación de carpeta inventada. La presencia pasó
de 56,947 segundos en frío a 18,059 y 7,627 segundos; esto tampoco satisface
conversación inmediata. En su primera prueba de herramientas describió lectura
y creación de carpeta sin ejecutarlas: ambas tareas quedaron BLOCKED con
`verification=proposal_only`, sin efectos ni escalada a Codex.

Se cambió la presentación del historial a mensajes con roles y la petición
actual a su propio mensaje de usuario. Además, una tarea especialista sin
resultados de herramientas no puede emitir una respuesta final: puede pedir
aclaración o solicitar una herramienta. Core sigue validando la evidencia
independientemente del esquema del proveedor.

## Reproducción

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
python scripts/validate_personality_live.py --run --ollama-model NOMBRE_LOCAL --report /tmp/argos-personality.json
python scripts/validate_local_tools_live.py --run --ollama-model NOMBRE_LOCAL --report /tmp/argos-local-tools.json
```

La evaluación completa de personalidad contiene 23 turnos. Las pasadas parciales
de comparación se identifican por sus escenarios en los informes. Las comprobaciones
de estructura no puntúan humor, naturalidad ni criterio; requieren revisión
cualitativa. No se ha validado aquí micrófono, síntesis, cancelación acústica ni
conversación hablada de extremo a extremo.
