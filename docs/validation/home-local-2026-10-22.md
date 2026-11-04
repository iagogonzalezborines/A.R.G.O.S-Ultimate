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

## Corrección del recorrido de voz y activación de manos libres

La prueba del usuario descubrió un fallo que la auditoría textual no ejercitaba:
Whisper transcribió «ARGOS is sky blue.» y «ARGOS is the sky blue.» sin coma.
El pulsador reenviaba el prefijo íntegro y no enviaba `conversation=true`;
Nemotron respondió sobre la identidad de ARGOS. La entrada manos libres ya
separaba la invocación, pero estaba desactivada. Ahora ambos recorridos comparten
la separación de la invocación inicial, conservan una invocación sola y no
transforman menciones citadas, negadas o internas. El pulsador también identifica
el turno como voz. No se reescribe la pregunta ni se inserta una respuesta fija.

También constaba un saludo transcrito como «¡Halo!». Un saludo breve sin evidencia
léxica clara que contradiga el idioma anterior puede volver a reconocerse en el
otro idioma, aun si la detección acústica inicial fue confiada. Se comparan las
hipótesis, sin traducir ni sustituir texto a mano. Los saludos claros siguen
cambiando de idioma y no añaden esa segunda pasada. Esto se verificó con fixtures;
no se conservaba audio del usuario para repetir su reconocimiento exacto.

Se reinició únicamente el Core identificado, comprobando que no había tareas
activas. El usuario solicitaba conversación sin pulsador: manos libres quedó
activado y persistido, idioma automático, micrófono SteelSeries, `voice_ready=true`,
`barge_in_available=true` y sin errores de eco. La espera indica
`listening_for_argos`; tras invocar se mantiene el diálogo. Escape desactiva la
escucha; «eso es todo» vuelve a esperar la invocación.

Validación: **276 pruebas automáticas pasadas** en 6,286 s. En una sesión separada,
el texto corregido «is the sky blue.» produjo una respuesta sobre el cielo en
inglés en **2,56 s**; «¿Y por qué se ve azul?» produjo una explicación en español
en **4,65 s**. Son tiempos de petición textual al Core, no latencia de voz completa.
No se reprodujo audio de prueba. Se añadió medición de reconocimiento y despacho
al recorrido manos libres, visible en `voice-status`, como en el pulsador.

El último turno manual observado había tardado 1596 ms en reconocimiento y 2503 ms
en despacho; un turno anterior registrado tardó unos 14,6 s entre entrada y
respuesta. La integración y el idioma se corrigen en sus recorridos, pero no se
da por resuelta la variabilidad de latencia de NVIDIA ni la calidad acústica real.

## Brevedad proporcional en el turno de voz

El usuario volvió a preguntar «is the sky blue?» y recibió 26 palabras sobre
Rayleigh y los colores del amanecer/atardecer. El registro confirma una pregunta
correctamente transcrita, pero una respuesta más explicativa de lo pedido. El
último diagnóstico mostró 1511 ms de STT, 3838 ms de despacho y 140 ms hasta el
primer audio de síntesis: aproximadamente 5,5 s antes de empezar a hablar.

Se compararon diez peticiones reales, alternando contrato anterior y una guía
breve de entrega situada inmediatamente antes de la pregunta actual. Ambas
variantes recibieron el mismo historial sintético con una explicación larga
anterior. No se alteraron modelo, temperatura, límites de salida ni validaciones.
La guía se aplica solo a General en voz, conserva el historial literalmente y
pide contestar la pregunta actual sin añadir causas, excepciones u ofertas no
solicitadas; permite detalle y aclaraciones cuando correspondan. No contiene
la pregunta del cielo ni respuestas prefabricadas, y no recorta texto generado.

Resultados en [el informe de comparación](voice-delivery-2026-10-22.json):

- Cielo azul: 16 palabras antes; «Yes.» con la candidata (2,082 / 1,521 s).
- Ocho mayor que tres: 6 palabras antes; «Yes.» con la candidata (1,574 / 1,850 s).
- Hielo frío: fallo por espera agotada en la línea base; candidata de 18 palabras
  con una explicación innecesaria. **La adherencia sigue siendo imperfecta.**
- Explicación explícita: ambas explican; la candidata conserva 60 palabras completas.
- Archivo seguro para borrar sin identificarlo: ambas piden una aclaración.

La candidata tuvo respuestas entre 1,521 y 18,520 s. No se atribuye una mejora de
latencia al cambio ni se presenta como solución al servicio remoto. Se conservó
la guía por su mejora en las dos comprobaciones simples en inglés y por mantener
las explicaciones y aclaraciones necesarias, con el fallo español documentado.

Tras **277 pruebas automáticas pasadas** (6,378 s), se reinició Core sin tareas
activas, conservando las preferencias de voz existentes. La petición final al
Core real, marcada como conversación de voz pero sin reproducción, recibió
**«Yes, it is.» en 4,065 s**, en inglés. Esta medida excluye reconocimiento y
reproducción. La brevedad mejoró en esa prueba; la latencia y la consistencia
no se dan por resueltas.

## Invocación desactivada al usar Espacio

Ante el aviso de que «Argos» no activaba el micrófono, el diagnóstico real mostró
`wake_enabled=false` y `wake_state=off`. El recorrido `voice.toggle` detenía el
listener y persistía `false` cada vez que se usaba Espacio. Esta observación
confirma el modo apagado y el comportamiento del código; no registra qué tecla
lo había desactivado en la sesión del usuario.

Ahora Espacio, si manos libres está activo, abre el diálogo de esa escucha sin
cerrar captura/AEC, cambiar sesión/proyecto ni guardar un cambio de modo. Pulsarlo
de nuevo no cancela un turno en curso. Escape y `--wake-word off` siguen apagando
la escucha explícitamente; con manos libres apagado permanece la captura manual.
Se actualizaron las instrucciones de consola y la documentación.

Validación silenciosa: **278 pruebas pasadas** en 6,489 s. La regresión comprueba
pulsaciones repetidas, persistencia, conservación de turnos en cola y ámbito,
aceptación de una frase tras Espacio, despedida y nueva invocación, apagado con
Escape y posterior captura manual. No usa micrófono, altavoces ni inferencia real.

Core se reinició sin tareas activas y se habilitó manos libres a petición del
usuario. Estado posterior: `wake_enabled=true`, `wake_state=listening_for_argos`,
`dialogue_open=false`, `voice_ready=true`, `barge_in_available=true`, sin errores
de voz/eco, idioma automático y entrada SteelSeries Arctis Nova 5X. La escucha
queda esperando una invocación real; no se da por validado el reconocimiento
acústico del nombre ni se atribuye una mejora de latencia a este cambio.

## Diagnóstico de la invocación sin respuesta

El usuario siguió sin obtener respuesta a «Argos» y «Argos, hello». Esta vez la
escucha estaba encendida, con entrada SteelSeries y AEC activos, sin errores.
Había una transcripción completada (586 ms), sin apertura de diálogo y con
despacho de 0 ms. Los datos existentes no permitían distinguir una transcripción
vacía de una frase sin el nombre reconocido. No se considera resuelto el fallo.

Se añadió `wake_diagnostics` a `voice-status`: contadores en memoria de tramas,
actividad, segmentos, transcripciones vacías, invocaciones no reconocidas y
turnos aceptados, con un estado categórico del último resultado. No expone ni
persiste transcripciones de fondo, audio ni razonamiento. **279 pruebas pasaron**
en 6,386 s, incluida la distinción entre rechazo vacío, rechazo sin invocación y
aceptación, comprobando que el diagnóstico no contiene el texto descartado.

Prueba acústica sintética, sin reproducción ni archivos de audio: Pocket TTS
generó «Argos» y el saludo con nombre en cada idioma; Whisper base reconoció la
invocación en los cuatro casos (0,815–1,243 s de transcripción). No reproduce la
voz, pronunciación, ruido ni recorrido de micrófono del usuario.

Tras reiniciar sin tareas activas, se pidió repetir una frase real. Durante una
medición paralela de 35 s, sin conservar audio, el máximo RMS de las tramas fue
188,5 en la entrada física y 8,5 tras AEC; ninguna alcanzó el umbral actual de
300. El listener recibió tramas, pero no detectó voz durante ese intervalo.
Sin confirmación del usuario de haber hablado durante la medición, estos datos
no demuestran un fallo de ganancia, de AEC ni del umbral. Queda pendiente la
prueba coordinada; no se alteraron el umbral ni el nombre de activación a ciegas.

## Invocación reconocida: espera remota y reproducción retenida

La prueba siguiente registró tres invocaciones aceptadas, ninguna rechazada y
diálogo abierto. El journal muestra «ARGOS.» seguido de un fallo tras 20,143 s,
y dos «hello.» con respuestas «Hello.» tras 2,751 s y 1,142 s. El usuario confirmó
que oyó las dos respuestas muy tarde y un aviso de error en español. La captura
y reproducción sí funcionaron en esa prueba; no era una invocación ignorada.

Se encontraron dos fallos del recorrido manos libres: `process_audio` mantenía
TTS pausado mientras hubiera más entradas pendientes, reteniendo las respuestas
hasta vaciar la cola; `_turn_loop` sustituía cualquier `ArgosError` por un aviso
genérico en español y no limpiaba ese error después de un turno correcto.

Ahora se libera la reproducción de cada turno antes de procesar el siguiente,
respetando la pausa de una interrupción activa. Se conserva el error público
saneado, se localizan los avisos de NVIDIA al idioma del turno y el siguiente
turno correcto limpia el error. El diagnóstico distingue aceptados, completados
y fallidos, y conserva el tiempo de despacho incluso si hay una excepción.

El timeout de red NVIDIA baja a 8 s para voz; texto conserva 20 s. Se mantiene
modelo, contexto, esquema, límite de generación y una única petición, sin
reintentos ni sustitución de proveedor. Esto limita la espera de red antes del
aviso; no acelera el servicio ni garantiza 8 s de latencia total. Podrá rechazar
respuestas que el anterior timeout habría permitido completar más tarde.

Validación: **281 pruebas pasadas** en 6,410 s. La regresión usa síntesis y salida
simuladas: primera petición fallida con una segunda ya en cola, aviso en inglés
antes de la segunda petición, continuación del diálogo y limpieza del error.
No reproduce por altavoces. Una comprobación adicional de AEC con salida nula
aislada no capturó tramas del monitor y es inconcluyente; no se usa como prueba
de entrega de audio. Sus nodos temporales se eliminaron y se conservó la salida
predeterminada SteelSeries.

Se reinició Core sin tareas activas y se verificó manos libres en
`listening_for_argos`, con SteelSeries, idioma automático, voz preparada y sin
errores. Dos llamadas reales al Core, en sesión separada con contexto de voz y
sin reproducción, dieron «I'm here.» en 2,197 s y «Hello. How can I help?» en
1,187 s. Excluyen captura/STT/TTS; no garantizan los siguientes tiempos remotos.

## Nuevo intento sin respuesta: transcripción vacía

Tras el aviso de 15 segundos sin respuesta, `wake_diagnostics` registraba dos
segmentos, ambas transcripciones vacías y cero turnos aceptados. El último STT
tardó 560 ms, sin despacho; no hubo petición a NVIDIA ni generación de voz.
El timeout remoto y la cola anterior no explican este intento.

Una prueba sintética local comparó la misma frase con ganancias 1, 0,1, 0,03 y
0,01, con y sin normalización limitada. Las ocho variantes conservaron una
invocación reconocible; no demuestra que normalizar arregle el micrófono real.
La comparación simultánea de entrada física y AEC durante 50 segundos no detectó
la frase solicitada: ambas devolvieron texto vacío incluso al reconocer la
ventana completa, sin endpointing. Sin confirmación de haber hablado durante
esa ventana, no permite atribuir el fallo a AEC, al nivel ni al detector.

Se preparó una segunda medición limitada a tres minutos para el siguiente
intento del usuario, con reconocimiento por segmento en ambas entradas. Expone
solo niveles, duraciones, aceptación, clase acotada del primer token y datos de
VAD; no guarda audio ni transcripciones libres. Pendiente de correlacionarla
con una frase real confirmada. No se modificaron umbrales o reconocimiento a
partir de una causa no demostrada.

## Pausa tras el nombre: activación local sin petición remota

El usuario confirmó haber oído un timeout en inglés y después «Yes, I can hear
you». La medición simultánea identificó el mismo patrón en entrada directa y
AEC: segmento de 1,32 s con invocación a los 56,9 s de la prueba y un segundo
segmento de 1,54/1,56 s empezando por «hello» a los 58,4 s. Ambos reconocedores
devolvieron texto no vacío; no se guardó la transcripción libre del diagnóstico.
Los procesos temporales cerraron sus capturas al acabar los tres minutos.

El journal de los turnos aceptados confirma dos peticiones distintas: «ARGOS.»
falló tras 8,118 s; «Hello, can you hear me?» recibió «Yes, I can hear you.» en
4,342 s. No fue una respuesta tardía de la misma petición ni un reintento
automático: el nombre aislado estaba consumiendo una petición remota delante
de la pregunta real.

Se cambió el recorrido manos libres: una invocación sola abre el diálogo
localmente y devuelve el control, sin consultar al modelo, crear mensajes ni
sintetizar un saludo. La esfera muestra escucha. La petición posterior, o el
nombre unido a una petición en el mismo segmento, consulta al modelo normalmente.
Se conservan contexto, preguntas explícitas de presencia, seguimiento sin volver
a invocar y despedida. `activation_only` distingue esta activación de un turno
aceptado para procesar. Documentación y contrato describen el nuevo comportamiento.

**282 pruebas pasadas** en 6,458 s, incluyendo dos nombres consecutivos seguidos
de la pregunta: una sola llamada al proveedor, una respuesta y dos mensajes en
el journal, sin tareas ni errores. Se reinició Core sin tareas activas. La
comprobación con el listener y el Core real, en sesión separada sin reproducción,
resolvió el nombre en 0,00043 s sin petición remota, y la pregunta en 5,170 s con
una única petición y respuesta en inglés. Estas medidas empiezan después del
reconocimiento; no representan latencia acústica completa. La espera variable
de NVIDIA permanece y no se consideran resueltas todas las transcripciones vacías
anteriores. Estado final: manos libres preparado, esperando «Argos», SteelSeries,
idioma automático y sin errores de voz/eco.

## Corte audible y retirada del timeout de ocho segundos

El siguiente intento registró «Are you there?» y la respuesta completa del
modelo «Yes, I'm here.» tras 1,700 s. «Hmm, what can you do?» falló tras 8,096 s,
en el límite reducido. El usuario aclaró que el corte afectaba una palabra o el
final audible, no solo que la respuesta fuera breve. No se equipara texto
completo con reproducción completa en los auriculares.

Se retiró el límite de ocho segundos y se restauraron 20 s de timeout de red,
también para voz. El margen menor estaba convirtiendo esperas en errores; no
había demostrado reducir la latencia de las respuestas correctas. Se mantiene
la activación local del nombre, el orden corregido de reproducción, la localización
de errores y una sola petición sin reintentos ni cambio de modelo.

En una prueba sintética local sin reproducción, Pocket TTS generó 1,600 s para
«Yes, I'm here.» y Whisper recuperó la frase entera. Esto valida esa generación,
no reproduce ni certifica el audio del intento del usuario. Para dar margen al
vaciado de la salida se añadieron 200 ms de silencio tras el último byte de voz,
antes de EOF del reproductor. No se corta ni se desvanece el contenido hablado.
La hipótesis de pérdida al cerrar el recorrido requiere validación acústica.

`voice-status` incorpora `last_stream` con estado de entrega, bytes de síntesis,
bytes enviados, silencio añadido, fin del generador y código de salida del
reproductor. Distingue final completo, interrupción y error; no registra audio ni
demuestra que el hardware haya reproducido todo. Las pruebas comprueban que el
receptor silencioso recibe cada byte original seguido de la cola de silencio,
incluidas frases cortas, y que una cancelación no se marca completa.

**282 pruebas pasadas** en 7,045 s. Una petición al Core real con el mismo texto
«Hmm, what can you do?», en sesión separada y sin reproducción, devolvió una
descripción de capacidades en inglés en 2,730 s. No prueba que el timeout mayor
acelere al proveedor ni garantiza la siguiente latencia. Se reinició Core sin
tareas activas para cargar los cambios; la escucha estaba apagada y se conservó
esa preferencia. Pendiente de que el usuario confirme el final audible.


## Retorno explícito a Codex con perfiles por tarea

A petición del usuario, se sustituye NVIDIA/Ollama en esta instalación por
Codex con la sesión ChatGPT existente. El `model/list` real confirmó
`gpt-5.6-luna` con esfuerzo `low` y `gpt-6-astra` con `high`.
General, Computer y Research usan Luna/low; Engineering, Design3D y Printing3D
usan Astra/high. El archivo global de Codex conserva su configuración.
No se emplean claves API de OpenAI ni fallback automático entre proveedores.
El perfil de una tarea incluye modelo/esfuerzo y no cambia silenciosamente al
reanudarla. Las capacidades y aprobaciones siguen siendo responsabilidad de Core.

General consume una inferencia por turno, con historial público acotado; prepara
la conexión sin inferencia y libera el hilo efímero al terminar. Se mantiene el
texto completo generado, sin recortes artificiales. El esquema limita nombres
de capacidades al catálogo y exige argumentos JSON no vacíos. Una prueba inicial
real encontró `arguments_json=""` para un saludo y otra una capacidad inexistente;
se corrigieron el contrato de transporte y las restricciones del esquema antes
de activar el perfil. No se habilitó control de Fusion 360.

La evaluación final incluye doce turnos reales, sin reproducción ni ejecución
de acciones: inglés/español, hechos simples, explicación, corrección Atlas→Orion,
recuerdo posterior en inglés, propuestas de abrir Firefox y el mapa, humor y
límites de Fusion. Los doce se validaron. Tiempos de decisión: 2,203–3,597 s.
Entradas: 7.751–8.172 tokens; salidas: 31–114 tokens (incluidos 0–62 de razonamiento,
solo contadores, nunca contenido privado). Estos datos no cuantifican el ahorro
de cuota respecto a Astra/high: no se hizo una comparación equivalente.

Después de reiniciar Core, tres turnos reales por socket en sesión de validación
separada devolvieron «Yes, I’m here.» (2,631 s), «Yes, usually.» (3,559 s), y una
explicación en español de por qué el cielo es azul (3,284 s). No reprodujeron audio;
las medidas empiezan con texto y excluyen micrófono, transcripción y reproducción.
No prueban que el corte audible previo esté resuelto.

Estado comprobado tras reinicio: `codex_profiles`, modelos/esfuerzos correctos,
voz preparada, escucha `listening_for_argos`, idioma automático, micrófono
SteelSeries Arctis Nova 5X y ningún error. **290 pruebas automatizadas pasadas**
en 7,445 s, incluyendo afinidad, formato, historial, puente de herramientas,
esfuerzo enviado al protocolo y rechazo de modelos no disponibles.

Resultados públicos: [evaluación Codex por perfiles](codex-profiles-2026-10-22.json).
Selección y acceso contrastados con [modelos Codex](https://learn.chatgpt.com/docs/models)
y [App Server](https://learn.chatgpt.com/docs/app-server), además del listado de
modelos de la sesión real. Luna satisface estos casos concretos; no garantiza
calidad o latencia uniforme para todas las peticiones.


## Ajuste de ironía con Luna/low

Tras confirmar el usuario que la conversación funciona mejor, pide más sarcasmo
e ironía. Se ajustan la personalidad compartida y la instrucción final de voz:
las exageraciones y absurdos lúdicos invitan a una observación irónica concreta;
las preguntas sinceras, frustración y peticiones serias reciben respuesta directa.
Se retiran ejemplos de chistes que Luna estaba copiando literalmente. No se añaden
respuestas prefabricadas, otra inferencia, recortes de texto ni cambios de modelo.

Comparación silenciosa con Luna/low: cuatro casos antes y diez después. Antes,
«Is the sky green?» recibió «No, the sky is usually blue.»; después añadió ironía
sobre el cambio atmosférico. La exageración de doce alarmas recibió «That is not
a sleep schedule; it is a heavily segmented negotiation with morning.» El caso
de carpetas definitivas produjo «Naturalmente. Cinco carpetas llamadas “definitivo”:
la duda ha sido cuidadosamente archivada.» Las frases son salidas reales del
modelo, no texto incorporado al contrato.

Al pedir seriedad, el modelo explicó sin bromas; ante pérdida de un archivo dio
orientación sin burlas; mantuvo saludo breve, respuesta aritmética directa y
pidió aclaración ante «hazlo todo automáticamente». No se ejecutaron capacidades
ni se reprodujo audio. Se revisó estilo, no se certificó exactitud factual de
cada respuesta. Una muestra por caso no demuestra consistencia universal.
Tiempos posteriores: 2,310–4,001 s de texto a decisión, mediana 2,985 s.
**290 pruebas automatizadas pasadas** en 7,306 s. Reinicio limpio sin tareas o
conversaciones en ejecución para cargar la instrucción de voz actualizada.

Respuestas y contadores públicos: [comparación de tono](codex-tone-2026-10-22.json).


## Reconocer una prueba conversacional, no solo introducir humor

El usuario precisa que busca el reconocimiento cómplice de la intención, como
«I assume we're testing definitions», y no solo brevedad o metáforas graciosas.
Se ajustan el contrato y la instrucción de voz para distinguir contradicciones
lúdicas de conocimiento elemental, preguntas plausibles, incertidumbre sincera
y ficción. Una corrección mínima puede ir seguida de una observación sobre el
intercambio. No se incorpora la frase del cielo ni su respuesta esperada al prompt,
no hay detección por palabras clave y no se añade otra inferencia.

En una iteración intermedia se detectó que Luna también llamaba “prueba” a una
pregunta normal sobre el cielo azul. Se reforzó la diferencia entre una proposición
plausible y un absurdo: la facilidad de una pregunta no basta para bromear.
En la evaluación final, «Argos, is the sky green?» obtuvo:

> No. A modest test of my observational standards, I see.

«Is the sky blue?» obtuvo «Yes. A pleasantly reliable feature of the daytime
sky.» Las peticiones serias posteriores recibieron explicación sin bromas; la
frustración recibió ayuda y la premisa ficticia fue aceptada como ficción.
Son doce muestras con dos formulaciones del caso del cielo; todas fueron
respuestas estructuradas sin acciones. Persisten algunas correcciones redundantes
y un juego de palabras forzado en español. No se afirma una personalidad perfecta
ni consistencia universal; tampoco se evaluó exactitud factual exhaustivamente.

Tiempos finales: 2,480–6,143 s, sin transcripción ni reproducción. **290 pruebas
pasadas** en 7,437 s. Se reinició el Core sin tareas o conversaciones activas
para cargar la instrucción de voz. Se conserva Luna/low y el resto de perfiles.
[Respuestas públicas y huellas del contrato](codex-intent-tone-2026-10-22.json).

Tras reiniciar, el Core real respondió «No. A straightforward test, I see.»
a la frase exacta en 2,965 s. Al pedir una explicación seria respondió sin ironía
en 3,186 s. Comprobación por texto, en sesión separada y sin reproducción.


## Selección y reproducción de vídeos en Firefox

El usuario confirmó que ARGOS abría una página de resultados, no el vídeo, y
eligió integrar una extensión pequeña en su Firefox normal. Se añadieron
`browser.play`, `media.status` y `media.control`, con catálogo, rol Computer,
política rutinaria y contexto que distingue abrir una página de reproducir.

`browser.play` usa la extensión de `integrations/firefox` y un host Native
Messaging local, con socket privado y una operación acotada a búsquedas de
YouTube. La extensión selecciona por título/artista, verifica ID y tiempo
avanzando sin pausa/silencio/anuncio. Las barreras de autoplay, consentimiento
o login no se eluden ni cuentan como éxito. Los controles MPRIS verifican
instancia y título antes de play/pause; no seleccionan resultados web.

Validación: **303 pruebas Python pasadas** en 7,666 s, incluidas siete de MPRIS
y seis del puente nativo mediante un proceso real, pipes y socket temporal.
**Siete escenarios JavaScript simulados pasados**, ejecutados con el Node
incorporado en Electron (`ELECTRON_RUN_AS_NODE=1 electron42 tests/firefox-extension.cjs`):
selección frente a otro resultado, ausencia de coincidencia, autoplay bloqueado,
anuncio, silencio, tiempo sin avance y cancelación. Ninguna prueba reprodujo audio.
Después de traducir los avisos nuevos, las 16 pruebas de idioma también pasaron.

Una inferencia real Luna/low ante «Play AC/DC Thunderstruck through Firefox»
seleccionó `browser.play`, query «Thunderstruck AC/DC»; solo se validó la decisión,
no se despachó. `browser-setup` registró el host por usuario y se reinició Core
sin trabajo activo. Se entregó también `integrations/firefox/argos-firefox.zip`.

**Pendiente de comprobación en Firefox real:** cargar la extensión temporal en
about:debugging, confirmar conexión y probar reproducción por petición del usuario.
Al primer seguimiento el usuario no encontraba la extensión; se abrió de nuevo
la página y se explicó cómo seleccionar el ZIP con Ctrl+L. No se afirma que esté
instalada o reproduciendo. La extensión temporal desaparece al reiniciar Firefox;
no se ha firmado ni publicado. Los selectores de YouTube necesitan validación
contra la página real y pueden requerir adaptación si cambia su estructura.

Fuentes: [Firefox y controles MPRIS](https://support.mozilla.org/en-US/kb/control-audio-or-video-playback-your-keyboard),
[Native Messaging](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/Native_messaging),
[carga temporal](https://extensionworkshop.com/documentation/develop/temporary-installation-in-firefox/).

El usuario cargó el ZIP desde Descargas y confirmó que la extensión aparece.
Se verificó que `firefox.sock` existe y acepta conexión; no se envió ninguna
orden de reproducción. Core sigue preparado, escuchando «Argos», sin errores.
La conexión nativa está confirmada; selección y reproducción sobre YouTube real
siguen pendientes de una petición de voz del usuario.

## Aviso de autoplay en inglés y final audible de «here»

El usuario confirmó que Firefox abrió el vídeo, pero notificó el bloqueo de
autoplay en español. La tarea conservaba `task.language=en`; las traducciones
estaban en el checkout, pero se añadieron después del arranque del Core activo.
Se reinició Core para cargarlas. Una regresión ejecuta `browser.play` simulado,
cambia la conversación a español mientras espera y provoca el bloqueo: la tarea
falla y su aviso de voz conserva el inglés. El permiso de autoplay de Firefox
continúa pendiente; no se ha cambiado ni se afirma reproducción confirmada.

El texto de la respuesta corta era completo: «Yes, I’m here.» El usuario precisó
que faltaba el final de «here». No había interrupciones de voz registradas.
Se comprobó la salida real PipeWire contra un sumidero nulo privado, directamente
y a través de otro módulo AEC conectado únicamente al sumidero nulo. Las señales
sintéticas de 0,3 y 1,6 s conservaron su duración con error menor de 0,1 ms. El
monitor se capturó con latencia de 20 ms y se dejó drenar un segundo; la captura
inicial con fragmentos predeterminados se descartó por truncar el propio registro.
No hubo reproducción por altavoces ni cambios del dispositivo predeterminado.

La síntesis local mostró variaciones con la contracción tipográfica `I’m`:
en tres semillas controladas, Whisper retranscribió palabras adicionales o
distintas. Con `I'm` recuperó la frase exacta en dos de tres; la tercera todavía
añadió una palabra. Es una comprobación automática orientativa, no una evaluación
acústica ni prueba de la causa exacta del intento del usuario. Se normalizan
apóstrofos tipográficos exclusivamente antes de sintetizar, preservando palabras,
acentos, idioma e historial público. No se cambió el modelo, el número de frames
tras EOS, ni se recorta o desvanece el audio. Añadir frames de generación no dio
una mejora consistente, por lo que se descartó ese ajuste.

**305 pruebas Python pasadas** en 7,875 s. Se reinició sin tareas ni conversaciones
en curso. El corte acústico queda pendiente de comprobar en los SteelSeries;
la normalización mejora muestras concretas y no demuestra que esté resuelto.

## Diferenciar permiso de Firefox, autoplay de YouTube y carga lenta

El usuario tenía activado el interruptor de reproducción automática de YouTube,
que controla el siguiente vídeo y es independiente del permiso del navegador.
Al revisar la extensión se encontró también un diagnóstico incorrecto: cuatro
segundos en pausa producían `autoplay_blocked` sin comprobar el rechazo de
`video.play()`. Por ello el aviso anterior no demostraba un bloqueo de permisos.

La versión 0.1.1 solo devuelve ese estado ante `NotAllowedError`. La observación
de `play()` espera como máximo 300 ms por intento, incluso si la promesa permanece
pendiente; otros errores y la carga lenta no se etiquetan como bloqueo de permisos.
Se mantiene la comprobación de avance, identidad, volumen, pausa y anuncios.

Validación: **15 escenarios JavaScript simulados** y **305 pruebas Python**
pasados, sin reproducir audio. Se cubren reproducción tras más de cuatro segundos
de carga, pausa persistente, rechazo de permisos, otros errores y promesa pendiente.
ZIP actualizado tanto en el repositorio como en `~/Descargas/argos-firefox.zip`.
**Pendiente:** volver a cargar el ZIP 0.1.1 en Firefox y comprobar el caso real.
No se ha cambiado ningún permiso del navegador ni se afirma reproducción real.

Referencias: [permiso por sitio de Firefox](https://support.mozilla.org/en-US/kb/block-autoplay),
[interruptor de YouTube](https://support.google.com/youtube/answer/6327615?hl=es),
[rechazos de play()](https://developer.mozilla.org/en-US/docs/Web/API/HTMLMediaElement/play).

## Auditoría de capacidades — 2026-10-27

Auditoría del checkout local, no de una versión publicada. Se revisaron catálogo,
contratos, Core, política, herramientas Linux, inventario, voz, desarrollo,
navegador y pruebas. No se cambió el runtime ni se ejecutaron acciones sobre
aplicaciones, proyectos reales o impresoras. Los escenarios de escritura y
ejecución pertenecen a las pruebas con directorios temporales. No se inició
Core, micrófono, reproducción ni inferencia remota para esta auditoría.

### Estado observado

- ARGOS 0.3.0; **Core apagado**. `voice-status` y `system-status` no pudieron
  conectarse. `doctor` pudo inspeccionar el equipo sin arrancarlo.
- Seis roles: General, Engineering, Computer, Research, Design3D y Printing3D.
  Son contratos y catálogos especializados; no seis modelos independientes
  permanentemente trabajando. Core dispone de dos puestos de ejecución y cola
  de 64 tareas, con exclusión por proyecto o agente cuando no hay proyecto.
- **35 capacidades registradas**. Este número no incluye las órdenes de control
  de Core, como mapa, monitor, preferencias de voz y revisión de aprobaciones.
- Configuración: Codex Luna/low para conversación y trabajo rutinario;
  Astra/high para tareas complejas. NVIDIA no es el proveedor seleccionado.
  No se revalidaron autenticación, acceso a modelos ni latencia conversacional.
- Voz instalada; configuración automática español/inglés, escucha habilitada y
  entrada SteelSeries Arctis Nova 5X. Al estar Core apagado no está escuchando.
- Puente Firefox conectado por socket. No se solicitó reproducción; la conexión
  por sí sola no demuestra la versión cargada ni el funcionamiento de YouTube.
- 31 aplicaciones descubiertas y cuatro ventanas observadas durante el sondeo.
  Bambu Studio no aparece en el catálogo de aplicaciones de ARGOS.
- Un proyecto registrado. Historial de tareas: cinco COMPLETED y cinco FAILED;
  no representa una tasa de fiabilidad: incluye pruebas anteriores y versiones
  distintas, sin muestreo controlado.

### Qué está implementado y hasta dónde llega

| Área | Capacidad actual | Límite relevante |
| --- | --- | --- |
| Conversación | Contexto por sesión/proyecto, español/inglés, contrato de concisión e ironía contextual | Hasta 16 intercambios completos y 24.000 caracteres; no memoria ilimitada ni garantía de estilo o latencia |
| Voz | Whisper local, Pocket TTS, pulsador, invocación «Argos», diálogo continuo e interrupción con AEC | Cortes y calidad acústica no certificados; no identifica al hablante |
| Tareas | Delegación por rol, cola, cancelación, respuestas a preguntas, aprobaciones y recuperación sin repetir efectos | Proveedor y herramientas disponibles condicionan cada tarea; una propuesta no prueba ejecución |
| Monitor | Mapa de agentes y monitor de tareas/conversaciones en terminales separadas | Solo actividad gestionada por ARGOS; no todas las sesiones externas del IDE |
| Archivos | Listar, leer por tramos, escribir/parchear, crear carpetas, copiar, mover y enviar a papelera | Modificaciones requieren aprobación; rutas, enlaces, secretos y versiones tienen restricciones |
| Programación | Inspección Git, edición, comandos revisados y pruebas; flujo de candidata aislada con plan y revisión | No equivale a manejar visualmente VS Code; el flujo de candidata no aplica cambios al origen |
| PC | Inventario, catálogo de aplicaciones, apertura de apps/documentos/URLs, listado de ventanas | Enfoque/cierre incompatibles con el dispatcher actual; no hay control general de ratón/teclado ni visión de pantalla |
| Web | Bing RSS, lectura paginada de HTML/texto público y síntesis con fuentes | Sin JavaScript, PDF, login ni navegación interactiva general |
| Multimedia | Selección de vídeo de YouTube con extensión; observación y play/pause mediante MPRIS | Extensión temporal, coincidencia textual y permisos de autoplay; sonido físico no verificado |
| Diseño 3D | Inspección de STL: triángulos y dimensiones geométricas | No modelado paramétrico, Fusion/Blender, reparación de malla ni certificación de imprimibilidad |
| Impresión 3D | Inspección de texto G-code, movimientos y temperaturas declaradas | No conexión a impresora, control de Bambu Studio, laminado ni lanzamiento de trabajos |
| Autoactualización | Preparar una candidata del propio ARGOS, modificarla y revisar pruebas tras aprobación | Sin aplicación, activación ni rollback automático de la candidata |

### Hallazgos reproducidos

1. **Prioridad alta — filtro incompleto de credenciales.**
   `src/argos/security.py:9` reconoce ciertos patrones pero no el prefijo
   `nvapi-`. Se probó exclusivamente una cadena ficticia de ese prefijo y 64
   letras iguales, en un Core temporal con proveedor falso. El texto llegó al
   proveedor falso y quedó en su historial temporal. No se usaron, buscaron ni
   enviaron credenciales reales. Es una brecha respecto a la intención de filtrar
   credenciales antes del proveedor y de SQLite; no se afirma que un filtro por
   patrones pueda detectar todos los secretos posibles.

2. **Prioridad alta para manejo del PC — enfoque y cierre de ventanas.**
   `src/argos/linux_tools.py:138` y `:153` invocan `focuswindow`/`closewindow` con
   la interfaz antigua. El Hyprland instalado utiliza Lua; al compilar las
   expresiones que produciría esa interfaz con `load()` se obtuvo error de
   sintaxis en ambos casos, sin ejecutar acciones de ventana. El adaptador de
   paneles ya usa `hl.dsp.*`, pero el general no. Además, `host.py:204` publica
   disponibilidad positiva solo porque el sondeo de monitores respondió.

3. **Limitación de catálogo — Bambu Studio no está integrado.**
   `discover_apps()` inspecciona archivos `.desktop` de dos directorios, no los
   AppImage de `~/Applications` ni las instalaciones de Windows. Bambu no está
   en los 31 resultados actuales. La apertura del AppImage y el centrado del
   modal realizados por el asistente de esta conversación no fueron acciones
   de ARGOS y no demuestran que ARGOS tenga esas herramientas.

4. **Limitaciones ya conocidas que siguen abiertas.**
   La extensión sin firma desaparece al reiniciar Firefox. El corte audible al
   final de frases cortas no tiene una validación acústica final. Los roles 3D e
   impresión y la preparación de autoactualizaciones no deben anunciarse como
   control CAD, impresión física o actualización instalada.

### Comprobaciones y alcance de la evidencia

- **305 pruebas Python pasadas en 7,668 s**, con
  `PYTHONPATH=src python -m unittest discover -s tests -v`.
- **15 escenarios JavaScript simulados pasados**, con
  `ELECTRON_RUN_AS_NODE=1 electron42 tests/firefox-extension.cjs`.
- La capacidad real `web.search` devolvió cinco resultados para una consulta
  pública sobre documentación de Bambu Studio; no se evaluó su relevancia exhaustivamente.
- La capacidad real `web.read` leyó 3.341 caracteres del README público de Bambu
  en raw.githubusercontent.com. example.com devolvió `page_unavailable`; no se
  atribuye la causa a un defecto concreto ni se generaliza a toda la web.
- Sondeos reales de catálogo, ventanas, dispositivos y socket Firefox sin efectos.
- Reproducción sintética del filtro y comprobación sintáctica del dispatcher.
- Pasar las pruebas no garantiza compatibilidad con cada app, servicio o versión
  del escritorio. La regresión de ventanas no fue detectada por la suite actual.
- Sin medición nueva de conversación real, latencia acústica, reproducción de
  YouTube, edición sobre proyectos del usuario ni ejecución física de impresoras.

Prioridad propuesta: corregir filtro de credenciales y adaptador/disponibilidad
de ventanas; registrar aplicaciones portátiles; cerrar validaciones de voz y
multimedia; después integrar capacidades concretas de Bambu/CAD. Esta auditoría
documenta los hallazgos; no los da por corregidos.

## Prioridad a la intervención nueva — 2026-10-27

El usuario informó de respuestas a frases anteriores mientras intentaba seguir
hablando. El estado real mostraba AEC disponible, nueve turnos completados y una
interrupción, sin fallo del dispositivo. El código solo interrumpía al detectar
salida de voz activa; al finalizar una inferencia liberaba su respuesta incluso
con entrada posterior pendiente. Una respuesta aún generándose no se invalidaba.

La captura ahora marca cada intervención tras 160 ms de actividad y mantiene
la pausa durante esa intervención. Core compara su generación antes de encolar
voz: una respuesta superada conserva resultado/historial/evidencia, pero no se
pronuncia. Un plan superado tampoco se marca oído ni habilita su aprobación.
Los errores antiguos no se locutan sobre las entradas posteriores. Los fragmentos
acumulados se transcriben juntos y en orden cuando el usuario termina el segmento.
Se conserva la cola acotada; en desbordamiento se descarta audio pendiente antiguo
en lugar de la última corrección, con contador y diagnóstico de pérdida.

`voice-status` incorpora `pending_voice_turns`, `user_speaking` y contadores
`suppressed_replies`, `merged_segments`, `discarded_segments`, sin texto ni audio.
Las tareas de fondo no se cancelan y los cambios no sustituyen el proveedor,
su contrato de personalidad ni el contenido de sus respuestas.

**313 pruebas Python pasadas en 7,716 s**, incluidas ocho regresiones nuevas:
actividad durante inferencia sin salida activa, pausa al terminar una inferencia
anterior, agrupación ordenada con espera de fin de intervención, error vigente,
desbordamiento que conserva la corrección reciente, supresión de respuesta tardía,
plan no oído sin aprobación y recorrido de reconocimiento/Core/salida silenciosa
en el que solo se reproduce la respuesta nueva. Se actualizaron las pruebas que
antes exigían pronunciar un error antiguo antes de atender la siguiente entrada.
No hubo reproducción por altavoces ni llamadas reales al proveedor en las pruebas.
La eficacia con voz y ruido reales sigue requiriendo la comprobación del usuario.

## 2026-10-27 — Apagado real de escucha y pestañas de medios sin tomar foco

Al revisar la incidencia, Core mostraba `dialogue_open=true`,
`wake_state=conversation`: «stop listening» no tenía control local y podía
recibir una confirmación del modelo sin apagar captura. Ahora esa orden y sus
equivalentes españoles ejecutan `voice.stop`, invalidan la generación anterior,
vacían las colas y confirman una vez en el idioma correspondiente. El controlador
vive fuera del consumidor que cancela, tanto en captura manual como manos libres.
`voice.quiet` evita locutar avisos posteriores; los resultados siguen en el
monitor. Espacio o activar manos libres levanta ese silencio. No cambia modelos.

Las dos operaciones de navegador más recientes eran tareas distintas: una
petición de Thunderstruck a las 10:17:29 y una aclaración de artista a las
10:17:39. Cada una ejecutó una vez `browser.play`; no había dos aperturas dentro
de la misma tarea. La extensión 0.1.2 abre con `active: false` y reutiliza su propia
pestaña en siguientes órdenes mientras conserve la URL dejada por ARGOS. Si el
usuario navega o la cierra, crea otra. No activa pestañas ni enfoca ventanas.
No cambia la comprobación de reproducción ni los permisos de autoplay.

Validación: **316 pruebas Python pasadas en 8,138 s** y **18 escenarios JavaScript**
con navegador simulado. Se cubren apagado desde ambos consumidores sin bloqueo,
idioma del acuse, silencio de avisos posteriores, reapertura manual, órdenes
negadas/citadas y reutilización de pestaña sin foco, incluida navegación o cierre
por el usuario. JavaScript se ejecutó con Node 22.15.0 extraído temporalmente,
verificando el SHA-256 publicado por nodejs.org; no se instaló en el sistema.
Las pruebas no activaron altavoces ni consultaron proveedores.

Core se reinició sin tareas RUNNING/QUEUED. Comprobación IPC real por texto:
`stop listening` devuelve `listening_stopped`, `route=local`, `language=en` y
`Microphone off.`. Preferencias persistidas: `voice.wake_enabled=false`,
`voice.quiet=true`. Estado final: voz preparada, escucha off, diálogo cerrado,
cero turnos pendientes y sin error. Se dejó apagado respetando la orden del usuario.

El ZIP 0.1.2 se preparó en `integrations/firefox/argos-firefox.zip` y
`~/Descargas/argos-firefox.zip`. Se pidió recargarlo manualmente en Firefox.
Pendiente comprobar con el usuario la versión cargada y la reproducción real en
segundo plano; las pruebas simuladas no certifican la política de Firefox ni
el sonido físico.

## 2026-10-27 — Personalidad adaptativa y separación entre voz e informe

La inspección confirmó que no existe un Persona/Response Composer independiente:
`ARGOS.md` es común a General y especialistas, Core compone los resultados
deterministas y Engineering ya dispone de campos `speech`/`detail`. Se extendió
ese recorrido, sin otro modelo, dependencia ni capa de reescritura.

El contrato v2 ordena verdad/autorización → instrucciones explícitas → intención,
correcciones y contexto → canal/profundidad → personalidad. Incluye las once
tendencias solicitadas como intensidades, no cuotas; ejemplos ES/EN ilustrativos;
ironía situacional, desacuerdo útil, lenguaje actual y retirada del humor ante
urgencia, frustración o fallos. «Solo los nombres» tiene prioridad sobre
honoríficos, explicaciones y humor. No se recorta ninguna respuesta generada.
Se acortó el recordatorio por turno para evitar repetir toda la personalidad.

La nueva vista `monitor capabilities` muestra el catálogo agrupado con sus
estados reales, descripción, efecto y requisitos, desplazamiento y selección
copiable desde kitty. Las órdenes conocidas de inventario por voz solicitan esa
ventana directamente. Core dice que la ha solicitado; no afirma que haya
recibido contenido visual. Si falla, explica el fallo y conserva el catálogo.
`stop talking` detiene voz sin otra locución; `that's all, ARGOS` vuelve a espera
sin apagar la invocación. Se preserva el apagado real con `stop listening`.

**322 pruebas Python pasadas en 7,736 s.** Las seis regresiones nuevas cubren
inventario sin inferencia y con idempotencia, fallo de presentación sin éxito
inventado, renderizado completo/saneado, silencio sin cancelar tareas, despedida
con nombre final y conservación del informe técnico sin leerlo por TTS.

Evaluación real: [respuestas públicas, latencias y tokens](adaptive-persona-2026-10-27.json),
obtenida mediante `scripts/validate_adaptive_persona_live.py`. Perfiles sin cambios:
Luna/low para General y Astra/high para Engineering. **36 turnos finales**:
29 de inferencia general, tres controles locales y cuatro turnos continuados
Engineering; sin errores ni una llamada extra de Persona. Se emplearon sesiones
sintéticas y una lectura de archivo en memoria; sin escritorio, altavoces ni
archivos del usuario. El primer intento del arnés de Engineering esperaba `path`
en lugar del argumento real `file`; se corrigió el arnés antes de su evaluación
final. Esos intentos incompletos no acreditan un fallo del modelo ni una validación.

Ejemplos reales, sin sustituirlos por respuestas prefijadas:

| Situación | Respuesta observada |
| --- | --- |
| Premisa juguetona: cielo verde | “No. The sky is usually blue; I suspect this is an inspection of my judgment.” |
| Copia «indestructible» en el mismo disco | «No, señor. Si falla ese disco, desaparecen ambas copias; la indestructibilidad aún está en pruebas.» |
| Comprobación sincera sobre cobre | “Yes, copper is a metal.” |
| Corrección de nombre/presupuesto, conservar color | «Nereo, 25 euros, gris.» |
| Solo los nombres | «Git / Copias de seguridad / Sincronización», sin introducción |
| Engineering tras cambiar al inglés | “I verified the source through one file read, not runtime behavior. The diagnosis is static; reproduction, proposed fixes, and integration remain untested, and I made no changes.” |

En la secuencia de longitud, la comparación inicial tuvo 55 palabras, «más
corto» 18, «solo los nombres» cinco y la explicación solicitada 103. La
interrupción posterior produjo una frase inglesa de siete palabras. Engineering
conservó informes de 124, 163, 1.072 y 639 palabras, con resúmenes hablados de
22, 27, 24 y 27 palabras. El informe más extenso tardó 76,117 s con Astra/high;
es trabajo de especialista, no latencia de conversación rutinaria.

En nueve turnos comparables, mediana antes/después: **2,358 → 2,646 s**;
tokens de entrada medianos: **8.600 → 8.514**. No se demuestra una mejora de
velocidad: son muestras pequeñas condicionadas por caché/proveedor. Se conserva
una llamada por turno generativo y cero en las acciones conocidas. No se mide
aquí captura, STT, síntesis ni reproducción física.

Límites: el tono sigue siendo probabilístico y puede reutilizar un ejemplo del
contrato; los ejemplos nuevos también produjeron variantes propias. Cuatro
turnos continuados no garantizan sesiones de trabajo arbitrariamente largas.
El historial sigue acotado; no se añadió memoria ilimitada ni reconocimiento
emocional. General no dispone de un visor de informes arbitrarios: las superficies
conectadas son inventario, agentes y monitor de tareas/conversaciones. La entrega
visual y acústica real requiere la prueba del usuario.

Activación local: Core reiniciado tras comprobar cero tareas RUNNING/QUEUED.
Estado observado después: `voice_ready=true`, `state=idle`, `wake_state=off`,
`dialogue_open=false`, sin errores. Se mantuvo el micrófono apagado y los perfiles
de modelos existentes; no se publicaron cambios ni se activaron candidatas de
otras tareas.

## 2026-10-27 — Registro contextual de proyectos existentes

Problema reproducido en la superficie disponible: General recibía nombres de
proyectos y el home, sin las raíces registradas ni una base observada; además,
`projects.add` existía por CLI/IPC pero no como capacidad del agente. El catálogo
solo ofrecía crear una carpeta nueva mediante `projects.create`.

Se añade `filesystem.project_locations`: comprueba directorios habituales del
home y padres de proyectos registrados sin recorrer ni leer sus archivos. Una
única candidata se publica como base; varias requieren contexto o aclaración.
En este equipo el resultado comprobado es `/home/tyrant/Proyectos`, tanto por
convención como por el padre del proyecto ARGOS registrado. Los especialistas
con proyecto seleccionado conservan aislamiento respecto a otros registros.

`projects.register(name,path)` pertenece a Computer y también puede usarla
Engineering. Valida una carpeta existente, rechaza enlaces/rutas protegidas y
solo modifica el registro. Core guarda evidencia `project_registered` y vincula
esa tarea, sin cambiar el proyecto global ni conceder futuras escrituras.
Repetir el mismo nombre/carpeta conserva el ID; conflictos y carpetas ausentes
fallan sin crear nada. CLI y agentes comparten validación. Crear carpetas nuevas
sigue requiriendo aprobación. El resultado factual admite español e inglés.

Los contratos indican usar la base observada, copiar las rutas literalmente,
conservar nombres del contexto y registrar directamente cuando nombre/carpeta
están resueltos. Solo delegan a Computer cuando hace falta investigar; una
respuesta de delegación no puede mezclar argumentos de una capacidad.

Validación:

- 332 tests locales completos pasan en 7,768 s. Diez pruebas nuevas cubren
  resolución de bases, ambigüedad, falta de convenciones, idempotencia, conflictos,
  conservación de archivos, rutas rechazadas, idioma, lectura relativa tras
  registro y aprobación de creación/escritura. Sin altavoces ni cambios en
  proyectos reales.
- Las primeras pruebas reales con Luna/low detectaron respuestas que mezclaban
  delegación y herramienta. Tras ajustar el contrato desapareció esa mezcla;
  una pasada intermedia alteró dos veces un componente de una ruta temporal.
  Se añadió la regla de copiar literalmente. Se conservan ambas pasadas en
  `project-registration-initial-2026-10-27.json` y
  `project-registration-intermediate-2026-10-27.json`; no son resultados finales
  aprobados. Hubo además fallos de proveedor: en la pasada intermedia se observó
  código HTTP 429 (`responseTooManyFailedAttempts`), no un fallo de filesystem.
- La comprobación final, `project-registration-2026-10-27.json`, usa General real
  y rutas/historial sintéticos: 4/4 casos pasan (nombre/base explícitos, referencia
  al historial, falta de nombre y descubrimiento). Resolución directa a
  `/home/argos/Proyectos/Faro` sin pedir otra ruta. Una llamada por decisión,
  2,285–3,334 s. No ejecuta acciones, no mide STT/TTS ni garantiza comportamiento
  perfecto del modelo. Español, ubicación ambigua y ruta explícita alternativa
  también se ejercitaron en la pasada intermedia; no se certifica esa pasada
  completa por sus errores indicados.
- Harness repetible y opt-in: `python scripts/validate_project_registration_live.py
  --run --report /tmp/argos-project-registration.json`. Las pruebas locales
  verifican la ejecución y persistencia reales sobre carpetas temporales.

Antes de activar se verificó que no había tareas RUNNING/QUEUED. La preferencia
actual era micrófono apagado (`voice.wake_enabled=false`, `voice.quiet=true`);
se conserva al reiniciar. Se mantienen Luna/low y Astra/high.

Activación comprobada: Core reiniciado y consola abierta; `voice_ready=true`,
`wake_enabled=false`, dispositivo SteelSeries y ningún error de voz. El inventario
IPC del proceso nuevo anuncia `projects.register` de Computer, efecto `routine`,
con comprobación de la ruta pendiente de cada operación.

## 2026-10-27 — Seguimiento: carpetas dictadas y contexto perdido al delegar

El registro real permitió reproducir lo que las pruebas anteriores no cubrían:
la voz produjo «Sum and CO2»/«Some score and score CO2» para `some-and-co2`.
General intentó registrar la transcripción literal; después `files.list` observó
la carpeta correcta, pero `task_context` solo transmitía estado/verificación, no
los nombres. Una delegación posterior llevaba únicamente la corrección aislada
como objetivo, sin la petición anterior de registrar el proyecto.

Corrección: inventario superficial y acotado de carpetas bajo las bases conocidas,
incluidas no registradas; listados recientes con ámbito de sesión/proyecto en
contexto General; instantánea pública del diálogo al delegar y entrega al
especialista como `conversation_handoff`. Los contratos resuelven nombres
hablados frente a entradas observadas, conservan la ruta exacta, investigan antes
de repetir una ruta fallida y preguntan cuando quedan coincidencias ambiguas.
No hay coincidencia difusa que ejecute operaciones por sí sola ni una llamada
adicional de clasificación. Las barreras de ruta y aprobación siguen en Core.

- 336 tests pasan en 7,851 s. Cuatro regresiones nuevas cubren carpetas sin
  registrar, exclusión de rutas privadas/enlaces, límites y fallos de observación,
  listados visibles en contexto y aislamiento de sesión/proyecto, y entrega
  congelada de historia/listado al especialista.
- `scripts/validate_folder_context_live.py --run --report /tmp/folder-context.json`
  ejercita proveedores reales y capacidades reales sobre carpetas temporales,
  sin audio ni operaciones en proyectos del usuario.
- Resultado guardado en `folder-context-2026-10-27.json`: tres casos pasan.
  «Sum and CO2» registra realmente `some-and-co2` (3,408 s, una llamada);
  «What folders can you see there…» devuelve los tres nombres observados
  (3,125 s, una llamada); el especialista interpreta la corrección «Some score
  and score CO2» con el contexto transferido y registra la carpeta (5,155 s,
  una llamada del especialista; en este caso el enrutamiento General es
  deliberadamente simulado para forzar y comprobar la transferencia).
- No es una prueba acústica de Whisper ni una garantía de toda transcripción.
  La prueba anterior, limitada a decisiones con nombres exactos, no bastaba
  para afirmar que el manejo hablado de carpetas estuviese resuelto.

La escucha estaba desactivada (`wake_enabled=false`, cero frames). A petición
actual del usuario se activó con `voice-config --wake-word on`; se comprobó
`listening_for_argos`, captura continua, SteelSeries y ningún error. La preferencia
se guarda para reinicios. Se mantiene la orden explícita de apagar la escucha.

Tras reiniciar: voz preparada, `wake_enabled=true`, `listening_for_argos`,
1.107 frames capturados y cero errores; micrófono SteelSeries seleccionado.
Todavía no se había recibido una intervención del usuario en esa nueva instancia.

## 2026-11-03 — Primer flujo persistente de proyecto y candidata por módulo

Se añade memoria estructurada de proyecto y selección de sesión, manteniendo
separada la identidad de las tareas en curso:

- Migración aditiva SQLite v3: `project_profiles`, `project_aliases` y
  `session_projects`. Conserva proyectos, tareas e historial previos.
- Capacidades `projects.inspect`, `projects.context`, `projects.select` y
  `projects.alias`, disponibles para Computer/Engineering. Inspección documental
  con fecha/hash, extracto público del propósito y un escaneo acotado de metadatos
  para presupuesto/módulos. No certifica código, pruebas ni funcionamiento.
- Alias confirmados únicos y selección persistente por sesión. Las peticiones
  sin proyecto explícito usan esa selección; un override puntual no la cambia.
  Las tareas conservan su proyecto cuando la conversación cambia de proyecto.
- CLI `select-project PROYECTO`, `select-project --clear`, `project-context` y
  `develop --scope apps/backend-api`. La selección/registro no autoriza escrituras.
- Los candidatos por módulo mantienen el ID del proyecto registrado y copian
  únicamente el módulo relativo validado. Se rechazan padres, rutas absolutas y
  enlaces. El alcance se conserva incluso al esperar la selección de proyecto.

Hallazgo en el piloto real: una estimación inicial por metadatos del conjunto de
archivos incluidos por la política sumó 4.104 archivos/621.986.385 bytes. Vídeos y
otros recursos de fuente hacen que el proyecto completo supere 128 MiB. No se
eliminaron esos recursos para forzar una candidata. La ficha acotada detecta la
superación y ofrece los módulos observados: `apps/backend-api` (Gradle),
`apps/emission-factors-importer` (Gradle) y `apps/frontend-web` (package.json).
El backend, comprobado por metadatos por separado, tiene 1.548 archivos/27.527.074
bytes bajo la política actual; eso no garantiza disponibilidad de sus dependencias
ni que pueda ejecutar toda su suite en la sandbox sin preparación adicional.

Validación final: **349 tests pasan en 7,934 s**. Trece regresiones nuevas cubren
persistencia/fecha/hash de perfiles, alias y conflictos, selección de sesión,
reinicio sin replay, overrides puntuales, cambio durante una tarea activa,
exclusión de credenciales y aislamiento de proyecto, migración v2→v3, contexto
serializable de candidatas, tamaño/módulos y ámbitos de desarrollo válidos,
rechazados o pendientes de selección.

Arnés opt-in `scripts/validate_project_workflow_live.py --run --report RUTA` con
los perfiles reales Luna/low y Astra/high seleccionados en la instalación. Usa
proyectos temporales y herramientas reales, aprobación exacta exclusivamente del
plan de esa fixture y comprobaciones reales en bubblewrap. No usa micrófono,
altavoces, escritorio ni escrituras en proyectos reales. Resultados:

1. `project-workflow-2026-11-03.json`: encuentra por nombre hablado, registra,
   selecciona e inspecciona (12,515 s); guarda alias confirmado (2,316 s); cierra
   Core/SQLite y recupera selección y propósito (3,543 s); prepara un plan aislado
   y se detiene en WAITING_APPROVAL (21,389 s). Tras aprobar solo la fixture,
   modifica dos archivos y pasa cuatro pruebas reales. Un cambio de selección
   simultáneo no reasigna la tarea. Fuente intacta, `activated=false`.
2. `project-workflow-scoped-2026-11-03.json`: repite el recorrido con
   `--scope apps/backend-api`; registro/inspección 13,875 s, alias 2,256 s,
   recuperación 3,066 s y plan 21,235 s. La candidata nace del módulo, mantiene el
   ID original y pasa las cuatro pruebas. Fuente intacta, `activated=false`.
3. Parches reviewables guardados junto a ambos informes (`.patch`). La mejora de
   fixture normaliza espacios/mayúsculas y conserva la prueba previa más tres
   regresiones. Los informes contienen resultados públicos y evidencia de las
   comprobaciones; los directorios temporales de las fixtures se eliminan.

La primera pasada (`project-workflow-initial-2026-11-03.json`) detectó un error de
serialización del ejecutor interno de desarrollo al entrar en Engineering. Se
corrigió el registro público y se añadió una regresión; esa pasada no es un éxito.
Los tiempos anteriores incluyen inferencia y herramientas de cada etapa, pero
no STT/TTS ni latencia hasta el primer sonido. Falta aceptación acústica del usuario.

Activación real autorizada para el piloto: se guardaron un checkpoint local de
fuentes y una copia SQLite previa a migración en `~/.local/state/argos/checkpoints`
(no son copias fuera del disco). Con Core apagado y sin RUNNING/QUEUED se registró
`some-and-co2` en `/home/tyrant/Proyectos/some-and-co2`, se inspeccionó su README y
manifiesto y se seleccionó en la sesión `default`. La ficha documenta una plataforma
SaaS de cálculo, gestión y comunicación de huella de carbono. No se editaron sus
fuentes ni se creó/aprobó una mejora de producto sin objetivo definido.

Se verificó la selección al reabrir SQLite y después al arrancar el Core de voz.
La preferencia encontrada estaba apagada; se activó manos libres conforme a la
petición vigente del usuario y se eliminó cualquier proyecto fijo de la captura
para que siga la selección de sesión. Estado comprobado: `voice_ready=true`,
`wake_enabled=true`, `listening_for_argos`, SteelSeries y cero errores. El proyecto
seleccionado y los tres módulos son accesibles por IPC en el proceso nuevo.
