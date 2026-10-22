# Conversación local en casa — 22 de octubre de 2026

El requisito es conservar la naturalidad, continuidad y rapidez de la conversación
anterior con Codex. Los tests de estructura no certifican ese requisito. La
comparación usa los escenarios existentes, sin respuestas prefabricadas ni un
segundo modelo que juzgue o reescriba las contestaciones.

## Entorno y método

Ryzen 7 5800X, RTX 4060 de 8 GB y entorno de voz anterior conservado. Ollama
0.40.8 se instaló manualmente en `~/.local/share/argos/ollama-runtime`, siguiendo
la [documentación oficial](https://docs.ollama.com/linux). Los pesos están en
`~/.local/share/argos/ollama-models`, fuera del repositorio. El servicio iniciado
por ARGOS escucha en loopback y tiene cloud desactivado. No se instaló un servicio
de arranque del sistema. No se ha usado inferencia real de Codex en estas pruebas.

Los escenarios de conversación ejecutan Core y el modelo local reales con estado
temporal, sin audio y con acciones bloqueadas. La prueba de herramientas permite
solo lectura y creación de un directorio dentro de su proyecto temporal.
Se revisan las respuestas públicas; nunca
se guardan trazas de razonamiento. El contexto es de 16.384 tokens y se mantiene
la personalidad compartida. Los tiempos son de respuesta textual completa,
sin STT, TTS ni latencia acústica. El escritorio estaba abierto.

## Resultados

| Configuración | Primera respuesta medida | Mediana posterior | Valoración |
| --- | ---: | ---: | --- |
| Qwen 3 8B, seis turnos | 50,288 s | 2,664 s | Rechazada: no comprende la ironía ni el fallo de la copia en el mismo disco. |
| Qwen 3.5 4B, 23 turnos (22 con modelo) | 22,835 s | 1,465 s | Rechazada: rápida, pero pierde referentes y afirma que el equipo está bien sin suficiente evidencia. |
| Qwen 3.5 9B, 23 turnos (22 con modelo) | 8,344 s | 3,900 s | Rechazada para conversación: conserva Helios, pero confunde referencias y sigue pidiendo rutas ante preguntas conceptuales. |

El 8B descargó 29 de 37 capas en GPU; parte del modelo/contexto permaneció en
CPU. El 4B descargó 33 de 33 capas en GPU; el 9B, 28 de 33. La primera petición
del 9B se midió después de descargarlo y puede beneficiarse de la caché del sistema:
no es una comparación controlada de arranque en frío. Son muestras de tareas diferentes y
no deben usarse como ranking general de modelos. La comparación histórica de
Codex tenía una mediana de 4,864 s en 22 turnos; ocurrió otro día y no constituye
un benchmark simultáneo controlado.

Fuentes completas:

- [Qwen 3 8B](home-qwen3-8b-initial-2026-10-22.json).
- [Qwen 3.5 4B](home-qwen35-4b-2026-10-22.json).
- [Qwen 3.5 9B](home-qwen35-9b-2026-10-22.json).
- [8B con contexto mínimo](home-qwen3-8b-minimal-context-2026-10-22.json): también
  falla la interpretación de la copia de seguridad.
- [4B sin restricciones de formato](home-qwen35-format-diagnostic-2026-10-22.json):
  diagnóstico que modifica contexto/formato, no un ensayo del runtime completo.
  Mejora la explicación final, pero persisten ofertas innecesarias y afirmaciones
  poco justificadas. No se ejecutó ninguna acción.
- [4B con razonamiento](home-qwen35-thinking-diagnostic-2026-10-22.json): el primer
  turno agotó 2.048 tokens en 33,856 s sin contenido final. La variante se detuvo;
  no se guardó razonamiento privado. No es aceptable para conversación rápida.
- [4B con contrato aclarado](home-qwen35-4b-context-revision-2026-10-22.json):
  se distingue una pregunta conceptual de una operación y un inventario de un
  diagnóstico. Las aclaraciones permanecen en el contrato, pero no corrigieron
  suficientemente la conversación. No se añadieron respuestas prefabricadas.
- [9B con texto antes de la decisión](home-qwen35-9b-answer-first-2026-10-22.json):
  diagnóstico con transformación de formato solo en el proceso de evaluación;
  mejora una explicación, pero mantiene ofertas innecesarias y minimiza el riesgo
  de una copia en el mismo disco. No se adoptó en producción.
- [9B con muestreo recomendado por Qwen](home-qwen35-9b-sampling-2026-10-22.json):
  variante indicada en el propio informe. Intentó delegar durante una broma,
  bloqueado antes de efectos por el evaluador. No se adoptó en producción.
- [Herramientas con 9B](home-qwen35-9b-tools-2026-10-22.json): cinco comprobaciones
  aprobadas con la configuración normal: lectura y respuesta, espera de aprobación,
  creación posterior de directorio, archivo original intacto y cero intentos de
  Codex. Este resultado no certifica calidad de conversación ni desarrollo completo.

## Continuidad y arranque

Se corrigió la recuperación de la conversación local tras reiniciar Core, por
sesión, proyecto y proveedor. No se reutilizan hilos remotos. El modelo recibe
hasta 16 intercambios completos, con un máximo de 24.000 caracteres; los turnos
interrumpidos o fallidos permanecen en el historial pero no se reintroducen como
órdenes sin responder. No hay resumen automático ni memoria ilimitada.

Se añadió carga anticipada de Ollama al preparar la consola, mediante una
petición vacía sin inferencia conversacional, según la
[API documentada de precarga](https://docs.ollama.com/faq#how-can-i-preload-a-model-into-ollama-to-get-faster-response-times).
Comprueba primero que el modelo es local. Conserva los pesos diez minutos desde
el último uso; una descarga de memoria posterior puede volver a causar espera.
Esto evita incluir la carga de pesos en la primera petición si la preparación
ya terminó; no elimina el cálculo del primer prompt.

235 pruebas automáticas aprobadas, incluidas recuperación con reapertura real
de SQLite, aislamiento entre sesiones/proyectos/proveedores, historial más largo,
conservación de pares completos, exclusión de turnos fallidos y precarga sin
mensajes, generación ni conexión a Codex. Las cinco pruebas del adaptador de
evaluación Gemini usan HTTP simulado: contexto y una sola llamada, descarte de
razonamiento, rechazo de truncamiento, cuota sin reintentos, operaciones inválidas
y bloqueo de redirecciones. No usan micrófono o altavoces. Las pruebas simuladas
no certifican compatibilidad ni calidad de la API real.

## Decisión y siguiente comparación

El usuario exige coste adicional cero: solo quiere pagar su suscripción de Codex.
No se seleccionó ninguno de los tres modelos como predeterminado, no se creó
`inference.json` y no se activó la consola de voz con un modelo inferior. Los
modelos descargados quedan disponibles para evaluación. El cambio de proveedor
conserva pendiente su validación de calidad; esta revisión no la da por resuelta.

Se verificó que [Groq dispone de plan gratuito](https://console.groq.com/docs/rate-limits).
Como referencia publicada, `openai/gpt-oss-120b` tiene 30 peticiones/minuto,
1.000/día, 8.000 tokens/minuto y 200.000/día; los límites efectivos deben comprobarse
en la cuenta. Un contexto largo puede consumir el límite por minuto rápidamente,
por lo que estos máximos no equivalen a conversación continua garantizada.
La [subida al plan de pago](https://console.groq.com/docs/billing-faqs) requiere
añadir un método de pago. No se creó cuenta, no se configuró facturación ni se
envió conversación a este proveedor. Queda pendiente una cuenta gratuita y clave
configurada localmente para poder comparar sus respuestas; no se presupone calidad
equivalente a Codex por el tamaño del modelo.

El usuario aclaró después que anteriormente usaba Gemini. El contexto recuperado
confirma `gemini-3.1-flash-lite` como proveedor histórico y Whisper/Pocket para voz.
La siguiente comparación prioriza ese proveedor, cuya
[tarifa oficial mantiene un nivel gratuito](https://ai.google.dev/gemini-api/docs/pricing#gemini-3.1-flash-lite).
No se encontró una clave configurada en las variables de entorno de esta sesión.

Se preparó `scripts/validate_gemini_live.py`, reutilizando los escenarios y el
constructor de mensajes del proveedor local. Mantiene Core temporal y bloquea
acciones, pero sustituye identidad/rutas por ejemplos y omite el inventario del
equipo antes de enviar contexto a Google. Adapta la identificación local del
contrato a Gemini, sin cambiar la personalidad. Esa diferencia de contexto queda
registrada y debe considerarse al comparar con las mediciones locales.

El adaptador usa el endpoint `generateContent`, descrito en el
[documento oficial de descubrimiento REST](https://generativelanguage.googleapis.com/$discovery/rest?version=v1beta),
salida JSON y validación de decisiones del Core. La clave solo está en memoria y
en la cabecera HTTPS; los informes no guardan cuerpos de errores ni razonamiento.
La prueba requiere `--run --confirm-free-tier`: la segunda opción es la declaración
del operador de que el proyecto no tiene facturación, no una garantía verificable
por el cliente. La primera versión detenía las peticiones ante cualquier fallo de API.

Al cerrar esa primera implementación quedaba pendiente introducir una clave del
proyecto gratuito y ejecutar la comparación. No se cambió el proveedor del ARGOS
que utiliza el usuario.

### Primera prueba de Gemini aportada por el usuario

El usuario ejecutó la prueba con su clave: la primera respuesta fue «I am here.»,
en 3,203 segundos, con 2.303 tokens de entrada y 43 de salida. Esto confirma una
petición autenticada válida y compatibilidad básica del esquema; no permite
valorar todavía naturalidad o continuidad. La segunda petición devolvió HTTP 503
en 1,445 segundos. Los errores posteriores del informe no eran nuevas llamadas:
el adaptador había bloqueado la red, pero el evaluador seguía recorriendo escenarios.

Se corrigió el diagnóstico: según la
[guía de Google](https://ai.google.dev/gemini-api/docs/troubleshooting), HTTP 503
indica indisponibilidad temporal, no demuestra una clave incorrecta. El evaluador
admite ahora dos reintentos de ese código tras uno y dos segundos, con el mismo
modelo y petición. No reintenta HTTP 429, errores de autenticación, formato ni
fallos de conexión. No hay cambio automático de proveedor. El tiempo del turno
incluye los reintentos y se registra además el número de intentos HTTP.

Si el proveedor queda detenido, el evaluador finaliza y contabiliza los turnos
restantes como no ejecutados, sin generar fallos repetidos ni tiempos de respuesta
artificialmente bajos. Se comprueban recuperación tras 503, agotamiento del límite
de tres intentos y parada del evaluador usando Core real con HTTP simulado.
La suite completa tras esta corrección pasa 238 pruebas en 5,696 segundos.
La comparación real completa sigue pendiente; la clave introducida por el usuario
no se conservó en disco ni está disponible para repetirla automáticamente.

### Segunda prueba real de Gemini

El usuario ejecutó el evaluador corregido. Se conserva el
[informe completo de esa ejecución](home-gemini-31-flash-lite-2026-10-22.json):
18 turnos intentados, 23 peticiones HTTP y cinco turnos restantes sin ejecutar.
La prueba terminó ante un 503 que persistió durante los tres intentos permitidos.
Hubo 16 respuestas conversacionales aceptadas por Core, con mediana de 4,282 s
y máximo de 17,853 s. Tres de esas respuestas necesitaron reintento. La latencia
incluye HTTP y esperas; no incluye voz. No es una comparación simultánea con Codex.

La comprensión mejora respecto a los candidatos locales: recuerda Helios y,
cuando se le pide ser serio, explica que original y copia se pierden si falla
el disco. Sin embargo, durante las bromas introduce ofertas de inspección no
solicitadas y una ironía ambigua; en preguntas sencillas se extiende con lenguaje
formal. El contrato ya pide evitar ofertas rutinarias: no se añadieron ejemplos
ni respuestas prefabricadas para hacer pasar estos escenarios.

En el primer escenario de honestidad («Mira esto en mi setup…») solicitó
`system.inspect`, con el anuncio de que examinaría la configuración. El evaluador
de conversación bloqueó esa operación antes de ejecutarla. Esto no demuestra
que se efectuase una inspección ni que Gemini afirmase haberla terminado; sí
impide aprobar ese escenario como respuesta puramente conversacional a una
referencia visual sin imagen disponible.

Resultado: candidato todavía no aceptado para sustituir la conversación anterior.
Quedan sin completar honestidad, cambio de idioma, aislamiento entre sesiones y
estado local en esta ejecución. La calidad y la disponibilidad deben validarse
por separado. No se cambió el modelo de la consola ni se realizaron nuevas
llamadas a partir de la lectura del informe.

## Nemotron 3.5 Super mediante NVIDIA

Tras obtener la clave, el usuario autorizó guardarla en un archivo privado.
Se leyó desde el portapapeles sin mostrar su contenido y se guardó fuera del
repositorio, en el directorio privado de credenciales de ARGOS, con permisos 0600
(directorio 0700). El evaluador acepta ahora `--key-file`: valida propiedad,
permisos y archivo regular, rechaza enlaces y no introduce la clave en los
prompts, informes ni SQLite. La suite completa pasa 252 pruebas en 6,099 segundos.

Se evaluó `nvidia/nemotron-3.5-super-vl-120b-a12b` en el endpoint de prototipado
de NVIDIA con `reasoning_effort=none`, el mismo contexto sintético usado para
Gemini, la personalidad compartida y validación de decisiones por Core. Los
resultados no contienen voz, efectos reales ni conexiones a Codex.

- [Ejecución inicial](home-nemotron-super-initial-2026-10-22.json): nueve respuestas
  aceptadas, mediana 1,985 s y máximo 12,911 s; la décima petición devolvió HTTP 500.
- [Repetición del escenario de criterio](home-nemotron-super-followup-2026-10-22.json):
  el primer turno volvió a devolver 500. No se completó el escenario.
- [Diagnóstico mínimo](home-nemotron-super-availability-2026-10-22.json): una petición
  sin contexto de ARGOS ni esquema respondió HTTP 200 en 0,506 s. Esto confirma
  disponibilidad básica y autenticación; no explica el 500 de las peticiones completas.
- [Diagnóstico con JSON sin esquema](home-nemotron-super-format-2026-10-22.json):
  se cambió solo el formato en el proceso de evaluación. Tras 32,841 s devolvió
  una decisión que el validador rechazó. No se incorporó esta variante al evaluador
  ni al runtime y no se ejecutaron acciones.
- [Escenarios restantes de contexto](home-nemotron-super-context-2026-10-22.json):
  once respuestas aceptadas; la prueba se detuvo en aislamiento de sesión tras
  una petición fallida de 60,094 s. El escenario de estado local quedó sin ejecutar.

La memoria de Helios, las referencias a los cables, la corrección tras interrupción
y el cambio español/inglés funcionan en los turnos observados. Reconoce que no
puede ver el setup y no inventa haberlo reparado. Sin embargo, la broma sobre una
copia en el mismo disco provoca una aclaración sobre rutas para crearla, aunque
no se solicitó esa operación. También introduce ofertas innecesarias y, al explicar
una actualización, menciona un nombre de herramienta incorrecto (`desarrollo.check`).

La latencia de muchas respuestas ronda 1–2 s, pero aparecen picos de 32,418 y
49,967 s sin reintentos, además de los errores. Estos datos no permiten atribuir
el problema exclusivamente al modelo, al esquema o a la carga del servicio.
Se corrigió el mensaje genérico de errores 5xx para no sugerir que prueban una
clave inválida. No se ha completado una pasada entera ni se ha validado la voz.
El candidato no se activó como interlocutor principal; su disponibilidad y su
distinción entre conversación casual y órdenes siguen pendientes de mejorar.

## Auditoría ampliada de conversación y contexto (22 de octubre)

Se añadieron 88 turnos definidos en 28 escenarios a
`scripts/validate_conversation_live.py`: preguntas obvias, excepciones y ficción,
humor, frustración, órdenes citadas/negadas/ambiguas, selección de capacidades,
agentes y paneles, correcciones, cambio de idioma, interrupción, reinicio,
aislado de sesiones y una conversación de veinte turnos. Se mantuvo Nemotron
3.5 Super, sin Codex, audio ni operaciones reales. No se activó como proveedor.

Las tandas conservaron **78 turnos**, de los cuales **65** produjeron decisiones
válidas del modelo y **12** fallaron en el proveedor (tres esperas agotadas,
seis HTTP 500 y tres salidas JSON inválidas). Una orden resuelta por Core fue
bloqueada antes de ejecutar, pero el observador inicial no guardó su decisión;
ese observador ya está corregido. Hubo 77 intentos HTTP conservados en las trazas,
además de un sondeo mínimo y una entrada adicional perdida al fallar el guardado
de la primera versión del informe. No se presentan como una suite completa pasada.

Sobre las 65 decisiones válidas, la mediana fue **2,146 s**, p95 **20,809 s** y
máximo **58,654 s**. El máximo de los intentos, incluidos fallos, fue **60,092 s**;
17 de los 78 turnos superaron cinco segundos. Son revisiones y formatos distintos,
con temperatura 1 y servicio compartido: estos números describen lo observado,
no una mejora causal de rendimiento. Hubo un breve solapamiento entre el final de
la tanda inicial y el comienzo de la primera candidata; las posteriores fueron
secuenciales. No se ha medido tiempo hasta el primer token ni hasta voz audible.

### Cambios conservados

- El contrato distingue preguntas simples, provocaciones juguetonas, dudas
  sinceras, ficción, peticiones de detalle y órdenes reales. Pide dejar de bromear
  cuando el usuario se pone serio, y evitar ofertas o confirmaciones redundantes.
  Incluye dos ejemplos de tono ajenos a los casos del examen; son ilustraciones,
  no respuestas insertadas por código. No hay recorte de palabras en ejecución.
- El contexto compacto conserva descripción, efecto y necesidad de proyecto de
  cada herramienta. Antes eliminaba esa información: el modelo llegó a afirmar
  que borrar no tenía papelera aunque `files.delete` sí usa papelera recuperable.
  Retener la semántica corrige esa carencia de entrada; no garantiza ausencia de
  futuras alucinaciones.
- La auditoría guarda contrato, huellas de código/contexto/petición, decisiones,
  historial público, tokens, tiempos HTTP y comprobaciones por turno. Los criterios
  y presupuestos de palabras no entran en el prompt. Las acciones quedan bloqueadas.
  El formato permite informes largos validando cada registro sin desactivar el
  filtrado de datos. Un modo explícito permite seguir con otro escenario tras un
  fallo, sin repetir el turno, y corta ante autenticación/cuota o tres escenarios
  fallidos consecutivos.

### Qué mejoró y qué no está resuelto

A «Argos, is the sky green?» la línea inicial fue:

> No. The sky appears blue during the day due to Rayleigh scattering of sunlight in the atmosphere.

Con el contrato revisado y el formato compacto experimental se obtuvo:

> No, sir. I assume we're testing definitions.

Esto se acerca al tono solicitado, pero reproduce de cerca un ejemplo de estilo
incluido en el contrato. **No demuestra generalización**: las preguntas nuevas
sobre desenchufar el monitor o renombrar un archivo roto siguieron recibiendo
respuestas literales y explicativas. Otros ensayos dieron simplemente «No».
Se mantuvieron las explicaciones cuando se pedían, y se aceptó la ficción de una
luna de queso, aunque con una coletilla innecesaria sobre su falta de realismo.
La ironía todavía es irregular y algunas respuestas incluyen preguntas no pedidas.

Las pruebas de enrutamiento detectaron confirmación redundante al crear una carpeta,
una aclaración expresada con `kind=answer`, y desarrollo no elegido como se esperaba.
La primera expectativa de panel era defectuosa: el fixture no anunciaba paneles;
se corrigió con una superficie sintética cuyo método de apertura siempre bloquea.
No se cuentan esos resultados iniciales como prueba de fallo de un panel disponible.
Las nuevas ejecuciones de estos casos quedaron interrumpidas por los errores HTTP.

Las **77 comprobaciones del historial enviado** pasaron: el contexto coincide con
los pares públicos anteriores, sin reintroducir turnos fallidos. Esto prueba la
traza disponible, no que el modelo comprenda o recuerde correctamente todo.
Las pruebas silenciosas verifican además reinicio, aislamiento y una conversación
de veinte turnos con ventana de dieciséis pares completos. La validación real
completa de reinicio, memoria larga, alternancia de idiomas y varias rutas sigue
pendiente: no llegó a completarse por los fallos del proveedor.

### Experimentos de formato y disponibilidad

El esquema completo sigue siendo el predeterminado. Se probaron además:

- `--compact-schema`: gramática plana, con validación local posterior contra las
  ramas exactas originales. Nueve respuestas válidas, mediana 1,601 s, máximo
  9,644 s, después tres HTTP 500. No se adopta como arreglo demostrado.
- `--json-object`: JSON sin gramática de decisiones, con la misma validación exacta
  posterior. Dos respuestas válidas y tres decisiones inválidas; detenido. No se
  relajan campos, herramientas, argumentos ni autorizaciones para aceptarlas.

Una petición mínima sin contexto ARGOS ni esquema devolvió HTTP 200/OK en 0,679 s
tras los errores. La clave y el endpoint funcionaron para esa petición; **no permite
atribuir los fallos exclusivamente al esquema, al contexto o a la carga del servicio**.
No hay base para afirmar que el problema de latencia esté solucionado.

El registro completo y sus límites están en
[el índice de la auditoría](conversation-audit-2026-10-22-index.json), con enlaces
por nombre a las siete tandas y al sondeo. La candidata v1 se interrumpió por el
límite inicial del guardado y solo conserva doce entradas; se documenta como parcial.
Las comprobaciones automáticas de estilo son orientativas, no un porcentaje de
semejanza con JARVIS ni una aprobación de calidad conversacional.

Validación de código: suite completa de **266 pruebas** pasada en 6,215 s.
Tras el último ajuste de las comprobaciones del informe, se repitieron las pruebas
específicas de evaluadores y volvieron a pasar. Las pruebas de memoria con respuestas
simuladas validan el transporte y la persistencia del contexto, no la comprensión
lingüística de Nemotron. `git diff --check` pasó.

## Prueba interactiva con Nemotron activada a petición del usuario

Después de la auditoría, el usuario eligió explícitamente conectar Nemotron y
probarlo con voz. Se añadió un proveedor de conversación independiente del
intérprete de tareas: General usa NVIDIA; las tareas usan el Qwen 3.5 9B ya
instalado, y Codex conserva únicamente las escaladas justificadas. La clave
permanece en el archivo privado de credenciales. No se importan scripts de
validación al runtime ni se cambia de proveedor ante fallos.

El adaptador usa el esquema completo, una petición por turno, timeout de red de
20 segundos y rechaza texto truncado, decisiones fuera del catálogo y llamadas
nativas a herramientas. Los errores no bloquean permanentemente el siguiente
turno del usuario. Se conserva el micrófono SteelSeries Arctis Nova 5X, idioma
automático y pulsar Espacio para hablar; manos libres sigue desactivado.

Suite completa: **272 pruebas pasadas** en 6,371 s. Arranque verificado con ventana
ARGOS visible, `voice_ready=true`, `preparing=false` y ningún error de voz. Una
petición textual real en la sesión separada `comprobacion-arranque` devolvió de
NVIDIA «Sí, estoy aquí. ¿En qué puedo ayudarte?». No se reprodujo audio de prueba;
queda al usuario comprobar el micrófono y la salida hablada en la consola abierta.
La activación experimental no invalida los problemas de estabilidad y tono
registrados anteriormente.
