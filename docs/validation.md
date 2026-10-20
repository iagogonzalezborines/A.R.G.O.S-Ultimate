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
