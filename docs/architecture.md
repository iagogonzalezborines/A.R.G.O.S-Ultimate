# Arquitectura

```text
Micrófono → Whisper ─┐
CLI ────────────────┴→ Core → intención conocida → capacidad local
                         └→ Codex General → respuesta / capacidad / especialista
                                                        ↓
                                    hilo Codex ligado a tarea y proyecto
                                                        ↓
                                  argos_capability → Policy → operación
                                                        ↓
                                       evidencia SQLite → resultado
                                                        ↓
                                 Pocket TTS → PCM progresivo → PipeWire → RMS → esfera
```

Core, consola y proceso de voz tienen ciclos de vida distintos. Cerrar la consola
no cancela tareas. Hay dos huecos de ejecución y una cola acotada a 64. Las tareas
del mismo proyecto se serializan; esperar ese bloqueo no ocupa un hueco e impide
que un proyecto atasque a los demás.

## Módulos

- `core.py`, `store.py`: tareas, eventos, contexto, idempotencia y recuperación.
- `router.py`: comandos completos conocidos, sin ejecución por coincidencia parcial.
- `codex.py`: App Server persistente, RPC, turnos y herramientas dinámicas.
- `providers.py`: decisiones estructuradas y alternativa Ollama.
- `agents.py`, `contracts/`: capacidades por rol e instrucciones en ejecución.
- `linux_tools.py`: operaciones de archivos, procesos, escritorio y búsqueda.
- `policy.py`: autorización por huella, tarea, proyecto y argumentos.
- `speech.py`, `voice_worker.py`: cola de voz, captura y proceso local de modelos.
- `voice.py`, `console.py`: reproducción, RMS y esfera sin transcript.
- `server.py`, `transport.py`, `launcher.py`: socket, exclusión del Core y apertura.

## Codex

Se comparte un App Server; cada tarea especialista conserva `thread_id`.
General mantiene hilos efímeros por sesión/proyecto. Los turnos tienen salida
estructurada y no se añade una segunda llamada de Persona.
Al abrir la consola se prepara el mismo hilo de sesión/proyecto que utilizará
la primera petición. Esto establece la conexión y el hilo sin ejecutar inferencia
ni introducir mensajes ficticios. Preparación y primera petición comparten el
mismo bloqueo para no crear hilos duplicados.

El proceso se inicia con herramientas nativas, plugins, apps y descubrimiento
de skills desactivados. Usa una carpeta vacía de ARGOS, sandbox de lectura y
sin red en herramientas nativas. Solo el bridge `argos_capability` entrega
operaciones del catálogo del rol. Las peticiones inesperadas se rechazan.
La conexión de inferencia del propio App Server requiere internet.

La cuenta debe ser ChatGPT. Se descartan variables de clave API del entorno
del hijo. Core no cambia configuración ni autenticación de Codex. Los archivos
solicitados mediante herramientas pasan al proveedor; los registros de tarea
conservan esa evidencia filtrada. No se conserva razonamiento.

El protocolo de herramientas dinámicas es experimental y depende de la versión
instalada. Se comprobó con Codex 0.154.0-alpha.6.2.

## Evidencia y autorización

QUEUED significa encolado; RUNNING, que un trabajador posee la tarea.
WAITING_INPUT y WAITING_APPROVAL liberan el trabajador conservando identidad.
Una aprobación contiene la operación preparada y su huella. Al continuar,
Core ejecuta esa operación exacta antes del siguiente turno del modelo.
La autoridad desaparece después de usarla o reiniciar Core.

COMPLETED requiere operaciones registradas; el resultado distingue inspección,
cambios sin comprobación y comando ejecutado correctamente. Un comando fallido
queda FAILED. Un comando anterior al último cambio no verifica ese cambio.
Un turno de modelo sin operaciones queda como propuesta BLOCKED. El detalle
narrativo del modelo no sustituye la evidencia de las herramientas.

Cada solicitud se reserva por ID y digest antes de efectos. Los reintentos
confirmados devuelven su resultado; los resultados inciertos después de una
caída requieren revisión. Reiniciar no reproduce efectos.

Lecturas y acciones rutinarias como abrir/enfocar aplicaciones no necesitan
aprobación adicional. Escritura, cierre de ventana y comandos sí.
Los comandos son argv registrados, acotados en tiempo y salida; ejecutan código
con permisos del usuario. No son una sandbox frente a código hostil.

Las rutas de texto se recorren con descriptores y O_NOFOLLOW. La escritura
prepara un temporal, compara la versión anterior, reemplaza y verifica.
Procesos ajenos de la misma cuenta no se consideran adversarios aislados.

## Audio

Espacio inicia captura PipeWire; la segunda pulsación envía a Whisper; límite
de 30 segundos. No hay wake word. Se pausa TTS durante captura/transcripción.
El modo predeterminado de idioma es automático español/inglés. Whisper aporta
idioma y confianza; las expresiones inequívocas y las órdenes explícitas tienen
prioridad. Palabras compartidas o ambiguas conservan el idioma anterior.
Una identificación acústica dudosa admite una segunda transcripción local en
el otro idioma; las identificaciones claras usan una sola. No se añade un LLM
para detectar el idioma ni traducir respuestas locales.

El idioma de respuesta viaja en el contexto de cada petición y se guarda para
cada tarea. Cada elemento de la cola TTS conserva su propio idioma: una petición
posterior no altera una respuesta pendiente. Los comandos de cambio se resuelven
antes de consultar al proveedor. El contrato del modelo usa el idioma del turno,
con prioridad sobre el del historial. El micrófono puede fijarse por nombre de
nodo PipeWire sin cambiar la configuración global del escritorio.
Un único propietario de reproducción evita solapamientos. Escape detiene audio,
no trabajos ya encolados. El RMS sigue el reloj del proceso de reproducción;
puede diferir por el buffer físico del dispositivo.

El entorno de voz se instala explícitamente con versiones fijadas, separado
del Python del sistema. El runtime no descarga modelos ni guarda grabaciones.
Las pruebas de modelo usan audio generado y no comprueban el micrófono físico.
Al arrancar se sintetizan frases de prueba en ambos idiomas en memoria y se
transcriben para preparar también el codificador y decodificador de Whisper.
Usar silencio con VAD no ejercita ese recorrido. La esfera refleja la preparación
en amarillo y el diagnóstico expone sus errores sin bloquear capacidades locales.

La reproducción comienza con una reserva de 240 ms de PCM y continúa mientras
se sintetiza el resto. La reserva es audio disponible, no una espera fija de
240 ms; normalmente se genera más rápido que su duración. Se conserva el final
del audio, incluso si una frase completa es menor que esa reserva. La brevedad
se expresa en el contrato de conversación y nunca con un recorte del texto.

## Siguientes integraciones

Activación por palabra, aprobaciones por voz, lectura web, Blender, impresión,
actualización mediante candidato/pruebas/activación/rollback y GUI Windows.
No se anuncian como capacidades conectadas.
