# ARGOS · Linux 0.3

Asistente con Core Python/SQLite, tareas en segundo plano, Codex por tarea,
investigación web, operaciones del PC y voz local. La consola muestra solo una esfera
ASCII; los detalles se consultan desde otra terminal y las aprobaciones también admiten voz. Esta es la
reconstrucción Linux, no una recuperación del código Windows perdido.

## Abrir

Para usar voz hace falta instalar previamente su entorno y modelos locales:

```bash
cd /ruta/a/argos
./argos start
```

Arranca Core con Codex y voz y abre una ventana kitty titulada ARGOS.
Reutiliza Core si ya está activo. No configura inicio automático al arrancar Linux.

| Tecla | Acción |
| --- | --- |
| Espacio | Empezar a grabar; volver a pulsar para enviar |
| Escape | Detener grabación y voz; las tareas ya encoladas continúan |
| Q / Ctrl-C | Cerrar la consola; Core continúa |

La esfera es verde mientras escucha, amarilla durante la preparación inicial
y mientras procesa voz, cian durante
la reproducción y roja si falla la voz. La amplitud procede del audio PCM enviado al reproductor.
Por defecto el micrófono se abre al pulsar Espacio, con límite de 30 segundos.
La escucha manos libres es opcional y está apagada inicialmente:

```bash
./argos voice-config --wake-word on
./argos voice-config --wake-word off
```

Con ella activa, «Argos?» o «Argos, …» abre una conversación. El modelo contesta
con su respuesta natural: una pregunta breve recibe una contestación breve, sin
un «Sir» fijo ni una locución superpuesta. Puedes seguir hablando, responder «sí»
o «yes» y continuar el tema sin repetir el nombre ni hacerlo dentro de un plazo.
«Eso es todo», «hasta luego» o «that's all» devuelve la escucha a espera de «Argos»;
no cancela las tareas en segundo plano.

Whisper local reconoce la invocación y los finales de turno se detectan por
silencio. La captura permanece abierta entre turnos; los turnos que llegan
durante el reconocimiento o la inferencia esperan en una cola acotada en memoria.
En espera se descartan los textos sin invocación. Con la conversación abierta,
lo que recoge el micrófono se trata como conversación: no identifica al hablante.
Con el diálogo abierto puedes interrumpir su respuesta hablando: detiene el audio,
conserva el inicio de tu frase y pasa tu intervención al modelo. No añade un «Sir»
ni otra frase fija, no reanuda automáticamente la explicación cortada y no cancela
las tareas en segundo plano.

La interrupción requiere la cancelación de eco WebRTC de PipeWire. Al activar
manos libres, ARGOS crea una entrada y una salida virtuales temporales para su
propia voz, sin cambiar los dispositivos predeterminados del sistema. Tras 160 ms
de actividad sostenida en la entrada filtrada solicita el corte; la latencia real
depende del equipo. `./argos voice-status` muestra `barge_in_available`,
`echo_error` y `voice_interruptions`. Si el módulo no está disponible, sigue
funcionando por turnos y descarta el micrófono durante su reproducción. Si se
pierde el cancelador en marcha, detiene la escucha y muestra el fallo.
Escape apaga también la escucha; Espacio vuelve a captura manual y la desactiva.
La preferencia se conserva entre arranques. Cerrar la consola no desactiva Core
ni una escucha manos libres previamente activada: usa Escape o `--wake-word off`.
La interrupción está cubierta por pruebas silenciosas; queda pendiente validar
eco, ruido y latencia con el micrófono y los altavoces del usuario. El detector
usa energía y no identifica al hablante: otras voces o ruido sostenido pueden cortarlo.

El modo de idioma predeterminado es
automático: responde en español si hablas español y en inglés si hablas inglés.
También reconoce «habla en inglés», «cambia a español» y «speak Spanish».
Si después vuelves a hablar en el otro idioma, la respuesta vuelve a seguirte.
Palabras ambiguas como «okay» conservan el idioma anterior.

Ejemplos: «hola», «abre Firefox», «lista las ventanas», «enfoca Firefox»,
«busca en la web documentación de Python», «qué estás haciendo»,
«activa modo gaming».

## Mapa de agentes y monitor de tareas

Son dos ventanas de terminal independientes, actualizadas en directo. La esfera
de voz sigue en su propia ventana.

- «Argos, muéstrame a los agentes», «mapa de agentes» o «diagrama de agentes» abre
  un diagrama con Core en el centro y los seis agentes conectados. Cada nodo
  muestra su nombre, disponibilidad, ocupación o espera y actividad actual.
  TAB o flechas seleccionan un agente para ver su rol, capacidades y proveedor.
- «Abre el monitor de tareas», «historial de tareas» o «conversaciones de Codex»
  abre tareas con objetivo, estado, agente, proyecto, hilo y secuencia de eventos.
  C muestra conversaciones generales mantenidas a través de ARGOS; T vuelve a tareas.
- Si la ventana ya existe, la orden la enfoca. Q cierra solo esa ventana.
  El mapa abre el monitor con T; el monitor abre el mapa con M.

También admite «puedes abrir el mapa de los agentes», «show me the map of agents»
y «The ARGOS agent diagram here». Las peticiones naturales que no coinciden
con una orden directa pasan a General, que puede solicitar el mismo panel.

En el monitor: **1–4** filtran todas/en proceso/en espera/finalizadas; **G**
recorre agentes y **A** quita ese filtro. **↑↓** seleccionan registros, **←→**
cambian la página del historial, **PgUp/PgDn** desplazan el texto y **[ / ]**
consultan eventos o mensajes anteriores/posteriores del registro seleccionado.
El texto sigue los eventos nuevos; PgUp permite revisar lo anterior y F vuelve
al seguimiento en directo.
Una conversación sin turno activo se distingue de una tarea finalizada.

```bash
./argos monitor agents --open
./argos monitor tasks --open
# Dentro de la terminal actual:
./argos monitor agents
./argos monitor tasks
```

Las vistas corresponden a la sesión seleccionada (`--session`, por defecto
`default`). Muestran datos registrados por Core; no consultan al modelo para
actualizarse. Incluyen el historial de tareas existente. Los mensajes de
conversación general empiezan a registrarse con esta versión: no se recuperan
conversaciones antiguas ni otros chats de Codex ajenos a ARGOS. Solo se muestran
mensajes públicos, preguntas, resultados y comentarios de progreso, sin
razonamiento interno. Estos mensajes se conservan en la base local privada.

Los paneles son de observación; las respuestas a preguntas, aprobaciones y
cancelaciones siguen usando las interfaces ya existentes. Al perder conexión,
indican que sus datos han dejado de actualizarse y vuelven a conectar cuando
Core está disponible.

## Qué ejecuta

ARGOS incorpora un inventario local de solo lectura. General y los especialistas
reciben observaciones del equipo con origen, fecha y estado de comprobación:
distribución/kernel, CPU, RAM, identificadores PCI/controlador de GPU, espacio
de `/` y de la carpeta personal, sesión gráfica, herramientas y dispositivos de
audio. Consultar dispositivos no abre el micrófono ni reproduce sonido.

```bash
./argos doctor                         # También funciona con Core apagado
./argos system-status                  # Inventario del Core y capacidades
./argos system-status --refresh        # Repetir las observaciones locales
./argos system-status --project ARGOS  # Incluir el contexto de un proyecto
./argos run system.inspect --wait      # Inspección registrada como tarea
./argos say "inspecciona el equipo"
```

El inventario se conserva en memoria durante 30 segundos y se renueva cuando se
necesita. Las consultas `system-status` no crean tareas ni escriben SQLite;
`system.inspect` sí registra evidencia como cualquier otra capacidad. No explora
documentos personales, credenciales, argumentos de procesos ni todo el entorno.
No comprueba la conexión a Internet, el inicio de sesión de Codex ni los modelos
de voz; indica esas limitaciones en lugar de deducirlas de un ejecutable instalado.
Los identificadores de GPU no equivalen a un diagnóstico completo del hardware y
la información de discos no enumera todos los montajes.

Cada capacidad distingue `implemented` de su disponibilidad:

| Estado | Significado |
| --- | --- |
| `available` | Los requisitos comprobados están presentes; el resultado de una operación aún debe verificarse. |
| `unavailable` | Falta una dependencia o sesión requerida. |
| `permission_denied` | Una comprobación ha recibido una denegación de permisos. |
| `needs_context` | Hace falta seleccionar un proyecto. |
| `not_checked` | Falta comprobar algo o depende de ruta, argumentos, fuente web o permisos concretos. |

`available` vale `true`, `false` o `null` (sin comprobar), acompañado de `reason`
y `checked_at`. Por ejemplo, `windows.list` no se anuncia disponible sin Hyprland;
`workspace.open` comprueba por separado VS Code y la combinación kitty/Codex.
Un bloqueo conocido impide solicitar aprobación o lanzar la operación. La
disponibilidad no sustituye las aprobaciones ni amplía permisos del usuario.
El mapa de agentes distingue «sin tarea» de la disponibilidad de herramientas.

| Rol | Capacidades conectadas |
| --- | --- |
| General | Intenciones locales y conversación/interpretación con Codex |
| Engineering | Archivos del PC, proyectos nuevos, comandos revisados, workspaces y consulta web |
| Computer | Inventario del equipo, aplicaciones, ventanas Hyprland, archivos, carpetas, workspaces y URLs |
| Research | Buscar, leer páginas públicas, seguir enlaces y sintetizar varias fuentes con Codex |
| Design3D / Printing3D | Inspección de STL / G-code; sin actuadores conectados |

Las aplicaciones se descubren mediante archivos `.desktop`. Las ventanas requieren
Hyprland. Abrir una aplicación informa de la solicitud de lanzamiento, no garantiza
que una aplicación externa haya terminado de arrancar. Cerrar requiere aprobación.

Las operaciones de archivo aceptan rutas absolutas en el PC con los permisos
normales del usuario Linux. No necesitan proyecto registrado. Las rutas relativas
usan el proyecto seleccionado. No elevan privilegios ni sortean permisos de Linux.
Se admiten archivos ocultos de configuración normales; se excluyen credenciales,
enlaces simbólicos, dispositivos y ciertos formatos privados del contexto del modelo.

`files.list` / `files.list_page` listan carpetas paginadas. `files.read` devuelve
la primera página UTF-8, el SHA-256 y `next_offset`; `files.read_range` continúa
por desplazamientos de caracteres. El archivo puede superar 64 KB. `files.write`
reemplaza el contenido completo; `files.patch` inserta, sustituye o añade tramos
a archivos grandes con SHA previo. Cada inserción admite hasta 64000 caracteres:
es un límite por operación, no de tamaño total del archivo.

También están conectadas `files.stat`, `files.mkdir`, `files.copy`, `files.move`
y `files.delete`. Copiar/mover admite archivos binarios y árboles de directorios;
no sobrescribe un destino existente. Borrar traslada a una carpeta `.argos-trash`
en el mismo directorio padre. La tarea registra origen, destino y SHA para poder
restaurar con `files.move`. Los movimientos entre sistemas de archivos requieren
copiar, verificar y después borrar. Las modificaciones se revisan y aprueban.

La búsqueda usa Bing RSS sin clave y puede encadenarse con `web.read` para leer
HTML/texto públicos, extraer enlaces y consultar páginas largas por tramos.
«Investiga …» delega en Research: el especialista elige consultas, puede seguir
fuentes, comparar varias páginas y citar sus URLs en el resultado. `web.read`
verifica el SHA entre páginas y registra URL final y fecha de consulta. Los
resultados externos no autorizan operaciones sobre el equipo.
El lector descarga hasta 4 MiB por página, sin ejecutar JavaScript ni usar sesiones
privadas; PDF, sitios que exigen inicio de sesión y páginas exclusivamente dinámicas
no se leen con este adaptador. La búsqueda depende de la disponibilidad de Bing.

## Proyectos, programación y aprobación

ARGOS puede delegar en Codex mejoras de un proyecto, proyectos nuevos y cambios
en su propio código. Primero inspecciona una copia privada, explica un plan
concreto y pide confirmación. Después trabaja en segundo plano con una sola
autorización para los archivos de esa candidata y las pruebas incluidas en el plan.
Puedes seguir conversando y preguntar «¿cómo va esa mejora?» o «qué estás haciendo».
Core aporta el estado observado; no inventa porcentajes de progreso.

```bash
./argos develop "Añade una opción para consultar las tareas fallidas" --target self
./argos develop "Implementa la exportación CSV y sus pruebas" --project mi-proyecto
./argos develop "Crea una biblioteca Python para convertir unidades" --target new
./argos task ID
./argos review ID
./argos approve ID HUELLA_DEL_PLAN
```

También admite peticiones naturales como «implementa esta mejora en ti mismo».
El plan y el aviso final los redacta el modelo y se reproducen sin añadir un
«Sir» fijo. Un «sí» inmediato confirma **solo** un plan que haya terminado de
reproducirse en esa sesión, durante dos minutos, sin otra pregunta/aprobación
pendiente. Interrumpir la locución o cambiar de tema invalida esa respuesta corta.
Para volver a presentarlo: «revisa aprobación ID»; también admite el código exacto
de revisión. No se amplía este permiso a otras tareas ni a operaciones del anfitrión.

Las candidatas quedan en `ESTADO/development/ID/workspace`, junto a `changes.patch`
y un manifiesto con hashes. El origen no se modifica. Se copian hasta 128 MiB y
10000 archivos; se excluyen Git, entornos/dependencias, cachés, enlaces y rutas
privadas. Las pruebas acordadas usan bubblewrap instalado, sin red, escritorio,
audio ni home del anfitrión, con runtimes del sistema y `PYTHONPATH=/workspace/src`.
Si falta una dependencia o falla el aislamiento, se informa del fallo: no hay
ejecución automática de esas pruebas fuera de la sandbox. No se instalan paquetes.

Al terminar, ARGOS anuncia el resultado después de la respuesta en curso, sin
una llamada adicional al modelo para redactar el aviso. Pruebas fallidas,
omitidas o anteriores al último cambio no certifican la candidata. Reiniciar o
cancelar revoca la autorización; reanudar exige revisar un nuevo plan y no repite
efectos. **Preparar y probar una mejora no la instala:** aplicar al proyecto,
publicar, activar una nueva versión y hacer rollback quedan fuera de este flujo.

```bash
./argos add-project ARGOS /ruta/a/argos
./argos say "programacion: revisa cómo se gestionan las tareas" --project ARGOS
./argos tasks
./argos task ID
```

Codex usa la sesión ChatGPT existente mediante App Server y conserva un hilo por
tarea, también después de una pregunta o aprobación. No utiliza claves de OpenAI
API. Los saludos y comandos conocidos se resuelven sin consultar un modelo.
El modelo recibe el contexto seleccionado y los archivos que solicita mediante
las capacidades permitidas, sin acceso libre al disco.

Para operaciones individuales sobre el anfitrión (fuera del desarrollo aislado):

```bash
./argos review ID
./argos approve ID HUELLA_COMPLETA_MOSTRADA
```

`review` muestra el contenido propuesto, archivo y SHA previo, o los argumentos
del comando y su carpeta. La aprobación es de un uso, ligada a tarea y argumentos.
Core ejecuta esa operación preparada antes de devolver el control al modelo.
Cambiar el archivo o la definición del comando invalida la operación.
También puedes decir «Argos, revisa aprobación», o «revisa aprobación ID» si hay
varias tareas. Core describe la operación, rutas/argumentos y emite cuatro palabras.
«Argos, aprueba PALABRAS» autoriza esa operación exacta una sola vez, en la misma
sesión, durante dos minutos. Un «sí» no basta. Reiniciar invalida los códigos.
Para escrituras, la revisión hablada indica ruta, longitud y huella del contenido;
el contenido completo sigue en `review`. Es posible usar el mismo flujo por texto
con `./argos say`, o pedir la lectura con `./argos voice-review ID`.

Registra comandos concretos para un proyecto:

```bash
./argos register-command --project ARGOS tests env PYTHONPATH=src python -m unittest discover -s tests -v
```

Registrar no ejecuta. Los comandos corren con los permisos del usuario después
de aprobarlos; no constituyen un contenedor de seguridad. El registro acepta argv,
no una cadena que ARGOS interpole en un shell.

`commands.exec` permite proponer comandos nuevos sin registro previo, indicando
`cwd` y `argv_json` (lista JSON codificada como texto). Core muestra los argumentos
y carpeta antes de solicitar aprobación. Los comandos ejecutan con permisos del
usuario y pueden tener efectos fuera de esa carpeta: la aprobación no es una sandbox.

Para crear carpetas directamente en el anfitrión están `files.mkdir` y
`projects.create`, esta última con nombre y ruta. Core registra el proyecto.
Para programar desde cero, `develop --target new` prepara una candidata vacía.
`workspace.open`
abre la carpeta en VS Code (`editor=code`) o una terminal kitty con Codex
(`editor=codex`), previa revisión. Esa terminal Codex es una sesión independiente;
sus acciones no se atribuyen automáticamente a la evidencia de ARGOS.

```bash
./argos develop "Crea un proyecto Python con conversión de unidades y pruebas" --target new
./argos run files.read_range --args '{"file":"/ruta/a/grande.txt","offset":"32000","limit":"32000","expected_sha256":""}' --wait
./argos run files.mkdir --args '{"path":"/ruta/a/nueva-carpeta"}' --wait
./argos run web.read --args '{"url":"https://www.python.org/","offset":"0","expected_sha256":""}' --wait
./argos say "investiga las alternativas y resume varias fuentes con sus enlaces"
```

Otras operaciones:

```bash
./argos run files.list --project ARGOS --args '{"path":"src/argos"}' --wait
./argos run files.read --project ARGOS --file README.md --wait
./argos run web.search --args '{"query":"Python asyncio documentation"}' --wait
./argos run windows.list --wait
./argos reply ID "respuesta"
./argos cancel ID
./argos resume ID
./argos say "hola" --speak
./argos voice-status
./argos voice-inputs
./argos voice-config --language auto --input-device ID_DEL_MICROFONO
./argos doctor --codex
```

`--json`, `--session` y `--state-dir` van antes del subcomando. Los reintentos
pueden usar `--request-id MISMO_ID` con los mismos argumentos. Las tareas
interrumpidas se revisan antes de reanudar; no se repiten al arrancar.

## Voz y dependencias

Core usa Python 3.11+ y su biblioteca estándar. Voz usa un entorno separado
Python 3.12 en `~/.local/share/argos/voice-env`, Whisper base/int8 en CPU y
Pocket TTS con el preset Peter Yearsley, modelos español e inglés. Al arrancar
se preparan silenciosamente ambas voces y se ejecuta reconocimiento sobre
audio sintético generado en memoria; una prueba solo con silencio no prepara
el reconocimiento completo. La esfera permanece amarilla durante esa preparación
(unos 5 s en una muestra de este equipo).
Las voces permanecen en memoria al cambiar español/inglés. No se carga
un modelo por cada agente. La primera petición puede esperar si la preparación
aún no ha terminado; interrumpir una síntesis reinicia ese proceso.

La voz se reproduce por fragmentos mientras se genera, sin esperar un WAV
completo. Antes de iniciar la reproducción se acumulan 240 ms de audio para
absorber pausas iniciales de generación. No se recorta el texto hablado a un
número de caracteres: la respuesta completa validada llega a la síntesis.
La extensión depende de la pregunta y del contexto de conversación.

Abrir la consola también conecta Codex y prepara el hilo de la sesión y proyecto
seleccionados. No envía un turno ficticio ni añade mensajes al historial.
La conversación General solicita esfuerzo `low` cuando el modelo
configurado lo admite; los especialistas mantienen su esfuerzo configurado.
No se cambia de modelo ni de proveedor. Las consultas remotas aún dependen
de la latencia de Codex y de la complejidad de la petición.

`./argos voice-status` muestra preparación de voz, tiempos del último
reconocimiento/despacho y tiempo hasta enviar el primer fragmento de síntesis.
Son medidas internas, no una medición acústica de los auriculares; no guardan audio.

Para reproducir la instalación en otra máquina con `uv`:

```bash
python scripts/setup_voice.py
```

Descarga paquetes y modelos de forma explícita. PyAV se fija a 16.1.0:
la versión 19 instalada inicialmente era incompatible con faster-whisper 1.2.1.
El modo de idioma y el micrófono se guardan en la configuración de ARGOS.
`voice-config --language auto` activa el seguimiento automático. Las opciones
`--language es` y `--language en` permiten fijar un idioma manualmente desde CLI.
Una orden hablada de cambio selecciona ese idioma y vuelve al modo automático.
Un micrófono
seleccionado que se desconecta produce un error; no se cambia a la webcam.
Esta selección no cambia los dispositivos predeterminados de otras aplicaciones.

El runtime usa los modelos descargados en modo offline. Necesita también
`pw-record` / `pw-play`, una sesión PipeWire y, para el lanzador, kitty.

STT y TTS comparten un proceso separado. Las notificaciones esperan mientras
se graba o transcribe, para evitar que el micrófono recoja la propia voz.
Los WAV de captura manual y manos libres son temporales, privados y se borran al terminar, cancelar
o reiniciar. La síntesis normal transmite PCM sin escribir audio en disco.
Los textos de las peticiones sí pueden quedar en el historial de tareas.
GAMING descarta avisos de tareas; no los acumula para reproducirlos después.

Referencias: [Codex App Server](https://learn.chatgpt.com/docs/app-server),
[Pocket TTS](https://github.com/kyutai-labs/pocket-tts),
[faster-whisper](https://github.com/SYSTRAN/faster-whisper).

## Ejecución manual y límites

```bash
./argos serve --codex --voice
# En otra terminal:
./argos console --project ARGOS
```

`serve` sin opciones mantiene capacidades locales.
`--ollama-model NOMBRE` permite usar un intérprete Ollama local ya instalado
en lugar de Codex. No se pueden seleccionar ambos proveedores.

Estado: `$XDG_STATE_HOME/argos` o `~/.local/state/argos`, socket privado y SQLite.
El lanzador escribe errores en `core.log`, nunca sobre la esfera.
Los procesos de tu mismo usuario pertenecen al perímetro de confianza.
El filtro de secretos rechaza patrones conocidos; no es una garantía DLP completa.

Pendientes: validación acústica del modo manos libres, lector web dinámico/PDF,
Blender, impresora, aplicación/activación de candidatas con rollback y GUI Windows. «Actualiza ARGOS» informa de que falta
el instalador y no reemplaza ningún ejecutable.

## Validar

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
python scripts/benchmark.py
```

Las pruebas `unittest` usan temporales y audio silenciado; no cambian proyectos
reales, abren aplicaciones, consultan modelos ni activan hardware.
Por tanto, su resultado no demuestra por sí solo que Codex responda bien ni que
el protocolo funcione con una versión/modelo reales. `benchmark.py` mide IPC,
no latencia de conversación con IA.

Evaluación explícita con **Codex real**, usando la sesión ChatGPT y el modelo ya
configurados (consume cuota; requiere conexión):

```bash
python scripts/validate_codex_live.py --run --report /tmp/argos-codex-live.json
python scripts/validate_codex_live.py --run --self-check --report /tmp/argos-self-live.json
```

Prueba conversación por texto, identidad/límites, una petición ambigua, un plan
de programación, confirmación por texto, conversación durante el trabajo,
consulta de estado, código/pruebas generados, resultado independiente y aviso
de finalización. Solo opera sobre una candidata temporal; no activa micrófono,
síntesis ni altavoces, no instala modelos y no altera proyectos reales. El informe
conserva respuestas públicas, herramientas utilizadas, tiempos y evidencia;
nunca razonamiento ni credenciales. Una pasada es evidencia de esos escenarios,
no una garantía de fiabilidad general ni una validación acústica.

Resultados y límites de la [evaluación real del 21 de octubre de 2026](docs/validation/codex-live-2026-10-21.md),
incluyendo el fallo inicial y las ejecuciones posteriores sobre un proyecto
temporal y sobre una copia del propio ARGOS.
Ver [arquitectura](docs/architecture.md), [validación](docs/validation.md)
y [contrato de ARGOS](src/argos/contracts/ARGOS.md).
