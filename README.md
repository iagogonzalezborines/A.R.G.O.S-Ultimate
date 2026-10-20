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

La esfera es verde mientras escucha, amarilla mientras procesa voz, cian durante
la reproducción y roja si falla la voz. La amplitud procede del WAV reproducido.
El micrófono solo se abre al pulsar Espacio y se limita a 30 segundos.
No hay palabra de activación todavía.

Ejemplos: «hola», «abre Firefox», «lista las ventanas», «enfoca Firefox»,
«busca en la web documentación de Python», «qué estás haciendo»,
«activa modo gaming».

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
./argos doctor --codex
```

`--json`, `--session` y `--state-dir` van antes del subcomando. Los reintentos
pueden usar `--request-id MISMO_ID` con los mismos argumentos. Las tareas
interrumpidas se revisan antes de reanudar; no se repiten al arrancar.

## Voz y dependencias

Core usa Python 3.11+ y su biblioteca estándar. Voz usa un entorno separado
Python 3.12 en `~/.local/share/argos/voice-env`, Whisper base/int8 en CPU y
Pocket TTS con el preset Peter Yearsley, modelos español e inglés. Los modelos
se cargan al usarse y permanecen en el proceso de voz para reducir latencia.
No se carga un modelo por cada agente. El primer turno tarda más.

Para reproducir la instalación en otra máquina con `uv`:

```bash
python scripts/setup_voice.py
```

Descarga paquetes y modelos de forma explícita. PyAV se fija a 16.1.0:
la versión 19 instalada inicialmente era incompatible con faster-whisper 1.2.1.
El runtime usa los modelos descargados en modo offline. Necesita también
`pw-record` / `pw-play`, una sesión PipeWire y, para el lanzador, kitty.

STT y TTS comparten un proceso separado. Las notificaciones esperan mientras
se graba o transcribe, para evitar que el micrófono recoja la propia voz.
Los WAV son temporales, privados y se borran al terminar, cancelar o reiniciar.
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
