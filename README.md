# ARGOS · Linux 0.3

Asistente con Core Python/SQLite, tareas en segundo plano, conversación y tareas con perfiles Codex explícitos,
investigación web, operaciones del PC y voz local. La consola muestra solo una esfera
ASCII; los detalles se consultan desde otra terminal y las aprobaciones también admiten voz. Esta es la
reconstrucción Linux, no una recuperación del código Windows perdido.

## Reproducir vídeos en Firefox

«Play AC/DC Thunderstruck through Firefox» puede usar `browser.play`: busca en
YouTube, elige un resultado cuyo título coincida con título/artista y comprueba
que el vídeo avance sin estar pausado, silenciado o mostrando un anuncio.
Abrir una búsqueda con `web.open` no equivale a reproducir.

Preparación de esta integración experimental:

```bash
./argos browser-setup
```

En tu Firefox normal abre `about:debugging#/runtime/this-firefox`, pulsa
**Load Temporary Add-on…** y selecciona `integrations/firefox/manifest.json`.
La extensión solo tiene permisos sobre `https://www.youtube.com/*` y Native
Messaging con el puente local. No instala macros, no controla otras páginas y
no transmite cookies. Firefox elimina la extensión temporal al reiniciarse:
hay que volver a cargarla; una instalación permanente requiere empaquetado y firma.

Si Firefox bloquea el inicio, permite reproducción de audio/vídeo **solo para
YouTube** en los permisos de reproducción automática del sitio. En la pestaña
de YouTube, abre Información de la página (Ctrl+I) → Permisos → Reproducción
automática, desmarca «Usar predeterminado» y elige «Permitir audio y vídeo».
El interruptor dentro del reproductor de YouTube controla el siguiente vídeo;
es independiente de este permiso del navegador. La extensión solo informa de
bloqueo de permisos cuando `play()` devuelve `NotAllowedError`; un vídeo pausado
o cargando no basta para atribuir el fallo a Firefox. Los avisos de
consentimiento o inicio de sesión requieren atención manual; ARGOS no los acepta.
La extensión 0.1.2 abre su pestaña en segundo plano, sin activar otra pestaña ni
enfocar Firefox. Las siguientes peticiones reutilizan esa pestaña si permanece
en la URL que ARGOS abrió; si la cierras o navegas a otro lugar, crea otra en
segundo plano. No cambia las pestañas ajenas. Firefox conserva la decisión de
permitir reproducción en segundo plano; ARGOS no toma el foco para forzarla.
No certifica que salga sonido por los altavoces: verifica el estado del vídeo.

Para medios ya cargados, Computer puede usar `media.status` y `media.control`
(`player`, `action=play|pause`, `expected_title`) mediante `playerctl`/MPRIS.
Comprueba el título y que el reproductor sea inequívoco antes de actuar. Estos
controles no seleccionan enlaces de una página de resultados.

## Abrir

Para usar voz hace falta instalar previamente su entorno y modelos locales:

```bash
cd /ruta/a/argos
./argos start
```

Para usar la sesión de Codex con ChatGPT, configura dos perfiles explícitos:

```bash
./argos configure-providers --conversation-provider codex \
  --codex-model gpt-5.6-luna --codex-effort low \
  --codex-complex-model gpt-6-astra --codex-complex-effort high
./argos start
```

General, Computer y Research usan Luna/low; Engineering, Design3D y Printing3D
usan Astra/high. Los modelos deben estar disponibles en tu cuenta; el comando
comprueba acceso sin generar inferencia. No necesita Ollama ni claves API.
La configuración se aplica al siguiente arranque de Core. Una instancia ya
abierta conserva su selección hasta reiniciarla. Las operaciones conocidas
siguen ejecutándose directamente en Core, con sus permisos y aprobaciones.
El adaptador no añade control de Fusion 360: solo ofrece capacidades implementadas.

Como alternativa, puedes instalar Ollama y seleccionar un modelo local:

```bash
./argos configure-providers --ollama-model NOMBRE_LOCAL --codex on
```

Para probar **Nemotron con voz**, manteniendo Ollama para tareas y Codex solo
para escaladas, guarda primero la clave NVIDIA en
`~/.local/state/argos/credentials/nvidia.key` con permisos `0600` y configura:

```bash
./argos configure-providers --ollama-model NOMBRE_LOCAL --codex on --conversation-provider nvidia
./argos start
```

Esta opción es experimental: envía texto, historial público reciente y contexto
de capacidades a NVIDIA; reconocimiento y síntesis de voz siguen siendo locales.
Usa Nemotron 3.5 Super con esquema completo y una sola petición por turno, sin
reintentos ni sustitución automática. La espera de red usa un timeout de 20 s;
no es un plazo total de captura y reproducción. Un fallo no impide que el
siguiente turno del usuario vuelva a intentarlo.
No activa los experimentos de formato de las evaluaciones. El monitor distingue
General/NVIDIA de los especialistas locales. La configuración se aplica al
arranque; para volver a conversación local usa `--conversation-provider ollama`.

En la configuración local, `start` puede arrancar Ollama ya instalado en loopback;
Codex queda reservado a escaladas justificadas. Con los perfiles Codex se omite
Ollama. Ningún modo descarga modelos ni configura arranque automático del sistema.

Arranca Core con los proveedores configurados y voz, y abre una ventana kitty titulada ARGOS.
Reutiliza Core si ya está activo. No configura inicio automático al arrancar Linux.
La consola prepara la conexión o el modelo seleccionado sin generar una conversación ficticia.
Conviene esperar a que termine la preparación inicial antes de hablar.

La conversación se recupera tras reiniciar dentro de la misma sesión y
proyecto. El contexto mantiene hasta 16 intercambios completos y 24.000 caracteres;
el historial completo sigue en SQLite. No recupera hilos remotos ni ejecuta de
nuevo peticiones interrumpidas, y todavía no resume conversaciones antiguas.

En conversación manos libres, una nueva intervención tiene prioridad sobre la
voz pendiente: ARGOS espera mientras hablas y omite respuestas antiguas que
terminan de generarse después. Los fragmentos acumulados se agrupan en orden;
interrumpir la voz no cancela tareas en segundo plano. La detección sigue siendo
por actividad de audio, con 160 ms para confirmar voz y 800 ms de silencio para
cerrar un segmento; no identifica al hablante ni interpreta todas las pausas.

| Tecla | Acción |
| --- | --- |
| Espacio | En modo manual, grabar/enviar; con manos libres, abrir la conversación |
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

Con ella activa, «Argos?» abre la conversación localmente y la esfera pasa a
verde: no consulta al modelo ni añade un saludo hablado. Puedes hacer una pausa
tras el nombre y continuar con la pregunta. «Argos, …» en una sola frase también
abre la conversación y envía directamente la petición. El modelo contesta
con su respuesta natural: una pregunta breve recibe una contestación breve, sin
un «Sir» fijo ni una locución superpuesta. Puedes seguir hablando, responder «sí»
o «yes» y continuar el tema sin repetir el nombre ni hacerlo dentro de un plazo.
«Eso es todo», «hasta luego» o «that's all» devuelve la escucha a espera de «Argos»;
no cancela las tareas en segundo plano.

«Stop listening», «deja de escuchar» o «apaga el micrófono» apaga realmente la
captura, descarta el audio pendiente y confirma una vez en el idioma del turno.
Es un control local, sin inferencia. También silencia los avisos hablados
posteriores, pero conserva las tareas y sus resultados en el monitor. La esfera
deja de estar verde. La preferencia apagada persiste al reiniciar: Espacio permite
captura manual; `./argos voice-config --wake-word on` recupera manos libres.
«Argos» no puede reactivarlo con el micrófono apagado.

Whisper local reconoce la invocación y los finales de turno se detectan por
silencio. La captura permanece abierta entre turnos; los turnos que llegan
durante el reconocimiento o la inferencia esperan en una cola acotada en memoria.
En espera se descartan los textos sin invocación. Con la conversación abierta,
lo que recoge el micrófono se trata como conversación: no identifica al hablante.
Si no responde al nombre, `./argos --json voice-status` muestra
`wake_diagnostics`: tramas recibidas y activas, frases detectadas, transcripciones
vacías, invocaciones no reconocidas, activaciones locales (`activation_only`)
y turnos aceptados, completados o fallidos.
Aceptar una invocación no equivale a haber obtenido o reproducido una respuesta.
Son contadores en memoria,
sin textos de fondo ni audio guardado. Una escucha activada no garantiza que
Whisper haya reconocido el nombre.
`last_stream` distingue una reproducción terminada, interrumpida o fallida y
cuenta bytes generados/enviados, fin de síntesis y salida del reproductor. No
guarda audio; confirma entrega al reproductor, no lo oído físicamente.
La voz añade 200 ms de silencio después del último sonido generado, antes de
cerrar el reproductor; `padding_bytes` lo distingue de la voz. No recorta palabras.
Una respuesta lista se reproduce antes de procesar el siguiente turno en cola;
no espera a vaciar todas las frases pendientes. Los errores públicos del proveedor
se anuncian en el idioma del turno. Un turno correcto limpia el error anterior.
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
Escape apaga también la escucha. Con manos libres activo, Espacio abre la
conversación de la escucha actual sin desactivarla ni cambiar de proyecto/sesión;
los turnos siguen enviándose al terminar de hablar, sin una segunda pulsación.
Para usar captura manual, desactiva manos libres con Escape o `--wake-word off`.
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

«Lista tus capacidades» o «list your capabilities», por voz, solicita una ventana
de inventario sin consultar al modelo ni leer la lista completa en alto. Agrupa
las capacidades por agente y muestra descripción, efecto, necesidad de proyecto
y disponibilidad observada. Se recorre con flechas/PgUp/PgDn; kitty permite
seleccionar texto con el ratón y copiarlo con Ctrl+Shift+C. También se abre con
`./argos monitor capabilities --open`. La respuesta distingue solicitar la
ventana de haber confirmado que su contenido se ve; un fallo del lanzador no
se convierte en una afirmación de éxito.

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
| General | Intenciones conocidas y conversación/interpretación con Ollama local |
| Engineering | Archivos del PC, proyectos nuevos, comandos revisados, workspaces y consulta web |
| Computer | Inventario del equipo, aplicaciones, ventanas Hyprland, archivos, carpetas, workspaces y URLs |
| Research | Buscar, leer páginas públicas y sintetizar con el perfil rutinario seleccionado |
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

«Registra Faro en mi carpeta de proyectos de Linux» puede usar una ubicación
observada: ARGOS comprueba `~/Proyectos`, `~/Projects` y los padres de proyectos
registrados. Si hay una sola candidata, la aporta como base; si hay varias,
resuelve con el contexto o pregunta cuál. No supone que Linux tenga una carpeta
universal de proyectos. `projects.register` permite a Computer registrar una
carpeta existente sin modificar sus archivos ni autorizar futuras ediciones.
Nombre y carpeta idénticos son idempotentes; los conflictos se rechazan.
Una ruta inexistente no se crea durante el registro. La creación de carpetas
sigue usando `projects.create` y requiere aprobación.

Para resolver nombres dictados, el contexto incluye una observación superficial
de las carpetas existentes en esas bases, aunque no estén registradas: hasta 50
carpetas por base, sin enlaces, rutas protegidas ni lectura de sus archivos.
ARGOS puede asociar un nombre hablado con una coincidencia clara y usar la ruta
observada; ante varias coincidencias pregunta por ellas. Los listados recientes
siguen disponibles en la conversación. Al delegar una corrección breve, el
especialista recibe el diálogo previo acotado de esa tarea.

Cada proyecto puede guardar una ficha con alias confirmados, un extracto de su
documentación, fuentes/hash/fecha y observaciones del tamaño y los módulos del
repositorio. `projects.inspect` la actualiza; `projects.context` consulta la
última inspección guardada. La descripción documentada no certifica pruebas ni
el estado del programa. Las tareas se recuperan desde sus registros existentes.

«Trabajemos con X» puede usar `projects.select`: guarda el proyecto de esa sesión
para las próximas peticiones y sobrevive al reinicio. Cambiar de proyecto no mueve
las tareas en curso. Registrar una carpeta por sí solo no cambia la selección.
`projects.alias` guarda un alias confirmado por el usuario y rechaza conflictos.

```bash
./argos select-project some-and-co2
./argos project-context
./argos run projects.inspect --args '{"project":"some-and-co2"}' --wait
./argos select-project --clear
```

ARGOS puede preparar mejoras de un proyecto, proyectos nuevos y cambios
en su propio código con el perfil de Engineering seleccionado. En modo Codex
usa el perfil complejo; en modo local puede escalar tras inspeccionar evidencia.
Primero inspecciona una copia privada, explica un plan
concreto y pide confirmación. Después trabaja en segundo plano con una sola
autorización para los archivos de esa candidata y las pruebas incluidas en el plan.
Puedes seguir conversando y preguntar «¿cómo va esa mejora?» o «qué estás haciendo».
Core aporta el estado observado; no inventa porcentajes de progreso.

```bash
./argos develop "Añade una opción para consultar las tareas fallidas" --target self
./argos develop "Implementa la exportación CSV y sus pruebas" --project mi-proyecto
./argos develop "Prepara la mejora del backend" --project mi-proyecto --scope apps/backend-api
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

Si el proyecto excede ese presupuesto, `scope` elige un módulo relativo ya
identificado por el usuario (por ejemplo `apps/backend-api`). La copia comienza
en ese módulo y conserva el ID del proyecto original; los módulos hermanos quedan
fuera de su alcance. No incluye automáticamente dependencias, recursos o pruebas
del resto del monorepo. La inspección muestra módulos conocidos y una comprobación
acotada del presupuesto por metadatos, sin leer vídeos o binarios.

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

Codex usa la sesión ChatGPT existente mediante App Server
y conserva un hilo por tarea, también después de una pregunta o aprobación. No utiliza claves de OpenAI
API. Los comandos conocidos se resuelven sin consultar un modelo; la conversación
usa el perfil seleccionado en una sola inferencia por turno.
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

La personalidad se define una sola vez en el contrato común de ARGOS. Sus
prioridades son verdad/autorización, instrucciones explícitas, intención y
contexto, canal de entrega y, por último, estilo. Ironía y «sir/señor» son
ocasionales; urgencia, errores y frustración suprimen el humor. «Más corto»,
«solo los nombres» y «explícalo bien» ajustan la respuesta usando la conversación
reciente, sin recortar texto después de generarlo. Los especialistas usan la
misma personalidad: Engineering devuelve un resumen hablado y conserva el
informe técnico completo en el monitor. No hay una segunda llamada de Persona.

«Stop talking» detiene la voz sin añadir otra respuesta ni apagar manos libres.
«That's all, ARGOS» cierra el diálogo y vuelve a esperar el nombre; «stop
listening» apaga el micrófono y los avisos, como se describe arriba.

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

La conversación usa el proveedor seleccionado para esta instalación. Con perfiles
Codex, Luna/low genera el habla completa; con la configuración local se usa Ollama.
No se añade una llamada para clasificación, personalidad o acuses.
La latencia local depende del modelo, contexto y CPU/GPU disponibles; las pruebas
del equipo de oficina no representan el rendimiento del equipo de casa.

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
./argos configure-providers --ollama-model NOMBRE_LOCAL --codex on
./argos serve --voice
# En otra terminal:
./argos console --project ARGOS
```

`configure-providers` guarda `inference.json` en la carpeta de estado de esta
instalación; no descarga modelos ni modifica un Core activo. Oficina y casa
pueden elegir modelos distintos sin cambiar el código. En modo local, `start` reutiliza o abre
Ollama instalado; para `serve` manual, arranca el motor previamente.
`serve --ollama-model NOMBRE --codex`
permite indicar los dos proveedores explícitamente: Ollama para conversación y
trabajo local, Codex únicamente para escaladas. `--codex` ya no selecciona Codex
como interlocutor; para ello usa `--conversation-provider codex`. Sin proveedor, las operaciones conocidas siguen disponibles,
pero no existe sustitución automática por Codex.

La escalada solo se acepta desde una tarea Engineering/Research que haya leído
evidencia y explicado un límite concreto de razonamiento, antes de aprobar o
intentar efectos. No se activa por timeout, error de herramientas, falta de modelo
o de permisos. Conserva ID, alcance y lecturas; registra `PROVIDER_ESCALATED` y
asigna el proveedor a esa tarea. El chat sigue local. La asignación y el cambio
de hilo se guardan de forma atómica. Los hilos antiguos sin asignación requieren
una tarea nueva; no se reanudan como si perteneciesen al modelo local.

El agente local dispone de un bucle acotado de hasta doce decisiones/herramientas
por ejecución. Puede leer, proponer planes y solicitar operaciones del catálogo;
Core conserva las aprobaciones y comprobaciones existentes. Alcanzar ese límite
bloquea la tarea y no consume Codex automáticamente. El motivo de escalada es
una decisión del agente bajo estas condiciones, no una medición objetiva de su
inteligencia ni garantía de que todo trabajo sencillo vaya a clasificarse bien.

Estado: `$XDG_STATE_HOME/argos` o `~/.local/state/argos`, socket privado y SQLite.
El lanzador escribe errores en `core.log`, nunca sobre la esfera.
Los procesos de tu mismo usuario pertenecen al perímetro de confianza.
El filtro de secretos rechaza patrones conocidos; no es una garantía DLP completa.

Pendientes: validación acústica del modo manos libres, lector web dinámico/PDF,
Blender, impresora, aplicación/activación de candidatas con rollback y GUI Windows. «Actualiza ARGOS» informa de que falta
el instalador y no reemplaza ningún ejecutable.

## Validar

Evaluación de personalidad adaptativa con los perfiles Codex configurados
explícitamente (consume cuota de ChatGPT; sin audio ni efectos sobre el PC):

```bash
python scripts/validate_adaptive_persona_live.py --run --engineering --report /tmp/argos-persona.json
```

Los escenarios sintéticos ES/EN recorren intención, ironía, preguntas sinceras,
urgencia, fallos, correcciones, longitud, interrupción y continuidad de una tarea
Engineering. Las operaciones de escritorio están interceptadas; el especialista
solo puede leer un archivo de prueba suministrado en memoria. Se conservan
respuestas públicas, llamadas, tiempos y contadores de tokens, nunca razonamiento
privado. Los resultados requieren revisión cualitativa: no son un porcentaje
automático de semejanza ni una validación acústica.

La separación local/Codex y la calidad conversacional se validan por separado.
La [comparación del equipo de oficina](docs/validation/local-first-2026-10-21.md)
recoge instalación, pruebas con modelos reales, tiempos y fallos. No implica
que la voz o la personalidad estén listas, ni mide el equipo de casa.

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
python scripts/benchmark.py
```

Las pruebas `unittest` usan temporales y audio silenciado; no cambian proyectos
reales, abren aplicaciones, consultan modelos ni activan hardware.
Por tanto, su resultado no demuestra por sí solo que Codex responda bien ni que
el protocolo funcione con una versión/modelo reales. `benchmark.py` mide IPC,
no latencia de conversación con IA.

Evaluación explícita de desarrollo **local con Codex disponible para escaladas**,
usando la sesión ChatGPT y el modelo ya configurados (si escala, consume cuota
y requiere conexión):

```bash
python scripts/validate_codex_live.py --run --ollama-model NOMBRE_LOCAL --report /tmp/argos-codex-live.json
python scripts/validate_codex_live.py --run --ollama-model NOMBRE_LOCAL --self-check --report /tmp/argos-self-live.json
```

Prueba conversación por texto, identidad/límites, una petición ambigua, un plan
de programación, confirmación por texto, conversación durante el trabajo,
consulta de estado, código/pruebas generados, resultado independiente y aviso
de finalización. Solo opera sobre una candidata temporal; no activa micrófono,
síntesis ni altavoces, no instala modelos y no altera proyectos reales. El informe
conserva respuestas públicas, herramientas utilizadas, tiempos y evidencia;
nunca razonamiento ni credenciales. Una pasada es evidencia de esos escenarios,
no una garantía de fiabilidad general ni una validación acústica.

Resultados históricos de la configuración anterior con Codex como interlocutor: [evaluación real del 21 de octubre de 2026](docs/validation/codex-live-2026-10-21.md),
incluyendo el fallo inicial y las ejecuciones posteriores sobre un proyecto
temporal y sobre una copia del propio ARGOS.

Para evaluar contexto y personalidad con conversación real, sin audio:

```bash
python scripts/validate_personality_live.py --run --ollama-model NOMBRE_LOCAL --report /tmp/argos-personality.json
python scripts/validate_local_tools_live.py --run --ollama-model NOMBRE_LOCAL --report /tmp/argos-local-tools.json
```

El primer evaluador recorre 23 turnos en diez conversaciones: presencia, ironía, frustración,
criterio propio, referencias entre turnos, correcciones tras una interrupción,
honestidad, idiomas, aislamiento entre sesiones y estado local. Usa Core y Ollama
reales en un estado temporal, sin conectar Codex; bloquea acciones y no conecta voz. Los criterios
de evaluación no se envían al modelo ni se añaden respuestas de ejemplo.
`--repeat 2` repite con sesiones nuevas. El informe distingue las comprobaciones
estructurales de la valoración del tono: contar palabras o «sir» no demuestra
personalidad. Véanse las respuestas y la revisión en la
[evaluación de personalidad](docs/validation/personality-live-2026-10-21.md).

El segundo evaluador pide leer un dato y crear una carpeta en un proyecto
temporal; comprueba la espera de aprobación, el resultado y que no haya intentos
de invocar Codex. No toca archivos del usuario ni reproduce audio.

Comparación experimental con el proveedor histórico Gemini 3.1 Flash-Lite:

```bash
python scripts/validate_gemini_live.py --run --confirm-free-tier --report /tmp/argos-gemini.json
```

Antes de ejecutarla, comprueba en [Google AI Studio](https://aistudio.google.com/api-keys)
que la clave pertenece a un proyecto del nivel gratuito con facturación desactivada.
`--confirm-free-tier` declara esa comprobación; el programa no puede verificar el
estado de facturación con la clave. La pide con entrada oculta y solo la conserva
en memoria; también admite `GEMINI_API_KEY` si ya está definida. No la pegues en
el chat ni la incluyas como argumento. El nivel gratuito tiene cuotas de uso;
un error de cuota detiene las peticiones, sin reintentos ni cambio de proveedor.
Solo un HTTP 503 (servicio temporalmente no disponible) admite dos reintentos,
tras esperas de uno y dos segundos. El tiempo medido incluye esas esperas y el
informe registra los intentos HTTP. Si persiste el fallo, termina la prueba y
cuenta los turnos restantes como no ejecutados.

Reutiliza los 23 turnos y Core temporal, con inventario marcado como no comprobado
y rutas de ejemplo. Envía escenarios sintéticos y contratos a Google, sin historial
privado, inventario del PC ni audio. Conserva la personalidad compartida y corrige
la identificación del proveedor en el contrato de evaluación. No configura el
daemon ni habilita Gemini en la consola: su calidad conversacional y su integración
completa siguen pendientes de una prueba real. Estado de las comparaciones en
[validación del equipo de casa](docs/validation/home-local-2026-10-22.md).

Para comparar **Nemotron 3.5 Super** mediante el endpoint gratuito de prototipado
de NVIDIA:

```bash
python scripts/validate_nemotron_live.py --run --report /tmp/argos-nemotron.json
```

Si ya guardaste la clave en un archivo privado, puedes reutilizarlo sin pegarla:

```bash
python scripts/validate_nemotron_live.py --run --key-file ~/.local/state/argos/credentials/nvidia.key --report /tmp/argos-nemotron.json
```

La auditoría ampliada añade preguntas obvias, humor y excepciones, órdenes
citadas/negadas, selección de agentes, correcciones, reinicio de Core, aislamiento
de sesiones y cambio de idioma:

```bash
python scripts/validate_conversation_live.py --run --key-file ~/.local/state/argos/credentials/nvidia.key --report /tmp/argos-conversation.json
# Comparación acotada, con tres repeticiones independientes:
python scripts/validate_conversation_live.py --run --key-file ~/.local/state/argos/credentials/nvidia.key --scenario obvious --scenario heldout --repeat 3 --report /tmp/argos-style.json
```

`--contract ARCHIVO` compara una instantánea explícita del contrato solo durante
la evaluación. El informe guarda contrato/huellas, contexto sintético por turno,
historial, decisión pública, comprobaciones y tiempos completos, incluidos fallos.
Las decisiones de acción se observan y se bloquean antes de crear tareas: un
acierto de enrutamiento no demuestra que la operación funcione. Las expectativas
y los presupuestos de palabras nunca se envían al modelo ni recortan respuestas.
La evaluación se detiene si falla el proveedor; distingue turnos omitidos de
intentados. Mediana y p95 corresponden a decisiones válidas; los fallos y las
esperas superiores a cinco segundos también se contabilizan por separado.
Para recorrer casos independientes a pesar de fallos transitorios, se puede
añadir `--independent-scenarios`: omite el resto del escenario fallido y empieza
el siguiente, sin repetir el turno ni cambiar modelo. Detiene todo el lote ante
autenticación/cuota o tres escenarios fallidos consecutivos. La traza HTTP guarda
huella del cuerpo, tamaño y tiempo/estado de cada intento, sin cabeceras privadas.
`--compact-schema` y `--json-object` son dos experimentos excluyentes de formato
de salida. Ambos conservan la validación exacta de decisiones contra el catálogo
del turno tras generar; nunca habilitan operaciones por aceptar JSON. El formato
normal sigue siendo el esquema completo. No son cambios del proveedor de producción.
El tono y la exactitud necesitan revisión humana. No prueba audio ni activa
Nemotron como proveedor de la instalación.

El archivo indicado explícitamente tiene prioridad sobre la variable de entorno.
Debe pertenecer a tu usuario y tener permisos `0600`; no se admiten enlaces simbólicos.

Pide la clave de NVIDIA con entrada oculta, sin guardarla; también acepta
`NVIDIA_API_KEY` si ya está definida. Admite tokens largos; ante una entrada vacía
o con caracteres no válidos para la cabecera, explica el problema sin mostrar la
clave y permite hasta tres entradas en la terminal. Reutiliza los mismos 23 turnos, personalidad,
memoria y bloqueos de acciones que la comparación Gemini, con contexto sintético.
Usa `nvidia/nemotron-3.5-super-vl-120b-a12b` en el endpoint oficial fijo de NVIDIA,
sin razonamiento (`reasoning_effort=none`) y con salida JSON validada por Core.
Las respuestas incompletas se rechazan. Los informes conservan solo texto público,
conteos de tokens, tiempos completos e intentos HTTP; nunca claves o razonamiento.
Solo HTTP 503 se reintenta dos veces; los límites de uso y demás fallos detienen
las peticiones. No cambia el proveedor del daemon ni utiliza Codex.

El [catálogo de NVIDIA](https://build.nvidia.com/nvidia/nemotron-3.5-super-vl-120b-a12b)
publica este endpoint como gratuito para prototipado; disponibilidad y cuotas
dependen del servicio. La configuración de inferencia sigue su
[referencia API](https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3_5-super-vl-120b-a12b-infer).
Las pruebas simuladas verifican el adaptador, pero la aceptación del modelo exige
revisar las respuestas reales y su latencia.

Ver [arquitectura](docs/architecture.md), [validación](docs/validation.md)
y [contrato de ARGOS](src/argos/contracts/ARGOS.md).
