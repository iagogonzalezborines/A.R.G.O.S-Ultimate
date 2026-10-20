# ARGOS · Linux 0.2

Asistente con Core Python/SQLite, tareas en segundo plano, Codex por tarea,
búsqueda web, operaciones Linux y voz local. La consola muestra solo una esfera
ASCII; detalles y aprobaciones se consultan desde otra terminal. Esta es la
reconstrucción Linux, no una recuperación del código Windows perdido.

## Abrir

En este equipo ya están instalados los modelos de voz:

```bash
cd /home/tyrant/Proyectos/argos
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
El micrófono solo se abre al pulsar Espacio y se limita a 30 segundos.
No hay palabra de activación todavía. El modo de idioma predeterminado es
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

| Rol | Capacidades conectadas |
| --- | --- |
| General | Intenciones locales y conversación/interpretación con Codex |
| Engineering | Inspeccionar repositorio, listar/leer/escribir texto, comandos registrados |
| Computer | Sistema, aplicaciones, ventanas Hyprland, abrir documentos y URLs |
| Research | Búsqueda pública con enlaces; síntesis con Codex al delegar investigación |
| Design3D / Printing3D | Inspección de STL / G-code; sin actuadores conectados |

Las aplicaciones se descubren mediante archivos `.desktop`. Las ventanas requieren
Hyprland. Abrir una aplicación informa de la solicitud de lanzamiento, no garantiza
que una aplicación externa haya terminado de arrancar. Cerrar requiere aprobación.

Los archivos se limitan a proyectos registrados: texto UTF-8 hasta 64 KB,
sin rutas ocultas, enlaces simbólicos ni credenciales evidentes. Las escrituras
comparan el SHA-256 anterior y verifican el contenido final. Todavía no se expone
borrar, mover ni crear carpetas.

La búsqueda usa Bing RSS, sin clave. Guarda títulos, fragmentos y enlaces;
no descarga ni verifica páginas completas. El servicio externo puede limitarla.
«research: investiga …» inicia un especialista que puede realizar varias búsquedas.

## Proyectos, programación y aprobación

```bash
./argos add-project ARGOS /home/tyrant/Proyectos/argos
./argos say "programacion: revisa cómo se gestionan las tareas" --project ARGOS
./argos tasks
./argos task ID
```

Codex usa la sesión ChatGPT existente mediante App Server y conserva un hilo por
tarea, también después de una pregunta o aprobación. No utiliza claves de OpenAI
API. Los saludos y comandos conocidos se resuelven sin consultar un modelo.
El modelo recibe el contexto seleccionado y los archivos que solicita mediante
las capacidades permitidas, sin acceso libre al disco.

Para modificaciones y ejecución de comandos:

```bash
./argos review ID
./argos approve ID HUELLA_COMPLETA_MOSTRADA
```

`review` muestra el contenido propuesto, archivo y SHA previo, o los argumentos
del comando y su carpeta. La aprobación es de un uso, ligada a tarea y argumentos.
Core ejecuta esa operación preparada antes de devolver el control al modelo.
Cambiar el archivo o la definición del comando invalida la operación.
La aprobación detallada se hace por CLI en esta versión.

Registra comandos concretos para un proyecto:

```bash
./argos register-command --project ARGOS tests env PYTHONPATH=src python -m unittest discover -s tests -v
```

Registrar no ejecuta. Los comandos corren con los permisos del usuario después
de aprobarlos; no constituyen un contenedor de seguridad. El registro acepta argv,
no una cadena que ARGOS interpole en un shell.

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
Los WAV de captura son temporales, privados y se borran al terminar, cancelar
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

Pendientes: activación por palabra, aprobación por voz, lectura de páginas web
completas, operaciones de archivo adicionales, Blender, impresora, instalador
de autoactualizaciones y GUI Windows. «Actualiza ARGOS» informa de que falta
el instalador y no reemplaza ningún ejecutable.

## Validar

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
python scripts/benchmark.py
```

Las pruebas automáticas usan temporales y audio silenciado; no cambian proyectos
reales, abren aplicaciones, consultan modelos ni activan hardware.
Ver [arquitectura](docs/architecture.md), [validación](docs/validation.md)
y [contrato de ARGOS](src/argos/contracts/ARGOS.md).
