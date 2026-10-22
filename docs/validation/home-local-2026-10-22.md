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
por el cliente. Un fallo de API impide nuevas peticiones durante esa prueba.

Pendiente: introducir una clave del proyecto gratuito en la terminal, ejecutar
la comparación y revisar naturalidad, continuidad, exactitud y latencia. No se ha
realizado ninguna llamada autenticada a Gemini, ni se ha cambiado el proveedor
del ARGOS que utiliza el usuario.
