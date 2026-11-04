# Arquitectura

```text
Micrófono → pulsador / invocación local → Whisper ─┐
CLI ────────────────┴→ Core → intención conocida → capacidad local
                         └→ perfil conversacional → respuesta / capacidad / especialista
                                                        ↓
                                    perfil de tarea → hilo ligado a tarea y proyecto
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
- `providers.py`: decisiones estructuradas y bucle local de herramientas con Ollama.
- `inference_config.py`: selección explícita de proveedores por instalación.
- `agents.py`, `contracts/`: capacidades por rol e instrucciones en ejecución.
- `linux_tools.py`: procesos, escritorio y búsqueda.
- `host.py`: observaciones Linux acotadas y comprobación de requisitos por capacidad.
- `filesystem.py`: rutas absolutas, páginas/tramos, árboles, papelera y workspaces.
- `development.py`: planes, autoridad por tarea, ejecución delegada y evidencia de candidatas.
- `development_workspace.py`: copias privadas, manifiestos/diffs y pruebas Linux en bubblewrap.
- `web_reader.py`: HTTP público, extracción de texto/enlaces y paginación.
- `wake.py`: endpointing PCM y filtro local de invocación.
- `echo.py`: cancelación de eco PipeWire temporal y supervisada para interrupción.
- `approval_dialog.py`: revisión hablada y códigos de una operación.
- `policy.py`: autorización por huella, tarea, proyecto y argumentos.
- `speech.py`, `voice_worker.py`: cola de voz, captura y proceso local de modelos.
- `voice.py`, `console.py`: reproducción, RMS y esfera sin transcript.
- `server.py`, `transport.py`, `launcher.py`: socket, exclusión del Core y apertura.
- `telemetry.py`, `monitor.py`, `panels.py`: proyecciones de solo lectura,
  diagrama/monitor de terminal y apertura/enfoque de ventanas propias.

## Observación

El contrato común versionado contiene las prioridades y tendencias de la
personalidad; no existe un modelo Persona o Response Composer adicional.
`agents.contract` comparte esas reglas entre General y especialistas;
`local_contract` reutiliza la misma sección para otros proveedores. El recordatorio
de voz es breve y se añade solo al turno de conversación. Core conserva el
control determinista de estados, aprobaciones y respuestas de operaciones.
La inferencia resuelve correcciones, referencias, intención, humor y longitud
con el historial público acotado; no se introducen diagnósticos emocionales ni
clasificaciones por otra llamada al modelo.

El monitor añade `capabilities`, una vista agrupada del catálogo observado, con
texto completo envuelto y desplazamiento. La voz solicita esa ventana para las
órdenes conocidas de inventario sin pasar por General. El lanzador devuelve
`requested`/`focused`, no un acuse de contenido mostrado; Core no afirma recepción
visual. En ausencia/fallo de ventana conserva el inventario en la respuesta de
diagnóstico y explica el fallo brevemente. Los resultados Engineering ya tienen
`speech` y `detail`: solo speech se encola en TTS y detail conserva el informe en
los eventos del monitor. No se recorta ni se reescribe la respuesta del modelo.
General sigue sin una superficie para informes arbitrarios separados de su
respuesta; el contrato no anuncia esa capacidad.

`monitor.snapshot` devuelve estados de agentes, contadores y páginas de tareas
o conversaciones de la sesión seleccionada. `monitor.detail` devuelve páginas
de mensajes públicos o eventos de un registro de esa misma sesión. Ambas rutas
son de lectura y no escriben el caché de solicitudes al sondear. El estado de
ocupación procede de RUNNING/QUEUED y las esperas tienen categoría propia.
La conexión verificada del proveedor se distingue de su mera configuración.

General registra entrada y respuesta visible en `conversations` y `messages`,
vinculadas a sesión, proyecto e hilo; una respuesta que delega lleva también el
ID de tarea. Los especialistas reutilizan sus eventos existentes: objetivo,
preguntas, respuestas, progreso público y resultados de capacidades. No se
serializan trazas ni eventos internos de razonamiento del proveedor.
Al recuperar Core, los turnos RUNNING pasan a INTERRUPTED sin reproducirse.
La migración aditiva SQLite de versión 1 a 2 conserva proyectos, tareas y eventos.

La versión 3 añade `project_profiles`, `project_aliases` y `session_projects` sin
alterar los registros existentes. Las fichas contienen evidencia documental con
fecha/hash, alias explícitos y un presupuesto acotado por metadatos. Sus fuentes
son datos no fiables como instrucciones. La selección persistente pertenece a
una sesión y solo se usa por defecto cuando la petición no indica otro proyecto;
una selección explícita por petición no modifica la preferencia guardada.
No reasigna tareas ni concede autorizaciones de escritura. General ve el registro
de nombres/rutas/alias y solo la ficha del proyecto seleccionado; especialistas
asignados reciben únicamente su proyecto. Los ejecutores internos de candidatas
no se serializan en el registro público.

El diagrama y monitor se ejecutan en procesos separados. Su cierre no afecta
al Core, y no hay controles que aprueben ni cancelen trabajo desde estas vistas.
El mapa mantiene siempre su función; T abre la otra ventana. El monitor tiene
pestañas de tareas/conversaciones y M abre el mapa. Se usan kitty y curses de
la biblioteca estándar. El lanzador limita enfoque y geometría a ventanas
ARGOS identificadas por vista, carpeta de estado y sesión. En Hyprland admite
el protocolo Lua actual y las órdenes anteriores, sin cambiar reglas persistentes.
General recibe `context.panels` y puede devolver una decisión `panel` con
`view=agents|tasks|capabilities`; Core abre la ventana y registra su propia respuesta.
La validación rechaza otras vistas, argumentos adicionales y solicitudes de
panel desde especialistas. Esto permite interpretar peticiones naturales y
aclaraciones sin limitar la función a frases exactas ni añadir otra inferencia.

## Codex

`conversation_provider=codex` selecciona la política `codex_profiles`: un App
Server Luna/low para General/Computer/Research y otro Astra/high para
Engineering/Design3D/Printing3D. Modelo y esfuerzo se fijan explícitamente por
instalación y se verifican con `model/list`; no se heredan del modelo global
del IDE. La selección del rol corresponde al Core sin una inferencia adicional.
La afinidad persistida incluye proveedor, modelo y esfuerzo; un cambio no reanuda
automáticamente un hilo con otro perfil. Las capacidades directas siguen locales.
No requiere Ollama, NVIDIA ni claves API; usa la sesión ChatGPT.

General recibe el historial público acotado del Core en hilos efímeros y libera
su suscripción al terminar. Preparar la conexión no genera texto. El esquema
limita los nombres de herramientas al catálogo del turno y se valida antes de
actuar. Las tareas conservan sus hilos y el bridge sujeto a permisos. Telemetría
expone modelo/esfuerzo por rol. Un fallo no cambia de proveedor automáticamente.

Los siguientes modos alternativos se conservan por selección explícita:

La opción explícita `conversation_provider=nvidia` conecta `nvidia.py` solo a
General mediante `Core.conversation_provider`. El intérprete local original
conserva las tareas y sus asignaciones; Codex mantiene las condiciones de escalada.
Preparación, historial, identidad de proveedor y monitor de General siguen al
proveedor conversacional seleccionado. No se importan conversaciones de otro
proveedor. Los errores de NVIDIA no llaman al modelo local ni a Codex.
El adaptador usa una credencial privada fuera del repositorio, endpoint fijo sin
proxies/redirecciones, salida pública completa y validación contra el catálogo
del turno. No acepta razonamiento privado ni llamadas nativas a herramientas.
La política se identifica como `explicit_remote_conversation_local_tasks`; sin
esa opción se conserva la política local que se describe a continuación.

En la configuración Ollama, General y los especialistas usan el modelo local. Codex está
conectado a un slot separado, reservado para tareas complejas. Sin un perfil conversacional explícito, el adaptador
rechaza General antes de iniciar App Server y Core rechaza inyectarlo
como intérprete conversacional. La falta/fallo del modelo local nunca activa
Codex como fallback. No se añade inferencia de clasificación o Persona.

El agente local puede solicitar `escalate` desde Engineering/Research con un
motivo público concreto. Core exige lectura previa registrada y ausencia de
aprobación de plan o intento de efecto. No se escala por dependencias, errores
o permisos. La asignación por tarea y el borrado del hilo anterior se guardan
atómicamente con `PROVIDER_ESCALATED` antes de volver a encolar. La evidencia
previa se entrega al nuevo proveedor, sin reproducir efectos. Los hilos previos
a esta separación, sin asignación de proveedor, no pueden reanudarse.

Un App Server se comparte entre las tareas escaladas; cada una conserva su hilo.
La conversación permanece en Ollama, que recibe los turnos públicos recientes
sin depender de memoria remota. Su bucle local utiliza las mismas capacidades
y política del Core, con doce pasos máximos y sin escalada automática al agotar
el límite. `inference.json` selecciona el modelo de cada instalación, de modo que
la oficina y la casa no heredan necesariamente la misma configuración.

El proceso se inicia con herramientas nativas, plugins, apps y descubrimiento
de skills desactivados. Usa una carpeta vacía de ARGOS, sandbox de lectura y
sin red en herramientas nativas. Solo el bridge `argos_capability` entrega
operaciones del catálogo del rol. Las peticiones inesperadas se rechazan.
Se mantiene `code_mode_host` habilitado: los modelos actuales lo necesitan para
despachar herramientas dinámicas. No habilita shell, navegador ni operaciones
del anfitrión; las llamadas del puente siguen pasando por Core. Desactivarlo
permitía conversar pero impedía utilizar las herramientas, un fallo descubierto
en una evaluación con inferencia real que no detectaban los proveedores simulados.
La conexión de inferencia del propio App Server requiere internet.

La cuenta debe ser ChatGPT. Se descartan variables de clave API del entorno
del hijo. Core no cambia configuración ni autenticación de Codex. Los archivos
solicitados mediante herramientas pasan al proveedor; los registros de tarea
conservan esa evidencia filtrada. No se conserva razonamiento.

El protocolo de herramientas dinámicas es experimental y depende de la versión
instalada. Se comprobó con Codex 0.154.0-alpha.6.2.

## Evidencia y autorización

El servidor inyecta `LinuxEnvironment` en Core; Core consume su interfaz de
inventario y disponibilidad sin implementar sondeos Linux. Al arrancar y antes
de construir contexto o ejecutar capacidades se renueva la caché si han pasado
30 segundos. Un bloqueo asíncrono agrupa consultas concurrentes. La lectura de
metadatos se ejecuta fuera del bucle de eventos; los sondeos `pactl`/`hyprctl`
corren en paralelo, con un segundo de plazo y 64 KiB máximos cada uno.

Las fuentes están prefijadas: platform/os-release, campos concretos de cpuinfo y
meminfo, identificadores PCI/controlador en DRM, statvfs de raíz/home, indicadores
de sesión permitidos, presencia de una lista de ejecutables, UID efectivo y
metadatos de fuentes/salidas de audio. No se invoca captura, reproducción,
instalación, autenticación ni consultas externas. Se filtran los datos públicos;
los fallos parciales producen estados sin incluir stderr ni valores privados.
La GPU se identifica por IDs, no mediante un catálogo remoto; no se inventan
dispositivos si el sondeo no los observa.

`context.environment` contiene observaciones fechadas con fuente, estado y
caducidad. `context.capabilities` añade `implemented`, disponibilidad ternaria,
estado, motivo y fecha. Un adaptador no comprobado nunca publica disponibilidad
positiva por defecto. Ficheros, comandos y web mantienen comprobaciones por
operación: la presencia del adaptador no demuestra permisos sobre una ruta ni
conectividad a una fuente. Core rechaza bloqueos conocidos antes de aprobación
o ejecución; la política de autorización y la verificación de resultados siguen
siendo independientes del inventario.

`environment.inspect` es una consulta IPC sin escrituras ni tareas, usada por
`system-status`; permite renovación explícita y contexto de proyecto. `doctor`
usa el mismo informe y puede obtenerlo sin Core. `system.inspect` es una capacidad
de lectura de Computer y Engineering: renueva el inventario compartido y guarda
la evidencia de esa operación en la tarea. El sondeo automático no se persiste.
El monitor reutiliza el inventario en memoria; no lanza sondeos por cada fotograma.

QUEUED significa encolado; RUNNING, que un trabajador posee la tarea.
WAITING_INPUT y WAITING_APPROVAL liberan el trabajador conservando identidad.
Una aprobación contiene la operación preparada y su huella. Al continuar,
Core ejecuta esa operación exacta antes del siguiente turno del modelo.
La autoridad de una operación individual desaparece después de usarla o reiniciar Core.

El flujo `develop` crea una tarea Engineering y una copia privada, incluyendo el
destino `self` resuelto desde la instalación por el adaptador inyectado en Core.
El proveedor asignado investiga con lecturas y propone `development.plan` (explicación hablada,
pasos y argv exactos de pruebas); se suspende en WAITING_APPROVAL sin escrituras.
La huella vincula tarea, origen, copia, base y plan. Core comprueba de nuevo el
hash de la candidata al confirmar y conserva la autoridad solo en memoria.
Cada efecto posterior sigue pasando por Policy con una autorización de un uso;
solo se emite tras validar la capacidad, la tarea y sus rutas dentro de la copia.
Los comandos del anfitrión no reciben permisos derivados de este plan.

`development.check` ejecuta un índice de la lista de pruebas aprobada, mediante
bubblewrap sin red, home, escritorio ni audio. Solo monta runtimes de sistema en
lectura y la candidata en escritura. Tiene límite de 120 s y 64 KB de salida;
cancelar termina el grupo de procesos. Nunca degrada a comandos sin aislamiento.
`development.review` mide hashes, archivos modificados y pruebas sobre el hash
actual. Un resultado sin candidata modificada/revisada queda BLOCKED; pruebas
acordadas fallidas, ausentes o invalidadas por cambios quedan FAILED. Una lista
de pruebas vacía produce `changes_not_tested`, nunca una verificación inventada.
Los artefactos contienen la candidata, diff y manifiesto; no se aplican al origen.

La respuesta final del mismo proveedor de tarea sirve como aviso. Core espera al final
de una respuesta conversacional en curso antes de encolarlo; TTS serializa audio.
General recibe identidad observada y tareas de su sesión; `task_status` selecciona
evidencia de Core. No existe llamada adicional para Persona o notificaciones.
Un plan oído por completo habilita un sí de corta duración en esa sesión cuando
solo hay una pregunta/aprobación pendiente. Una interrupción, cambio de tema,
caducidad o reinicio lo invalida. La revisión por código sigue disponible. Ninguna
decisión del modelo autoriza planes; al reanudar tras interrupción se vuelve a
planificar sin reproducir efectos y con autorización nueva.

COMPLETED requiere operaciones registradas; el resultado distingue inspección,
cambios sin comprobación y comando ejecutado correctamente. Un comando fallido
queda FAILED. Un comando anterior al último cambio no verifica ese cambio.
Un turno de modelo sin operaciones queda como propuesta BLOCKED. El detalle
narrativo del modelo no sustituye la evidencia de las herramientas.

Cada solicitud se reserva por ID y digest antes de efectos. Los reintentos
confirmados devuelven su resultado; los resultados inciertos después de una
caída requieren revisión. Reiniciar no reproduce efectos.

Lecturas y acciones rutinarias como abrir/enfocar aplicaciones no necesitan
aprobación adicional. Escritura, cierre de ventana y comandos sobre el anfitrión sí.
Los comandos son argv registrados, acotados en tiempo y salida; ejecutan código
con permisos del usuario. No son una sandbox frente a código hostil.

Las rutas de texto se recorren con descriptores y O_NOFOLLOW. La escritura
prepara un temporal, compara la versión anterior, reemplaza y verifica.
Procesos ajenos de la misma cuenta no se consideran adversarios aislados.

## Acceso al PC y proyectos nuevos

Las capacidades de archivo aceptan rutas absolutas sin proyecto. Solo las relativas
requieren una base seleccionada. Se conserva el filtro de credenciales y el recorrido
O_NOFOLLOW. Los archivos UTF-8 se inspeccionan por streaming, incluyendo el filtrado
de secretos entre fragmentos. Las páginas y parches usan desplazamientos de caracteres,
no bytes; SHA-256 identifica el archivo completo. Los parches escriben un temporal,
comprueban de nuevo la versión y verifican el resultado. Los archivos grandes no
se entregan enteros al modelo. El trabajo de disco se ejecuta en un hilo y las
operaciones de archivo del Core se serializan. Si llega una cancelación durante
ese paso, se espera su resultado y se registra evidencia antes de marcar cancelada
la tarea; no se repite al recuperar.

Copias y movimientos no reemplazan destinos. La huella de árbol incluye nombres
ordenados y huellas del contenido, y rechaza enlaces/archivos especiales. Borrar
es renombrar a una papelera hermana recuperable; su ruta aparece en la evidencia.
No hay borrado irreversible automático. Los procesos del mismo usuario siguen
en el perímetro de confianza; esto no aísla frente a modificaciones externas hostiles.

`projects.create` crea el directorio tras aprobación; Core registra y vincula
el proyecto a la tarea, sin cambiar de hilo. `projects.register` verifica una
carpeta existente con la misma barrera de rutas (sin enlaces ni credenciales),
registra únicamente metadatos y vincula esa tarea. La evidencia
`project_registered` se emite después de guardar el registro; no concede
permisos para escribir archivos. CLI y agentes comparten la validación de rutas,
la idempotencia nombre/carpeta y el rechazo de conflictos.

`filesystem.project_locations` aporta candidatas existentes (`~/Proyectos`,
`~/Projects` y padres de proyectos registrados), su procedencia y una base
solo si es única. No recorre árboles ni lee archivos. General recibe el registro
para resolver referencias; un especialista con proyecto seleccionado solo ve
el suyo. Computer/Engineering sin proyecto pueden resolver una ubicación antes
de registrarla. Los contratos usan esta evidencia y los detalles del usuario
antes de preguntar por rutas; una inscripción directa no necesita otra llamada
de planificación. Las rutas de carpetas concretas se verifican al ejecutar.

La observación `project_locations.directories` enumera únicamente subcarpetas
directas (máximo ocho bases, 50 entradas por base, 512 entradas inspeccionadas),
fecha y estado/completitud. No lee contenido ni registra carpetas automáticamente.
No se incluye el inventario de hermanos en el contexto de un especialista con
proyecto asignado. General distingue el inventario del registro de proyectos.
`task_context` añade proyecciones de listados anteriores solo de la misma sesión
y proyecto: nombres, ruta, continuación y advertencia de que son observaciones
anteriores, sin copiar contenido de archivos.

Antes de devolver una delegación interpretada, Core guarda `CONVERSATION_CONTEXT`
en la tarea: hasta ocho pares/8.000 caracteres de diálogo público y tres listados.
El especialista recibe esa instantánea como `conversation_handoff`. No consulta
conversaciones futuras, no cambia su autoridad y no ejecuta las órdenes antiguas.
Las correcciones a una pregunta pendiente pueden completar la instantánea de
una tarea anterior que aún no la tuviera. La incorporación es local, sin otra
llamada al modelo.

`commands.exec` prepara argv/cwd
revisables sin registro previo, y compara la definición con el evento aprobado
antes de ejecutarla. `workspace.open` solicita una ventana de VS Code o terminal
Codex tras revisión; el trabajo posterior de esa sesión externa no es evidencia
de la tarea. No se cambian modelos ni configuración de autenticación.

## Investigación y revisión hablada

`web.read` resuelve DNS público, conecta a la IP validada y verifica TLS con el
hostname original. Cada redirección vuelve a comprobarse; no usa cookies, perfiles
privados ni proxies del entorno. Limita descarga, tiempo y redirecciones. Extrae
HTML/texto y enlaces; no ejecuta scripts. Las páginas se entregan por fragmentos
con huella del texto, URL final y fecha de consulta. Research combina estas
operaciones con búsquedas y conserva la síntesis pública con fuentes. Texto
externo y enlaces son evidencia no confiable, nunca autorización.

La revisión hablada es local, sin inferencia. Selecciona una tarea pendiente
inequívoca de la sesión y emite un código de cuatro palabras con dos minutos de
vigencia, vinculado a tarea y fingerprint. Solo la orden completa `aprueba CODE`
(o `approve CODE`) consume el código y llama al mismo flujo de aprobación exacta
que la CLI. El código no sobrevive al proceso; cambiar la operación, cancelar o
consumirlo invalida su autoridad. Un sí aislado y una decisión del modelo no pueden
aprobar. El contenido de una escritura permanece revisable por CLI; la locución
indica ruta, longitud y huella, sin leer todo un archivo de código en voz alta.

## Audio

Espacio inicia captura PipeWire; la segunda pulsación envía a Whisper; límite
de 30 segundos. La escucha opcional de «Argos» usa PCM PipeWire, endpointing
por energía y Whisper local; está apagada por defecto. La invocación abre un diálogo
persistente, sin vencimiento por silencio ni reinvocación entre turnos. La invocación
sola se resuelve localmente: abre el diálogo, sin inferencia, journal conversacional
ni saludo hablado; la esfera pasa a escucha. Así una pausa tras el nombre no
crea una petición remota que bloquee la pregunta posterior. La invocación con
petición y las comprobaciones explícitas de presencia se envían al modelo:
su respuesta pública se sintetiza una vez, sin saludo fijo ni llamada adicional
de Persona. El contexto pide concisión proporcional a la pregunta, no una frase
predefinida ni un honorífico obligatorio.

La captura PCM permanece abierta y drena continuamente, separada del consumidor
de reconocimiento/inferencia por una cola de cuatro segmentos en memoria.
Cada segmento tiene una generación asignada tras 160 ms de actividad sostenida.
Una intervención nueva pausa la salida también durante reconocimiento/inferencia,
sin esperar a que ARGOS empiece a hablar. Core conserva el resultado y la evidencia
del turno anterior pero no encola su voz si su generación ha quedado atrás; una
revisión de plan no oída tampoco habilita aprobación hablada. No cancela tareas.
La pausa permanece mientras se captura voz o quedan segmentos por procesar.
El consumidor espera el final de la intervención y agrupa los segmentos pendientes
en orden antes de transcribirlos, en lugar de producir una respuesta por fragmento.
El lote está limitado al segmento tomado y los cuatro de la cola (hasta 100 s de
PCM si todos alcanzan el máximo de 20 s). Si se llena la cola se descarta el segmento
pendiente más antiguo para conservar la corrección reciente; se cuenta y señala
la pérdida en diagnóstico. No se conservan grabaciones ni se reproducen efectos.
Los errores de turnos superados se registran en diagnóstico sin interrumpir la
entrada nueva. Los errores
`ArgosError` ya saneados se localizan al idioma del turno, conservando su causa;
una petición posterior correcta limpia el error anterior. Los tiempos de despacho
se registran también al fallar. Se distinguen invocaciones aceptadas de turnos
completados/fallidos. En NVIDIA, el timeout de red es 20 s para voz y texto,
sin reintentos ni proveedor sustituto; no limita la longitud del texto generado
ni garantiza una latencia total de 20 s incluyendo captura, colas y síntesis.
La salida PCM expone `last_stream`: estado final, bytes generados/enviados,
fin de síntesis y código de salida del reproductor. Un final normal exige EOF
del generador y salida correcta del reproductor; una cancelación se distingue
de ese final. No contiene audio/texto ni certifica lo oído en el dispositivo.
Tras EOF de síntesis se envían 200 ms de silencio, manteniendo abierto el flujo
para dar margen de vaciado al recorrido de audio antes de cerrar el reproductor.
Los bytes de voz se preservan literalmente y `padding_bytes` cuenta solo ese
silencio añadido. Una interrupción explícita cancela también ese margen.
`EchoCancellation` mantiene un proceso `pw-cli --monitor load-module` con
`libpipewire-module-echo-cancel` y WebRTC. Publica nodos privados con nombres únicos;
fija el micrófono seleccionado y la salida predeterminada antes de crearlos. No
cambia los dispositivos predeterminados ni escribe configuración persistente.
`pw-record` recibe la fuente filtrada y toda reproducción propia (TTS o WAV) pasa
por el sumidero de referencia. La presencia de los nodos se comprueba antes de
habilitar interrupciones. Terminar el proceso elimina sus nodos. Véanse las
referencias de [cancelación de eco](https://docs.pipewire.org/page_module_echo_cancel.html)
y [módulos locales de pw-cli](https://docs.pipewire.org/page_man_pw-cli_1.html).

En diálogo abierto, ocho tramas consecutivas de actividad tras AEC (160 ms)
interrumpen la voz o invalidan su entrega pendiente sin esperar al final del turno.
El reproductor se termina antes
de esperar a que cierre el generador de síntesis. Se descarta la locución pendiente,
se pausa la cola de voz y la captura conserva el preámbulo y el resto de la frase
mientras se cierra TTS. No cancela tareas ni modifica aprobaciones. El siguiente
turno recibe `interaction.speech_interrupted`; el contrato pide atender la nueva
intervención sin repetir automáticamente la explicación ni un acuse prefijado.
Solo se envía ese indicador y el texto reconocido: no audio al modelo ni a SQLite.
La cancelación de síntesis puede cerrar el proceso local compartido; el siguiente
reconocimiento lo reinicia y puede pagar el coste de recargar modelos.

Si AEC no está disponible al arrancar, continúa por turnos y descarta PCM durante
TTS. `voice.state` expone `barge_in_available`, `echo_error` y `voice_interruptions`.
Perder el proceso AEC activo detiene la escucha y libera la ruta de reproducción;
no vuelve silenciosamente a un micrófono sin filtrar. La detección es por energía,
no identifica voces ni garantiza distinguirlas de ruido sostenido. La eficacia
acústica y la latencia real requieren validación en el equipo del usuario.
En espera se ignora lo que no invoque ARGOS; en diálogo abierto los turnos se
procesan sin identificar al hablante.
Una despedida explícita cierra el diálogo y descarta sus segmentos pendientes;
la respuesta a esa despedida también pertenece al modelo. No cancela tareas.

Apagar el micrófono es distinto de despedirse: `stop_listening` es una intención
local ES/EN que ejecuta `voice.stop`. El controlador de este comando tiene una
tarea retenida por Core, protegida de la cancelación del consumidor de audio
que está cerrando; Core la cancela durante su propio cierre. Así se evita esperar
circularmente al consumidor manos libres o manual. Tras cerrar captura/AEC y
vaciar la voz, se permite únicamente la confirmación `listening_stopped` aunque
la generación anterior haya caducado. `voice.quiet` persiste el silencio de avisos;
Espacio o habilitar manos libres lo levanta. Los resultados y tareas se conservan.

General recibe hasta 16 intercambios completos de la misma sesión/proyecto,
con un máximo de 24.000 caracteres de historial. Al reiniciar recupera la última
conversación pública del mismo proveedor local; no importa hilos remotos ni
mezcla proyectos o sesiones. Los turnos fallidos/interrumpidos permanecen en el
journal, pero quedan fuera del contexto conversacional para evitar reintroducir
órdenes sin respuesta. El recorte conserva pares completos y no resume ni
reescribe lo dicho. Sigue siendo una ventana acotada, no memoria ilimitada.
El contexto compacto del modelo conserva también la descripción, el efecto y
la necesidad de proyecto de las herramientas: sus nombres y argumentos no
bastan para explicar su comportamiento ni distinguir lectura de modificación.
Las preguntas de tareas pendientes se exponen con su ID; la decisión `reply`
selecciona una de ellas y Core devuelve a esa tarea el texto original del usuario.
Se revalida sesión, proyecto y WAITING_INPUT; nunca se usa esta vía para aprobar.
No se crea un modo global de especialista ni se ejecuta una inferencia extra.
Escape desactiva manos libres y guarda la preferencia. Con la escucha activa,
Espacio abre su diálogo actual sin cambiar proyecto/sesión, cerrar el capturador
ni alterar la preferencia persistida; no inicia una segunda captura. Las siguientes
pulsaciones son idempotentes y no cancelan inferencia, reproducción ni turnos
pendientes. Con manos libres apagado conserva el pulsador manual de grabar/enviar.
Se pausa TTS durante captura/transcripción.
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

Lectura web dinámica/PDF, validación acústica de manos libres, Blender, impresión,
aplicación/activación/rollback de candidatas de actualización y GUI Windows.
No se anuncian como capacidades conectadas.


## Firefox y reproducción multimedia

`browser.play(query)` pasa por la política habitual de Core como efecto rutinario.
Su puente Native Messaging está restringido al ID `firefox@argos.local`, con
socket Unix `firefox.sock` de permisos 0600 bajo el estado privado de ARGOS. No
expone un servidor HTTP ni recibe JavaScript, selectores o comandos arbitrarios.
El manifiesto nativo se registra mediante `browser-setup`; la extensión temporal
se carga manualmente en el Firefox del usuario. La selección no modifica su perfil.

La extensión abre una pestaña propia de resultados de YouTube, limita candidatos
a enlaces de vídeos con ID válido y selecciona el primero cuyo título normalizado
contenga los términos de búsqueda. No usa botones de anuncios ni acepta avisos.
El criterio es correspondencia textual, no certifica versión oficial/artista:
si se necesita una edición concreta, incluirla en la petición. Comprueba ID del
vídeo, ausencia de anuncio, estado no pausado/no silenciado, volumen positivo y
tiempo avanzando antes de devolver `browser_video_advancing`. No certifica audio
físico. Las restricciones de autoplay permanecen bajo control de Firefox.

Desde 0.1.2 la creación usa `active: false` y la navegación no activa pestañas ni
ventanas. La extensión recuerda únicamente el ID y la última URL de su pestaña;
la reutiliza en siguientes órdenes si sigue allí. Si está cerrada o el usuario
ha navegado, crea otra en segundo plano. Una cancelación solo cierra una pestaña
creada por ese trabajo, nunca una reutilizada. No se deduplican órdenes distintas
por parecido textual ni se considera éxito la mera apertura de una pestaña.

Una sola petición de navegador está activa; las siguientes reciben busy.
Timeout, desconexión o cancelación no reenvían el trabajo. La cancelación se
transmite al complemento y cierra su pestaña si el trabajo seguía activo.
Los resultados web y títulos se tratan como datos, no como instrucciones.

`media.status`/`media.control` son capacidades Computer para reproductores MPRIS
ya cargados. `playerctl` se ejecuta con argv, sin shell; nombres de reproductor,
acciones y salida están acotados. Play/pause son explícitos, nunca toggle.
El título esperado y la instancia única se revisan antes de actuar, y el estado
se vuelve a comprobar después. MPRIS no ofrece selección de resultados web ni
una operación atómica que garantice que otra pestaña no cambie justo al actuar.

## Alcance de candidatas por módulo

`develop` acepta `scope` opcional solo para `target=project`. Debe ser una carpeta
relativa existente bajo la raíz registrada, sin `..`, rutas absolutas ni enlaces.
La candidata toma ese módulo como raíz; la tarea conserva el ID del proyecto.
Si aún falta elegir proyecto, el alcance se conserva mientras espera la respuesta.
La aprobación queda ligada a esa fuente/candidata y sus comprobaciones; los módulos
hermanos y el repositorio original quedan fuera de sus efectos. No se cambian
permisos de dependencias o de ejecución por seleccionar un módulo.

La ficha incluye un escaneo de metadatos limitado por el presupuesto de candidatas
(128 MiB/10.000 archivos), con contadores, completitud y módulos `apps/*`/`packages/*`
identificados por manifiestos. No se leen los contenidos de vídeos/binarios. Los
contadores incompletos son cotas inferiores, no el tamaño exacto del repositorio.
General usa el módulo indicado por el usuario o pide elegir entre los observados;
no excluye recursos de código arbitrariamente para forzar una copia completa.
