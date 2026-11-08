# ARGOS en casa — integración y fiabilidad

8 de noviembre de 2026. **Instalación actualizada y flujo real de proyectos verificado. El fallo original de arranque no se ha reproducido; no se afirma una causa ni una reparación de ese timeout. La aceptación acústica por el usuario y un inicio real del PC siguen pendientes.** [Mediciones saneadas](home-integration-2026-11-08.json).

## Instalación entregada

La app instalada en `~/.local/share/argos-hermes-pilot` incorpora el repositorio, Projects, Adaptive y Project Map. Conserva Hermes `0073fa98cfcf61c066a919df4b336924720f8463`, con la corrección acotada de persistencia `codex_thread_id` ya validada en el bloque A. No se ha cambiado el proveedor/modelo: conversación y Engineering usan la suscripción Codex / gpt-6-luna low. No se habilitó facturación por API ni otro modelo cognitivo local.

Se creó un entorno nuevo con el gestor nativo y el lock de Hermes, incluyendo MCP 2.3.0 y el grupo de desarrollo. `env` apunta a ese entorno; el anterior se conserva en el backup. Los entornos de voz, modelos CUDA, Peter y su referencia no se reinstalaron. Los hashes de autenticación original, configuración Hermes, voz y referencia coinciden con el backup. Los cambios deliberados son el parche nativo anterior y la allowlist MCP de Projects/Adaptive en la configuración aislada de Codex.

El instalador admite `--adopt-legacy` para exportaciones antiguas cuyo contenido coincide con el manifiesto original; sigue rechazando modificaciones locales desconocidas. Los siguientes despliegues usan `installed-source.json`. También se solicitó una actualización de prompts mediante la API nativa `SessionDB.request_prompt_refresh`: conserva mensajes, IDs y herramientas, y actualiza las instrucciones almacenadas una vez. No se borró ni compactó el historial para acelerar las pruebas.

El menú **ARGOS (Hermes)** y el autoinicio existente apuntan al piloto actualizado. La app quedó abierta por su lanzador normal, con escucha SteelSeries, cancelación de eco y voz preparada. La extensión firmada 0.1.4 está habilitada permanentemente y su puente responde. No se reprodujo música inesperadamente ni se inspeccionaron cuentas, cookies o historial de Firefox.

## Arranque y diagnóstico

| Inicio de proceso | Codex listo | STT CUDA listo | Qwen/Peter listo |
|---|---:|---:|---:|
| Primero, cachés de proceso frías | 7,42 s | 14,77 s | 149,10 s |
| Segundo | 4,77 s | 1,87 s | 18,30 s |
| Tercero, recuperación | 4,30 s | 1,85 s | 18,53 s |
| Cuarto, conversación nueva | 4,12 s | 1,93 s | 18,32 s |
| Conversación original, solo texto | 4,27 s | No iniciado | No iniciado |
| Lanzador habitual final | 5,14 s | 1,98 s | 18,76 s |

Son reinicios de procesos, **no un reinicio del sistema ni una reproducción del login con toda su carga**. El primer arranque de voz sigue siendo costoso. Se observó lectura considerable del modelo, pero eso no establece la causa del timeout de Codex registrado previamente.

Ahora se registran etapas de importación, almacén, proveedor, Hermes, historial, prompt, App Server, recuperación, autenticación, inventario efectivo de herramientas, pesos/referencia/compilación de voz y disponibilidad. Se guardan solo tiempos, estados, tipos de error, códigos conocidos y marcos estructurales; stderr permanece acotado en memoria y no se persiste. El plazo Codex sigue en 45 s, sin reintentos indefinidos. La siguiente incidencia real podrá indicar la etapa que falló.

El texto queda utilizable al prepararse Codex mientras termina el audio. Un fallo de audio conserva el texto y declara disponibilidad parcial. Engineering se inicia al despachar trabajo, no antes de habilitar conversación. `/health` distingue presentación, conversación y voz; una actualización con voz no se acepta como sana hasta que voz y renderer estén preparados. El estado de Projects se carga bajo demanda: no se inicia su propietario ni se escanean discos en cada turno.

## Voz y rendimiento observado

Tres preguntas breves, repetidas durante Engineering:

| Condición | Mediana primer texto | Mediana primer audio preparado |
|---|---:|---:|
| Sin Engineering | 1,16 s | 1,85 s |
| Engineering realmente en ejecución | 1,09 s | 1,65 s |

Todos esos turnos tuvieron cero compactaciones nativas. La repetición puede aprovechar cachés de proveedor/TTS y el contexto creció entre condiciones: **tres muestras no certifican p95 ni ausencia general de regresiones**. La reproducción se simuló en tiempo real para evitar altavoces; no son tiempos físicos de micrófono a oído.

Dos clips sintéticos bilingües recorrieron Qwen → PCM → Whisper turbo CUDA → conversación. La decodificación final tardó 0,43 y 0,42 s para clips de 2,91 y 2,35 s. «Batman» se reconoció correctamente en inglés. La transcripción española conservó errores («QUANTO ES DOS MASTOS»); no se presenta como precisión resuelta. Se corrigió un defecto determinista de selección de idioma: faltaban «es» y cuantificadores españoles, por lo que la voz podía conservar inglés incluso ante esa evidencia española. La repetición seleccionó español y respondió en español. No se añadieron reemplazos fonéticos ni otra inferencia.

El reproductor real consumió 0,8 s de PCM en 0,827 s y drenó EOF. Detener el proceso de reproducción tardó 0,82 ms en una salida nula temporal. Esta medición excluye detección de voz y STT; no mide la interrupción acústica completa.

En las ventanas muestreadas, RSS agregado pasó de una mediana de 5,77 GiB a 6,87 GiB durante Engineering; los máximos fueron 5,84/6,96 GiB. GPU de procesos de cómputo: 5710/5756 MiB. CPU agregada tuvo máximos de 120/131 %, con 100 % equivalente a un núcleo. Incluye páginas compartidas, Electron y herramientas de QA; no representa memoria exclusiva del runtime ni una comparación controlada de CPU. Los contadores de proveedor y caché están en el JSON; no equivalen a una factura ni a un límite global de la suscripción.

Una consulta de proyecto en la conversación original tardó **15,55 s hasta el primer texto y 16,71 s en el turno nativo**, sin compactación. Su prompt contabilizó 179711 tokens, 179200 en caché. Es una observación de latencia pendiente de comparar; no prueba que el historial cause la espera. Las consultas de proyectos aún no tienen una garantía de respuesta equivalente a las preguntas simples.

## Flujo real desde la interfaz instalada

Se autorizó una carpeta nueva `~/Proyectos/biblioteca-3d-casa`, con el proyecto nativo **Biblioteca 3D Casa** (`p_130fb5c4`). No se registró ni modificó una biblioteca real de modelos. El usuario de la prueba pidió indexar STL/OBJ sin modificar originales, etiquetas/notas/búsqueda/SQLite y una CLI con Python estándar. 3MF quedó pendiente.

La primera respuesta describió una propuesta sin ejecutarla. La prueba falló; se corrigieron instrucciones para exigir `projects.propose` y su resultado real antes de afirmar que hay una revisión disponible. Se eliminó además la instrucción obsoleta que negaba la disponibilidad del mapa. La repetición abrió el panel, se aprobó el alcance y creó un solo proyecto.

La primera ejecución Engineering se bloqueó al interpretar una carpeta nueva vacía y Git oculto/sintético como falta del proyecto. No se cambió el sandbox ni se reparó Git. Se aclaró que debe crear el código solicitado en esa carpeta; se inspeccionó el efecto vacío y se concedió **un reintento desde el mapa**. Ambos intentos quedaron registrados. El segundo generó `catalogue.py` y `tests/test_catalogue.py`, ejecutó sus pruebas y solicitó revisión nativa. Durante esa ejecución se mantuvo conversación y se completaron tareas `files.inventory` → `files.types` con su dependencia real.

El verificador independiente ejercitó API y CLI con datos sintéticos: indexación idempotente, etiquetas, notas, búsqueda, persistencia entre procesos y preservación de originales. Inicialmente falló por exigir un README aunque la documentación estaba en el docstring del módulo. El verificador ahora admite ambas ubicaciones; sigue ejecutando las mismas pruebas funcionales y registra hashes del snapshot. El test añadido verifica también que una cadena `--db` en código sin documentación no satisface ese criterio y que no ejecuta código para leer documentación.

Solo después de pasar esa verificación se aceptó el resultado mediante la interfaz. El mapa conserva el intento bloqueado, el intento de ejecución válido y la evidencia firmada del controlador. No se autocompletó la tarea por la afirmación del trabajador. La aplicación creada es **una biblioteca/CLI**, no una app gráfica integrada ni un slicer.

Se comprobó persistencia al cerrar/abrir paneles, reiniciar el backend, abrir una conversación nueva sin ese historial y recuperar la conversación original anterior a la actualización. Las llamadas MCP reales recuperaron el estado aceptado y la decisión 3MF; no regeneraron el proyecto ni repitieron Engineering. Los artefactos se abrieron en el visor acotado. Una prueba de UI inicialmente intentó pulsar un nodo detrás del panel de conversación: se corrigió el harness para enfocar el mapa, sin forzar clicks a través de ventanas.

## Permisos y regresiones

- **359 tests del repositorio**, **40 del contrato nativo Codex/persistencia**, **21 de Projects/ciclo de vida** y **7 de Adaptive**, aprobados.
- **17 comprobaciones Electron reales**: estado vacío, decisiones, edición, cancelación, rechazo, verificación fallida/exitosa, reintento sin replay, selección contextual, ventanas, navegador y layout estrecho. El registro controlado de revisión de esa suite es una fixture nativa, no una segunda implementación por Engineering.
- **25 de archivos**, **21 de almacenamiento/clipboard**, **17 de presentación de investigación**, **26 límites de mantenimiento** y **8 de revisión automática**, aprobadas.
- **19 comprobaciones de comandos con la política instalada**, sin inferencia: escritura autorizada, tablero/controlador/canarios privados denegados, symlink/proc/hijos, red TCP IPv4/IPv6 y UDP denegada, entorno filtrado. Los canarios se conservaron y retiraron. Es un preflight directo con framing sintético de tarea propietaria, no otra ejecución completa Kanban. La ejecución real Engineering y las pruebas nativas son evidencia adicional distinta.
- Inventario efectivo del trabajador: únicamente `kanban_show`, `kanban_heartbeat`, `kanban_comment`, `kanban_block`, `kanban_request_review`; sin apps ni otros servidores MCP. No se debilitó la política para corregir el bloqueo de Git.

La suite Electron usa su perfil de QA con audio silenciado. El backend de voz de prueba tenía captura desactivada y reproducción simulada. La app final usa su lanzador habitual, sin esos modos de QA. No hubo nueva migración de runtime, memoria o dueño de tareas.

## Backup, actualización y rollback

Backup privado: `~/.local/share/argos-home-backups/20261108T130635Z/pilot-before.tar.gz`, 410868984 bytes, 22228 entradas. SHA256 `80aef7a46e38dc08123ef74a7e6e267c84b3b8781885b595301726a77e5dcf79`. Incluye fuente instalada anterior, estado, credenciales/configuración privadas, workspaces y mantenimiento; excluye los modelos/herramientas/vendor completos que no se reinstalaron. Se guardaron aparte el archivo vendor modificado y los accesos de escritorio. El entorno anterior está en `previous-env`.

Se verificó la lectura del archivo, nombres seguros y extracción privada de una selección de fuente/configuración/autenticación con hashes coincidentes. **No se ejecutó un rollback completo de la app**. Para revertir, cerrar ARGOS y respaldar primero el estado actual; extraer el archivo en otra carpeta privada; restaurar la selección anterior de fuente y el archivo vendor guardado; recuperar el entorno anterior y los accesos guardados. Una reversión solo de código no debe reemplazar automáticamente las bases nuevas de proyectos/conversaciones. Restaurar estado al punto anterior perdería cambios posteriores y requiere esa decisión explícita. Los archivos del proyecto de prueba fuera del piloto no se borran con el rollback del runtime.

Despliegue normal posterior: `python scripts/prepare_hermes_pilot.py --projects on --project-map on --adaptive on --register`. `--adopt-legacy` solo fue necesario en la primera incorporación. Si se cambia el contrato, solicitar el refresh nativo de prompts una vez antes de reabrir; conservar la configuración local y el parche/pin validado. No copiar el perfil de desarrollo de otra máquina sobre casa.

## Límite de aceptación y siguiente paso

La app está entregada y el flujo nativo descrito está probado. Quedan: confirmar micrófono/voz/interrupción por oído en el modo habitual, comprobar un arranque real del PC y capturar la siguiente traza si reaparece el timeout. No se certifica aún el p95 de voz, la precisión general STT ni la latencia de consultas en conversaciones largas. Las pruebas de cancelación/rechazo y recuperación nativa por fallos usan las fixtures de las suites; el proyecto real se recuperó después de terminar su ejecución, no durante un corte eléctrico.

**Agent Desktop no se instaló ni habilitó**: su prueba acotada espera estos gates. La [evaluación documental previa](agent-desktop-assessment-2026-11-08.md) distingue AT-SPI de las limitaciones de entrada/captura bajo Hyprland. No se concedió acceso global al escritorio.

Evidencia local adicional: `reports/home-live/` (JSON y capturas), `reports/reliability-ui/`, `ui-workbench/private/startup/<sesión>/latest.json` y `private/home-integration-resources.json` del piloto. Credenciales, audio, bases, rollouts y logs privados no se añaden a Git. Commits de implementación: `d42da20` y `0a5e34e`.

Aceptación manual breve: decir «Argos» sin Espacio, alternar inglés/español e interrumpir una respuesta; abrir el mapa y pedir continuar Biblioteca 3D Casa; en el siguiente encendido comprobar disponibilidad y, si falla, revisar la etapa de arranque registrada. No autorizar 3MF para esta prueba.

## Seguimiento de la prueba manual: invocación sin respuesta

El usuario notificó que no responde a «Argos» y que veía «preparando voz». El backend estaba realmente listo, con escucha y cancelación de eco activas. Se confirmó un defecto de presentación: el caption de preparación no se sustituía al terminar el arranque. El commit `01e2709` lo corrige; seis comprobaciones del renderer pasan, incluyendo conservar la respuesta al volver a standby y distinguir texto disponible de voz disponible. Esta suite usa un servidor de presentación de fixture, sin micrófono, voz, inferencia ni broker de producción.

Dos mediciones de 25 s recibieron exclusivamente ceros, tanto del SteelSeries físico como de su salida AEC (1248 frames por fuente/medición; RMS máximo 0). PulseAudio mostraba mute desactivado/volumen 100 % y ALSA captura activada. Solo se conservaron contadores, nunca audio. Falta confirmar que el usuario habló durante la medición con el auricular encendido y sin mute físico: estos datos no permiten atribuir una causa al dispositivo, al reconocedor o al detector de «Argos». **La aceptación de voz sigue fallida/pendiente; corregir el caption no demuestra que la invocación funcione.** La app se reinició con la corrección visual.

Resultado posterior: con una medición activa sincronizada, el usuario confirmó «Ahora responde». Se observó señal no nula tanto física como AEC y diálogo abierto en el backend. El último turno real registró STT 0,437 s, primer texto 2,56 s y primer audio preparado 3,12 s, con reproducción real y sin compactación. Se detuvieron las sondas adicionales y se dejó la captura normal de ARGOS activa. Esto confirma respuesta a la invocación; la causa del silencio inicial sigue sin establecerse y todavía no hay confirmación manual completa de alternancia de idioma/interrupción.
