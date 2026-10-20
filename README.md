# ARGOS · base Linux 0.1

Nueva implementación basada en los requisitos recuperados. No es una copia
del ejecutable Windows perdido. Core Python/SQLite, especialistas acotados,
trabajo en segundo plano y consola ASCII independiente. Python 3.11+;
sin dependencias Python de ejecución.

## Arrancar

Desde esta carpeta:

```bash
./argos serve
```

En otra terminal:

```bash
./argos console
```

La consola solo muestra una esfera. Ctrl-C cierra la visualización; el Core
continúa en su terminal. El Core no requiere tener la esfera abierta.
Los siguientes comandos son la interfaz de desarrollo y diagnóstico, no
una conversación que se imprime sobre la esfera:

```bash
./argos say "hola"
./argos agents
./argos add-project ARGOS /ruta/absoluta/al/proyecto/argos
./argos run repo.inspect --project ARGOS --wait
./argos run system.info --wait
./argos run stl.inspect --project MiPieza --file pieza.stl --wait
./argos run gcode.inspect --project MiPieza --file pieza.gcode --wait
./argos tasks
./argos task ID_COMPLETO
./argos reply ID_COMPLETO "ARGOS"
./argos say "activa modo gaming"
```

`--json`, `--session` y `--state-dir` son opciones globales y van antes del
subcomando. Las peticiones tienen ID idempotente. Al reintentar una petición
usa `--request-id MISMO_ID` con exactamente los mismos argumentos.

Estado por defecto: `$XDG_STATE_HOME/argos` o `~/.local/state/argos`.
Socket local privado, un único Core por carpeta y base con permisos de usuario.
Las tareas interrumpidas no se repiten automáticamente: `argos resume ID`
las vuelve a encolar después de revisarlas. Una petición sin resultado
confirmado tras caída exige revisión; no se reejecuta silenciosamente.

## Qué está conectado

| Rol | Capacidad real |
| --- | --- |
| Engineering | Estado Git y entradas visibles del proyecto, sin leer fuentes |
| Computer | Información del sistema y CPU |
| Design3D | Triángulos, límites y dimensiones de STL ASCII/binario |
| Printing3D | Metadatos parciales de G-code, sin conectar una impresora |
| General | Atajos locales; intérprete por modelo opcional |

Una definición de agente no es un modelo cargado. Los cuatro especialistas
ejecutan capacidades locales sin IA. Las tareas complejas quedan bloqueadas
de forma explícita cuando falta el proveedor o la herramienta.
Las respuestas de un modelo solo pueden solicitar capacidades registradas;
no pueden ejecutar shell arbitrario ni autoconcederse permisos.

## Contrato y proveedores

[ARGOS.md](src/argos/contracts/ARGOS.md) es el contrato de identidad y decisión
que se carga de verdad al consultar un proveedor. Los contratos de especialistas
se añaden según la tarea. Tono sobrio, directo, ironía discreta y respuestas
cortas salvo petición. Sin saludos forzados ni cadenas obligatorias de modelos.

No se descarga ni se activa un modelo por defecto. Existe un adaptador
opcional para **Ollama local ya instalado**:

```bash
./argos serve --ollama-model NOMBRE_DEL_MODELO_YA_INSTALADO
```

Una interpretación estructurada resuelve la ambigüedad; no se añade otra llamada
para Persona. El proveedor se comparte con concurrencia limitada. Solo recibe
el proyecto seleccionado, catálogo y decisiones de esa tarea, no todos los
proyectos ni fuentes del disco. Este adaptador se valida con un servidor de
prueba; la calidad y velocidad de un modelo real no están medidas.
Referencia: [API oficial Ollama](https://docs.ollama.com/api/chat).

Para Codex:

```bash
./argos doctor --codex
```

Comprueba el transporte App Server y el tipo de autenticación, sin crear un
hilo, llamar al modelo ni mostrar credenciales. **Todavía no es un adaptador de
ejecución Codex**. Conectar sus hilos persistentes y un bridge controlado es el
siguiente bloque de Engineering; no se ha introducido consumo de OpenAI API.
Referencia: [App Server oficial](https://learn.chatgpt.com/docs/app-server).

## Esfera y voz

La esfera flota suavemente en reposo y cambia con el RMS del audio de salida.
Para probar con un WAV PCM 16-bit propio, mientras Core y consola están activos:

```bash
./argos play-wav /ruta/al/audio.wav
./argos stop-speech
```

Usa `pw-play` o `aplay`. El medidor se sincroniza con el reloj de reproducción
del proceso, no con el reloj físico del dispositivo; puede haber desfase por
buffer de audio. Un solo propietario evita reproducciones superpuestas.
Parar audio no cancela tareas.

**Micrófono, wake word, STT y TTS aún no están conectados.** La entrada `say`
es texto de desarrollo y el WAV es audio real aportado por el usuario.
No hay una animación que finja una respuesta hablada.
El Core prepara avisos finales en memoria; falta el consumidor TTS.
GAMING los suprime y no los acumula para reproducirlos después.

## Alcance y límites

- No edita código, ejecuta Blender, controla aplicaciones ni imprime todavía.
- El comando «actualiza ARGOS» registra un bloqueo explícito: no hay instalador.
  El contrato define preparación, pruebas, candidato aprobado y activación;
  esos pasos no se anuncian como implementados.
- Base de Policy con huellas y aprobación de un uso; todas las capacidades
  conectadas son de lectura. Falta el flujo de aprobación por voz.
- No hay memoria semántica ni historial conversacional completo. Se conservan
  proyectos, tareas, decisiones y eventos; no audio ni razonamiento.
- El filtro de secretos rechaza patrones evidentes, no es un DLP completo.
  No pegar contraseñas en conversación.
- Los resultados 3D son inspecciones, no certificados de imprimibilidad.
- Adaptación Windows y su GUI quedan para una fase posterior.

## Validar

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
python scripts/benchmark.py
./argos doctor
```

Las pruebas usan temporales y audio silenciado; no cambian tus proyectos,
no abren aplicaciones, no llaman a modelos ni activan hardware.
Consulta [arquitectura](docs/architecture.md) y [validación](docs/validation.md).
