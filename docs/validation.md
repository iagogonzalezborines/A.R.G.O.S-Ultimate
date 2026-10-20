# Validación de la base 0.1

20 de octubre de 2026. Linux, Python 3.14.8.

## Resultado

`PYTHONPATH=src python -m unittest discover -s tests -v`

49 pruebas aprobadas, 1,556 segundos en la última ejecución. Compilación de
bytecode de `src`, `tests` y `scripts` correcta. Arranque del launcher comprobado.

Cobertura de comportamiento:

- Contratos y catálogo, negaciones y ausencia de efectos en peticiones inciertas.
- Proyectos persistentes, aislamiento del contexto y continuidad del mismo ID.
- Estados de tarea válidos, cancelación, recuperación sin replay y reintentos
  idempotentes; las solicitudes inciertas tras caída exigen revisión.
- Estado disponible durante un proveedor lento y trabajo independiente mientras
  hay dos solicitudes para el mismo proyecto.
- Git real en un repositorio temporal, STL ASCII/binario y G-code de texto.
- Rechazo de escapes de ruta, enlaces simbólicos, coordenadas no finitas,
  capacidades inventadas, argumentos inesperados y credenciales evidentes.
- Policy con huella exacta y autorización de un solo uso.
- Core real como subproceso: socket privado, cliente desconectado, doble Core,
  petición malformada y flujo CLI completo.
- Consola sobre pseudo-terminal: dibuja, restaura pantalla/cursor y puede
  cerrarse sin detener Core.
- WAV PCM real con reproductor de prueba silencioso: amplitud, exclusión de
  reproducción y cancelación inmediata. Corregida una carrera que dejaba vivo
  el reproductor si se cancelaba antes de arrancar el medidor.
- Intérprete HTTP con servidor de prueba: contrato y esquema enviados en una
  única solicitud. No se ha medido un modelo real.

Las pruebas no reproducen sonido por los altavoces, no conectan impresoras,
no usan el modelo Codex ni modifican los proyectos del usuario.

## Latencia local

`python scripts/benchmark.py`, Core real y socket Unix en un directorio temporal:

| Flujo | Muestras | Mediana | p95 |
| --- | ---: | ---: | ---: |
| Saludo local, incluyendo IPC | 100 | 0,350 ms | 0,536 ms |
| Consulta de tareas, incluyendo IPC | 100 | 0,270 ms | 0,345 ms |
| Medidor de salida, incluyendo IPC | 100 | 0,249 ms | 0,331 ms |

`system.info` de extremo a extremo: una muestra de 1,458 ms.
Son medidas locales; excluyen STT, inferencia, TTS y latencia física de audio.
No se deben anunciar como velocidad de conversación.

## Codex

`./argos doctor --codex` comprobó App Server por stdio y autenticación de tipo
`chatgpt` en el Codex instalado (`0.154.0-alpha.6.2`). No se inició ningún hilo
ni turno de inferencia. No se verificó edición, continuidad de hilo ni ejecución
de herramientas mediante Codex; ese adaptador aún no está conectado.

## Pendiente

Micrófono, wake word, eco, STT, TTS, proveedor real de conversación, Codex con
ejecución y sesiones, control del escritorio, Blender, impresora y actualización
con instalación/rollback. No hay validación de voz física ni GUI Windows.
