# Fiabilidad, Project Map y proyecto real — 6 de noviembre de 2026

La integración está implementada e instalada en **ARGOS (Hermes)** con Projects, Project Map y capacidades acotadas activados. Se conserva Hermes como autoridad de proyectos, tableros, claims y ejecución. No se ha añadido un scheduler, una base de proyectos ni otro proveedor. La aceptación humana y del hardware de casa sigue pendiente.

[Prueba real y medidas](reliability-2026-11-06/execution.json) · [evaluación semántica](reliability-2026-11-06/quality.json) · [medición de RAM](reliability-2026-11-06/quality-resources.json) · [aplicación generada](reliability-2026-11-06/model-library/README.md).

## Integración y seguridad

- A conserva el pin Hermes `0073fa98cfcf61c066a919df4b336924720f8463` y el hash validado de su reparación de persistencia. Se reutilizan el aislamiento de Codex, la denegación de red y de credenciales/controlador, las herramientas nativas limitadas y el permiso de carpeta de B.
- `review_dispatch` debe estar desactivado antes de admitir trabajo. Los trabajos nuevos tienen cero reintentos automáticos. Una ejecución anterior exige inspección y un permiso de reintento del usuario, ligado al último registro nativo; máximo dos. Para Engineering también se comprueba que los archivos no hayan cambiado desde ese permiso. Un claim consume la admisión, incluso si falla el arranque. Los casos ambiguos quedan bloqueados.
- Verificar y aceptar son acciones separadas del usuario. El controlador ejecuta perfiles fijos en el sandbox de lectura existente, sin red y con límites de tiempo, memoria y salida. La aceptación exige un resultado satisfactorio y los mismos hashes. La evidencia se firma en comentarios nativos: el trabajador no puede fabricar una aprobación con su propia prosa o metadata. La clave permanece privada en `project_state/argos-evidence.key`.
- Cancelar utiliza la terminación nativa con identidad del proceso. CAS protege proyecto y tarea; rechaza acciones antiguas, dobles clics y accesos cruzados. Las decisiones pendientes no se despachan a Codex.
- La aceptación puede crear una fila administrativa de Hermes: el mapa la distingue de un intento de ejecución. Los archivos declarados mediante `artifacts` o `files` se comprueban en disco; no se ejecutan al abrirlos.

## Experiencia y recorrido real

El menú ofrece **Proyectos** y **Escribir a ARGOS**. El mapa presenta objetivo, requisitos, decisiones, tareas, dependencias, responsable, intentos, archivos y evidencia. Permite modificar tareas no iniciadas, iniciar, cancelar, verificar, aceptar, rechazar y autorizar un reintento mediante el Broker. Se actualiza mientras está visible; cerrar/minimizar deja de observar y no cancela trabajadores. Menú y General reutilizan el mismo panel. El proyecto y la tarea seleccionados se transmiten como contexto acotado, sin convertir la selección en autorización. La entrada escrita comparte la conversación existente, tiene cola acotada y rechaza credenciales reconocibles.

El recorrido se ejecutó con Electron/Playwright, General y Codex reales, contra carpetas y registros nativos desechables:

1. Una petición natural creó la propuesta «Biblioteca 3D de prueba». El clic de autorización creó una sola carpeta y proyecto.
2. General guardó requisitos y decisiones, despachó el prototipo y creó una decisión de 3MF dependiente de él. La investigación obtuvo documentación oficial de `sqlite3` y `pathlib` con URL, fecha y hash. Es recuperación de fuentes acotada, no un investigador general autónomo.
3. Codex produjo `catalogue.py`, pruebas y documentación. La aceptación independiente comprobó indexación STL/OBJ, deduplicación, etiquetas, notas, búsqueda, persistencia y conservación de originales.
4. La inspección detectó que faltaba una CLI de uso. La nueva prueba `model_library_v2` falló antes de corregirla. Se creó una tarea de corrección dentro del mismo alcance; Codex añadió comandos y pruebas conservando la API. Pasaron la aceptación API+CLI y **6 tests** ejecutados por el controlador en sandbox. El artefacto final incluye instrucciones de uso.
5. Durante la corrección se ejecutaron inventario y conteo de extensiones, con dependencia nativa, mientras Engineering seguía activo. Cada tarea de Engineering tuvo **un intento**, sin repetir la implementación inicial. La decisión de 3MF queda pendiente; no hay integración de impresoras o slicers.
6. Se cerraron y reabrieron paneles y se reiniciaron servidor, conversación y Electron. «Continúa el proyecto…» recuperó los registros existentes y la decisión pendiente, sin crear otro proyecto. Se verificaron y aceptaron los resultados desde la interfaz.

La primera investigación terminó en un segundo, antes del inicio efectivo del primer trabajador; no se presenta como solapamiento medido. El inventario/conteo sí se solapó con el segundo trabajador. Durante el primero, consultar aplicaciones tardó **4,85 ms** y una respuesta conversacional **5,97 s**; Engineering seguía ejecutándose. Son observaciones de este equipo, no garantías de latencia. La concurrencia sigue acotada a un escritor Engineering y un auxiliar, compartiendo admisión nativa y presupuesto de memoria.

Capturas inspeccionadas: [autorización](reliability-2026-11-06/scope-approval.png), [verificación](reliability-2026-11-06/verified-artifacts.png), [archivos](reliability-2026-11-06/project-files.png), [decisión pendiente](reliability-2026-11-06/pending-decision.png), [desconexión](reliability-2026-11-06/disconnected.png), [vacío](reliability-2026-11-06/map-empty.png), [bloqueo](reliability-2026-11-06/map-blocked.png), [panel estrecho](reliability-2026-11-06/map-narrow.png), [función desactivada](reliability-2026-11-06/map-unavailable.png), [prueba fallida](reliability-2026-11-06/map-verification-failed.png), [arranque de la instalación habitual](reliability-2026-11-06/installed-startup.png).

## Calidad local y selección

18 casos con respuestas esperadas, sin juez LLM: extracción literal, requisitos, objetivos, dependencias, clasificación, resumen e información insuficiente. Se mide exactitud, cobertura, omisiones, invenciones, tiempo y memoria comunicada por Ollama; una segunda pasada toma muestras de RSS del proceso y sus descendientes cada 50 ms.

| Alternativa | Resultado observado | Uso admitido |
|---|---|---|
| Qwen3 0.6B, digest fijado | 9/18 exactos; extracción literal 6/6; resto insuficiente | Solo borrador de extracción de elementos, con revisión semántica humana |
| General existente, sesiones independientes | 10/18 exactos en esta prueba de IDs/JSON | El resultado tampoco acredita clasificación estructurada universal; el flujo de proyectos se prueba por separado con efectos reales |
| Baseline de coincidencias léxicas | 6/18 | No se usa como clasificador semántico |
| Normalización determinista de lista explícita | Resultado exacto del fixture, sin inferencia | Preferida para listas; inventario y agregación también usan funciones |

En la pasada comparativa local: mediana **0,647 s**, rango **0,474–3,931 s**. Ollama comunicó unos **747 MiB** y cero VRAM. El máximo RSS sumado muestreado en la segunda pasada fue aproximadamente **899 MiB**; puede contar páginas compartidas y no es el pico único de RAM del sistema. El modelo se liberó al terminar. Seis ejemplos no certifican extracción general: la salida permanece en revisión y nunca autoriza ni modifica requisitos por sí sola.

El registro comprueba modelo/digest y perfil medido, sin llamada de IA para enrutar. En la instalación habitual no se configura ni arranca automáticamente inferencia local: aparece no disponible hasta preparar su configuración privada revisada. Las funciones deterministas, investigación acotada y Codex funcionan sin ella. El laboratorio conserva el modelo descargado; no se descargó otro.

## Regresiones y problemas encontrados

- Core: **353 tests**.
- Projects/lifecycle: **20 tests** (incluyen las regresiones B), con verificación falsa, cambios tras autorización/verificación, CAS concurrente, claims interrumpidos, deduplicación y denegaciones de alcance.
- Project Map nativo: **3**; adaptativo: **7**; evaluador/perfiles: **3**.
- Archivos: **25**; almacenamiento/clipboard: **21**; fronteras de investigación: **17**; arranque: **10**; mantenimiento: **26 + 8**; guardia de direcciones del navegador: **13**.
- Electron: **17 comprobaciones** de mapa/controles con registros nativos de prueba y un caso de función desactivada. Incluyen rechazo, error por motivo vacío, reintento sin reproducción, cancelación y anchura reducida. La ejecución real anterior aporta la prueba con Codex y artefactos, no sustituida por esos fixtures.
- Entrada escrita: preparación, límites, rechazo de credenciales, FIFO y ausencia de audio. Salida PCM real a un **null sink** temporal: drenaje e interrupción correctos; no se usaron altavoces.

Se corrigieron: importación del lector en el auxiliar, mapa antes de crear el tablero auxiliar, reconocimiento de metadata `files`, doble panel, menú fuera de pantalla, colisión del control orbital, desplazamiento involuntario del escritorio al enfocar elementos de paneles, acciones que perdían el archivo abierto y respuesta de disponibilidad antigua en pruebas. Los controles se repitieron después de los cambios. Dos ejecuciones de automatización sufrieron intercepción de clics/capturas recortadas con varios paneles; el recorrido se recuperó sin repetir Engineering y la prueba final de dos paneles a pantalla completa pasó. La variación del compositor/DPI requiere la comprobación de casa indicada abajo; no se afirma cobertura de todos los gestores de ventanas.

## Relevo para casa

Estado funcional: implementación integrada; falta aceptación humana/hardware. Commit: el commit que incorpora este informe y su evidencia. No copiar credenciales ni bases privadas mediante Git. El artefacto exportado no contiene modelos personales ni la base SQLite del proyecto.

Sobre el piloto A/B ya restaurado y validado en casa, desde este repositorio:

```sh
python scripts/prepare_hermes_pilot.py --projects on --project-map on --adaptive on --register
```

Abrir **ARGOS (Hermes)**. Para trabajar sin iniciar audio, el lanzador admite `~/.local/share/argos-hermes-pilot/bin/argos-hermes --text-only`. El instalador preserva configuración, login y cambios locales; comprueba el pin de A. En una máquina sin sus dependencias, seguir primero la restauración A: este comando no descarga Hermes, voz ni modelos. Inferencia local opcional: [SETUP](../adaptive/SETUP.md); no habilitar un modelo nuevo sin revisar su digest/perfil.

La continuidad entre conversaciones/reinicios está probada **en la misma instalación**. Trasladar un proyecto a otra máquina requiere sus archivos, registro nativo y clave privada de evidencia, con las rutas y autorizaciones revisadas. No hay sincronización automática entre equipos; recrear solo una carpeta no migra el tablero. No se ha construido esa migración fuera de alcance.

Aceptación manual pendiente, limitada al entorno real:

- Micrófono de casa: wake word, interrupción, eco, salida de voz/persona y alternancia con la entrada escrita; GPU y latencia de STT/TTS reales.
- Resolución/DPI y gestor de ventanas: abrir Proyectos y conversación juntos, seleccionar una tarea, redimensionar, minimizar y reabrir; comprobar teclado y legibilidad.
- Firefox habitual: extensión firmada disponible en casa, sesión y reproducción. No se deshabilitaron firmas para suplir el XPI ausente aquí.
- Confirmar que el comportamiento y los mensajes resultan naturales con una petición propia. Las pruebas automatizadas no certifican la experiencia humana completa.

Límites deliberados: máximo 100 tareas por tablero en el mapa, perfiles de verificación registrados, investigación pública limitada a dos documentos, un escritor por instalación y reintentos explícitos. Engineering pendiente requiere un despacho autorizado; el mapa no promete ejecutar automáticamente todas las tareas pendientes. La recuperación conserva estado/evidencia y evita repetir efectos; no garantiza reanudar la misma instrucción suspendida de Codex.
