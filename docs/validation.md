# Validación 0.2

20 de octubre de 2026. CachyOS/Hyprland, Python del Core 3.14.8;
entorno de voz Python 3.12.15.

## Suite automática

`PYTHONPATH=src python -m unittest discover -s tests -v`

67 pruebas. Conserva las comprobaciones de la base y añade:

- RPC Codex con proceso de prueba, herramientas dinámicas, continuidad de hilo,
  rechazo de peticiones nativas, suspensión por aprobación y cancelación del
  callback de herramienta cuando se cancela su turno.
- Preparación sin escritura, huella exacta, aprobación de un uso, aislamiento
  entre tareas/sesiones y rechazo de un archivo cambiado desde la revisión.
- Lectura/escritura de texto con SHA, conservación de permisos y rechazo de
  rutas ocultas, escapes y enlaces simbólicos.
- Comandos registrados: argv revisable, código de error como FAILED y rechazo
  de una definición modificada después de preparar la operación.
- Reanudación de especialista: primero se ejecuta la operación aprobada;
  el mismo hilo recibe su evidencia. Una comprobación anterior al último cambio
  no se cuenta como verificación del cambio.
- Cola de voz serial, borrado de temporales al cancelar y pausa de notificaciones
  durante captura. Reproductores de prueba silenciosos y consola en pseudo-TTY.

La suite no usa modelos reales, micrófonos, altavoces, aplicaciones del usuario
ni proyectos reales. Todos sus cambios de archivo ocurren en temporales.

## Pruebas manuales de integración

**Codex real**, App Server 0.154.0-alpha.6.2, autenticación ChatGPT:

1. Conversación general estructurada: respuesta en español, aproximadamente
   6,1 s en una muestra con arranque del proveedor.
2. Proyecto temporal con una función de suma defectuosa: lectura real, propuesta
   `files.write`, pausa WAITING_APPROVAL sin alterar el archivo, aprobación de
   la operación exacta, cambio comprobado y continuación del mismo `thread_id`.
3. Segunda prueba con `check.py` y comando registrado `verify`: dos pausas
   separadas, una para escritura y otra para ejecutar el comando; archivo de
   comprobación intacto, salida `addition verified`, exit code 0 y resultado
   `command_passed`. El hilo permaneció igual en las tres fases.

Estas pruebas reales consumen la sesión Codex, pero no cambian el proyecto del
usuario: se ejecutaron en directorios temporales eliminados al terminar.

**Voz local real, sin reproducción**:

- Pocket español generó «Hola. Soy Argos. Todo listo.» en un WAV mono 24 kHz.
  Whisper devolvió «Hola, soy Argos, todo listo.» y lenguaje `es`.
- Pocket inglés generó una segunda frase y Whisper devolvió lenguaje `en`.
  Transcribió el nombre como «Argus», un error de nombre propio observado.
- Una muestra: síntesis española fría 2,99 s para 2,64 s de audio; transcripción
  fría 3,60 s. Síntesis inglesa posterior 1,02 s; transcripción 0,94 s.
  Son muestras aisladas, no una garantía de latencia conversacional.
- Se corrigió incompatibilidad PyAV 19 / faster-whisper 1.2.1 fijando PyAV 16.1.0.

No se ha validado habla humana a través del micrófono físico. La captura usa
PipeWire y se activa solo al pulsar Espacio. No hay prueba de wake word ni
cancelación acústica de eco; TTS se pausa durante la grabación/transcripción.

**Linux y web reales**:

- Bing RSS devolvió cinco resultados para documentación Python; primer enlace
  `https://www.python.org/`. Se comprueba recepción de resultados, no contenido
  ni actualidad de las páginas enlazadas.
- Se descubrieron 30 aplicaciones `.desktop` y se listaron ventanas Hyprland.
- `argos start` abrió kitty con clase `argos`, título `ARGOS` y consola activa;
  la ventana se verificó en el compositor. Core quedó separado de la consola.
- Diagnóstico de voz: Whisper/Pocket conectados, estado idle y sin error.

No se cerraron ventanas ajenas ni se actuó sobre impresoras.

## Latencia local

`python scripts/benchmark.py`, Core real sobre socket temporal:

| Flujo | Muestras | Mediana | p95 |
| --- | ---: | ---: | ---: |
| Saludo | 100 | 0,336 ms | 0,456 ms |
| Estado de tareas | 100 | 0,239 ms | 0,265 ms |
| Medidor de voz | 100 | 0,257 ms | 0,348 ms |

`system.info`: 1,606 ms en una muestra. Estas medidas excluyen STT, inferencia,
TTS y latencia física de audio; no representan velocidad de conversación.

## Límites pendientes

Aprobaciones detalladas por CLI, no por voz. Búsqueda por fragmentos, sin lectura
de páginas completas. Escritura de texto, sin borrar/mover/crear carpetas.
Sin Blender, impresora, activación de autoactualizaciones ni GUI Windows.

## Corrección de idioma y micrófono

71 pruebas aprobadas tras corregir el seguimiento automático del idioma.
Regresiones añadidas: una detección `en` no cambia una voz configurada `es`,
Whisper recibe el idioma seleccionado, PipeWire recibe el dispositivo elegido,
un dispositivo ausente no cae a otro micrófono y el fallo del reproductor
se refleja como error. Todas esas pruebas usan procesos silenciosos o dobles.

En el equipo del usuario la entrada predeterminada era la webcam, mientras la
salida era SteelSeries. Se confirmó recepción de audio por PipeWire en la salida
SteelSeries y el usuario confirmó que se oía, aunque con idioma/voz inadecuados.
Se seleccionó el micrófono SteelSeries expresamente solicitado y español fijo
para reconocimiento, contexto del modelo y síntesis. La calidad subjetiva de
la voz requiere valoración del usuario; un exit code 0 no demuestra inteligibilidad.

## Idioma automático español/inglés

La preferencia fija anterior se sustituye, a petición del usuario, por modo
automático predeterminado. CLI conserva las opciones de idioma fijo.

84 pruebas aprobadas. Se cubren cambios explícitos en ambos idiomas, rechazo
de órdenes citadas/negadas como acciones, saludos cortos frente a detecciones
acústicas equivocadas, conservación del idioma ante palabras ambiguas, contexto
de peticiones simultáneas, idioma persistido por tarea y voces independientes
por elemento de la cola TTS. Solo clips con identificación dudosa se vuelven
a transcribir localmente en el otro idioma.

Prueba de audio generado, sin altavoces: español → respuesta española, inglés
→ respuesta inglesa, «Cambia al inglés» → cambio inglés, «Please speak Spanish»
→ cambio español. En una primera ejecución Whisper deformó el comando español;
se añadió vocabulario de contexto y revisión del segundo idioma para casos
dudosos. La ejecución posterior reconoció las cuatro intenciones. Esto no
garantiza reconocimiento perfecto de cualquier acento, ruido o frase mixta.

Codex real, en el mismo hilo: una pregunta sobre carpetas en inglés recibió
respuesta inglesa; la siguiente pregunta española recibió respuesta española.
El contexto de cada turno tuvo prioridad sobre el idioma del historial.

La instancia abierta quedó en modo auto, con el micrófono SteelSeries conservado.
Se comprobaron por IPC los cambios inglés/español y las respuestas locales,
sin consultar al modelo para cambiar una preferencia.

## Reducción de espera

La salida normal ahora transmite PCM mientras Pocket lo genera. Whisper y la
voz del idioma actual se preparan al arrancar; ambas voces permanecen en memoria
una vez usadas. Decir «Argos, abre Firefox» o «Please open Firefox» conserva la
ruta local, incluyendo el nombre original de la aplicación.

91 pruebas automáticas. Añaden inicio de reproducción antes del final de la
generación, cierre del generador y del reproductor al interrumpir, errores de
reproducción, reutilización del proceso de voz, reinicio tras interrupción y
esfuerzo reducido exclusivamente en General cuando el catálogo lo admite.
Los reproductores de las pruebas son silenciosos.

Muestras locales sin altavoces, mismas frases antes/después:

| Frase | Antes: WAV completo disponible | Después: primer PCM disponible |
| --- | ---: | ---: |
| Español, 28 caracteres, modelo preparado | 533 ms | 69 ms |
| Español, 136 caracteres, modelo preparado | 1776 ms | 120 ms |
| Español tras usar inglés | 853 ms | 68 ms |

Preparación inicial: 2,715 s en segundo plano, sin grabación ni reproducción.
La primera voz inglesa, aún sin cargar, produjo PCM a los 418 ms.
La integración completa Speech → VoiceWorker → VoiceOutput con reproductor
silencioso envió su primer fragmento español a los 71 ms, terminó sin errores
y conservó el proceso preparado. Esto mide entrega al reproductor; no incluye
STT, Codex, la latencia física de PipeWire ni la de los auriculares.

El modelo configurado sigue siendo el mismo. Se confirmó mediante el catálogo
del App Server que admite `low`; General lo solicita por turno y los
especialistas conservan su configuración. Fuente del protocolo:
[documentación oficial de Codex App Server](https://learn.chatgpt.com/docs/app-server).

En dos muestras por configuración de una pregunta breve, el esfuerzo heredado
`high` tardó 4,504 y 4,445 s; `low`, 3,861 y 4,269 s. Una prueba posterior del
bridge completo tardó 5,841 s con arranque y 2,623 s en la continuación inglesa.
La variación remota sigue siendo relevante: estas pocas muestras no establecen
un porcentaje de mejora general ni prometen respuestas instantáneas.

`voice-status` expone tiempos internos del último reconocimiento/despacho y
primera entrega de audio, sin guardar audio ni razonamiento. Interrumpir una
síntesis termina el proceso para descartar sus fragmentos pendientes; la
siguiente petición vuelve a cargar los modelos necesarios.

## Primera conversación y conservación de respuestas

Tras el informe de cortes solo al comenzar, se revisó la preparación: el
calentamiento anterior usaba silencio con VAD y solo preparaba la voz del último
idioma. La nueva preparación sintetiza y transcribe frases de ambos idiomas en
memoria. La consola también prepara la conexión y el hilo Codex del proyecto
seleccionado, sin ejecutar un turno de inferencia ficticio. El estado muestra
la preparación; las capacidades locales siguen disponibles.

Se añade una reserva inicial de 240 ms de PCM. No demuestra por sí sola que
todos los cortes físicos estuvieran causados por falta de buffer, pero evita
iniciar el reproductor con un único fragmento de 80 ms. Se elimina también
el recorte de síntesis a 1200 caracteres y la cuota de una o dos frases del
contrato. Las respuestas recientes inspeccionadas no excedían ese recorte,
por lo que no se atribuye a él el problema de arranque observado por el usuario.

97 pruebas aprobadas. Las nuevas regresiones comprueban conservación completa
de respuestas largas, espera del buffer inicial, igualdad exacta del PCM
generado y entregado (incluido el último fragmento), frases menores que el
buffer, preparación no bloqueante y reintento tras fallo, y reutilización del
hilo preparado sin una llamada adicional al modelo.

Desde un proceso de voz nuevo, con reproductor silencioso:

- Preparación completa de ambos idiomas: 5,006 s.
- Primera frase española después de preparar: primera entrega en 150 ms,
  8 s de audio; transcripción posterior en 1,115 s conservó la frase final.
- Primera frase inglesa: primera entrega en 132 ms, 6,48 s de audio;
  transcripción posterior en 1,102 s conservó la frase final.

Estas muestras incluyen el nuevo buffer y no usan micrófono ni altavoces.
No prueban percepción acústica en los auriculares, conversación sin pulsador,
ni latencia de inferencia remota. La preparación de Codex abre conexión/hilo;
el cálculo de la primera respuesta sigue ocurriendo al recibir la petición.

Codex real: preparar conexión/hilo tardó 0,229 s; la primera respuesta solicitada
en cuatro frases completas tardó 6,614 s y conservó las cuatro frases. Se usó
el mismo hilo preparado. Esta medición confirma que preparar la conexión no
elimina la espera de inferencia remota.

## Mapa de agentes y monitor de actividad

111 pruebas automáticas aprobadas. Cubren proyecciones de agentes ocupados,
en cola y en espera; historial paginado de 109 tareas; aislamiento por sesión;
conversaciones durante un turno y después de una interrupción; paginación de
mensajes completos; migración aditiva desde SQLite v1; comandos de voz exactos
y rechazo de frases negadas o citadas. El sondeo no escribe solicitudes en SQLite.
Los eventos mostrados excluyen cuerpos de herramientas y razonamiento interno.

Una prueba con pseudo-terminal abre el monitor, cambia entre tareas y
conversaciones, redimensiona de 100 × 32 a 80 × 24 y cierra el panel sin detener
Core. El lanzador se prueba con procesos simulados: reutilización de ventana,
enfoque y elevación por dirección exacta, y compatibilidad Lua/legacy de Hyprland.
Las pruebas automáticas no abren aplicaciones reales ni usan micrófono o altavoces.

La activación local conserva las tres tareas históricas y muestra los seis
agentes registrados. Antes de migrar se creó una copia consistente y privada en
`~/.local/state/argos/backups/before-monitors-20261020-141115.sqlite`.
Los paneles reales se comprobaron en kitty, como ventanas flotantes de
1180 × 780. En Hyprland 0.56.2, enfocar una ventana no bastaba para situarla por
encima de otra: se añadió elevación explícita de esa misma ventana, siguiendo
los [dispatchers oficiales de Hyprland](https://wiki.hypr.land/configuring/core/dispatchers/).

Treinta consultas IPC de la proyección tardaron una mediana de 0,477 ms y un
máximo de 0,761 ms en este equipo. No incluyen reconocimiento de voz, inferencia
ni renderizado; los paneles actualizan sus datos aproximadamente cada 750 ms.
Las órdenes se verificaron por la entrada textual compartida con la voz, sin
una nueva prueba acústica. Se conservaron el idioma automático y la selección
del micrófono SteelSeries.

Las conversaciones generales empiezan a registrarse con esta versión. El
historial anterior de tareas permanece disponible, pero no se reconstruyen
mensajes generales antiguos ni conversaciones de Codex ajenas a ARGOS.
