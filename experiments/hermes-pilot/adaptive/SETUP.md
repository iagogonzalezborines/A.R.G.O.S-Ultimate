# Continuar en el equipo principal

Estado al 6-11-2026: [red experimental ejecutada](../reports/adaptive-network-2026-11-06.md), A/B operativos conservados; no migración ni funciones de operación/publicación de C/D. El [catálogo](CATALOGUE.md) distingue pruebas de candidatos. No copiar bases privadas, modelos ni autenticación mediante Git.

## 1. Base validada y laboratorio

Usar Linux para reproducir esta prueba. Se necesitan Git, Python, bubblewrap, el piloto A/B con su entorno nativo y Codex fijado. El [informe A](../reports/restoration-2026-11-06.md) registra versiones, reparación de persistencia y dependencias de voz; el [informe B](../reports/block-b-2026-11-06.md) registra permisos/Projects. `scripts/prepare_hermes_pilot.py` materializa fuentes pero **no construye automáticamente esas dependencias**. En una máquina sin piloto A validado, completar primero esa restauración y su prueba de aislamiento: este script rechaza un Hermes sin el pin/parche requerido.

Desde la raíz del repositorio, elegir rutas privadas y una raíz visible nueva para fixtures:

```sh
ARGOS_BASE="$HOME/.local/share/argos-hermes-pilot"
ARGOS_LAB="$HOME/.local/share/argos-adaptive-lab"
ARGOS_FIXTURES="$HOME/Proyectos/argos-adaptive-fixtures"
python scripts/prepare_adaptive_lab.py plan --lab "$ARGOS_LAB"
python scripts/prepare_adaptive_lab.py init --lab "$ARGOS_LAB" \
  --base "$ARGOS_BASE" --projects "$ARGOS_FIXTURES"
```

`init` requiere un laboratorio nuevo, comparte las dependencias ya validadas mediante enlaces y crea **estado/credenciales/configuración separados**, sin arrancar nada. Nunca pasar la instalación habitual como `--lab`. Está comprobado con un destino temporal: autenticación ausente, herramientas y políticas preparadas, baseline intacto. Los enlaces a dependencias se reconstruyen en casa; no trasladar enlaces con rutas del portátil. Actualizaciones posteriores de fuentes usan el instalador existente contra `--destination "$ARGOS_LAB/pilot"`, que conserva cambios locales.

El manifiesto versionado fija runtimes/modelo y declara proveedores deshabilitados. La copia privada `local/config.json` configura inferencia; `pilot/installation.json → adaptive.local` debe contener la misma selección. Las raíces autorizables solo incluyen fixtures. `review_dispatch=false` es obligatorio: el adaptador rechaza un dispatcher que vuelva a ejecutar tarjetas en revisión.

## 2. Un modelo local, bajo demanda

Reutilizar Ollama 0.40.7 si está instalado. En una máquina limpia, instalar el binario oficial para su plataforma y verificar versión/origen antes de ejecutar. El helper no instala otro runtime ni ejecuta un instalador remoto con privilegios. El único `pull` de esta prueba es Qwen3 0.6B, unos 523 MB; dejar margen para binario, caché y modelo residente.

```sh
# Terminal A: servidor aislado, primer plano; Ctrl-C lo detiene.
python scripts/prepare_adaptive_lab.py serve --lab "$ARGOS_LAB" --ollama /ruta/a/ollama
# Terminal B: descarga seleccionada y comprobación del digest revisado.
python scripts/prepare_adaptive_lab.py pull --lab "$ARGOS_LAB" --ollama /ruta/a/ollama
python "$ARGOS_LAB/pilot/adaptive/local_check.py" \
  "$ARGOS_LAB/local/config.json" "$ARGOS_LAB/local/result.json"
```

El puerto de laboratorio es 11554, solo loopback; no comparte el almacén del servidor habitual. Cloud deshabilitado, un modelo cargado, una inferencia concurrente, cola Ollama de dos, contexto 2048, salida máxima 512, dos hilos y CPU. `keep_alive=30s` reutiliza el modelo brevemente; el controlador descarga el modelo inactivo bajo presión y al cancelar/fallar. No hay servicio de autoinicio.

Para GPU en casa, revisar disponibilidad/controlador/CUDA y memoria **antes** de cambiar `options.num_gpu` de `0` a `-1` u otro límite admitido en ambas configuraciones privadas. El helper solo oculta CUDA cuando se selecciona CPU. No instala CUDA ni cambia STT/TTS. Medir VRAM con el contexto real; no solapar una carga que expulse la voz. `min_available_bytes` reserva inicialmente 2 GiB de RAM disponible: es admisión, no un límite duro de cgroup. El adaptador acota hilos, contexto, slots y tiempo, pero no implementa aún un presupuesto global de VRAM compartido con voz.

Otro modelo compatible requiere seleccionar etiqueta, comprobar licencia, registrar el **digest completo revisado**, ajustar presupuesto y repetir calidad/latencia. No sustituir el digest automáticamente tras un `pull`: una etiqueta puede cambiar. Opciones permitidas: contexto 512–8192, salida 1–512, hilos 1–16, GPU -1–200; vida inactiva 0/10/30/60 segundos. Estos topes son controles, no garantías de que una combinación quepa en la máquina.

## 3. Codex, capacidades y pruebas

Autenticar de forma independiente mediante el flujo soportado de Codex/Hermes, apuntando explícitamente a los hogares del laboratorio. Para Codex:

```sh
env HOME="$ARGOS_LAB/pilot/home" CODEX_HOME="$ARGOS_LAB/pilot/state/codex" \
  "$ARGOS_BASE/bin/codex" login --device-auth
```

El piloto también necesita su credencial nativa `state/hermes/auth.json` mediante su login `openai-codex`; usar el flujo del pin (`hermes auth --help` con `HERMES_HOME` del laboratorio) y no una API key. El helper no copia credenciales del IDE ni transforma tokens. En esta sesión se reutilizaron copias privadas del login aislado ya autorizado del piloto y se retiraron al cerrar. El instalador configura MCP `adaptive` con aprobación de transporte; **eso no autoriza carpetas**: la aprobación de proyecto sigue pasando por la vía confiable de B.

```sh
python "$ARGOS_LAB/pilot/adaptive/qa.py"
python "$ARGOS_LAB/pilot/projects/qa.py"
PYTHONPATH=src python -m unittest discover -s tests -v
# Explícito: consume suscripción, crea proyectos desechables y ejecuta código aislado.
python "$ARGOS_LAB/pilot/adaptive/live_check.py"
```

`live_check` crea dos fixtures, pide a General un workflow inventario → extensiones, despacha Engineering, solapa extracción local, consulta aplicaciones y conversa, cierra General/reabre Broker y repite el unittest generado en el sandbox de validación. Produce `reports/adaptive-live.json` y `adaptive-workflow.canvas`. No captura/reproduce audio ni abre aplicaciones reales. Verificar siempre timestamps/artefactos, no solo respuestas del modelo.

General usa `catalog`, `submit`, `workflow`, `status`, `canvas`, `tick`, `cancel`. `items` exige `format=lines|prose`; las listas usan código, la prosa el modelo. Cada workflow tiene hasta ocho nodos, validación completa previa de payload/dependencias y claves idempotentes. Las entradas de catálogo no ejecutables no se registran. Los modelos quedan en revisión semántica; sus descendientes no avanzan sin aceptación confiable. Esta primera superficie no incorpora aún esa aceptación ni edición arbitraria de workflows.

Engineering tiene un escritor; el tablero auxiliar comparte un slot entre todos los proyectos. El límite global nativo es dos. La presión deja la tarea pendiente; `tick` explícito reevalúa tras presión/reinicio. Los eventos de finalización avanzan la cola nativa. No hay otro scheduler ni daemon de polling. Las interrupciones con intentos previos se aparcan para inspección, sin repetir efectos.

## 4. OpenClaw opcional y separado

Solo instalarlo si se va a repetir la comparación. Node 26 y npm fueron los usados; comprobar los requisitos del paquete fijado. El helper instala npm con scripts de instalación deshabilitados y luego el plugin oficial específico. No conecta canales externos.

```sh
python scripts/prepare_adaptive_lab.py openclaw --lab "$ARGOS_LAB"
python experiments/hermes-pilot/adaptive/openclaw_prepare.py \
  --candidate "$ARGOS_LAB/openclaw" --base "$ARGOS_BASE"
```

Revisar `openclaw/state/openclaw.json`, sin volcar su token. Usa Codex App Server con el lanzador/política de A, hogar independiente y un Docker por sesión, sin red, raíz de solo lectura, 512 MiB, una CPU, 64 PIDs y `capDrop=ALL`. Workboard necesita además sus tres herramientas de protocolo en la allowlist de sandbox. No conceder `--admin`, herramientas elevadas ni host exec para resolver un fallo. Fijar la imagen por digest del equipo antes de probar. La imagen Node usada aquí ya estaba instalada; **no incluye Python**, lo que impidió que el trabajador verificase por sí mismo su módulo.

Para la autenticación, ejecutar el login Codex anterior con `HOME="$ARGOS_LAB/openclaw/home"` y `CODEX_HOME="$ARGOS_LAB/openclaw/codex"`. Lanzar los comandos siguientes en un shell cuyo entorno esté explícitamente limitado a ese HOME, CODEX_HOME, PATH y `OPENCLAW_STATE_DIR="$ARGOS_LAB/openclaw/state"`:

```sh
node "$ARGOS_LAB/openclaw/node_modules/openclaw/openclaw.mjs" gateway run --port 19831
# Otra terminal, mismo entorno privado:
node "$ARGOS_LAB/openclaw/node_modules/openclaw/openclaw.mjs" workboard create \
  "Implement fixture notes" --agent main --status ready --notes \
  "Create fixture_notes.py append_note(path,text), preserving existing UTF-8 lines. Add and run a unittest for two appends. Compile the module. Request review with artifact paths. No network or installs." --json
node "$ARGOS_LAB/openclaw/node_modules/openclaw/openclaw.mjs" workboard dispatch --max-starts 1 --json
```

Las pruebas comparables deben usar el mismo modelo, objetivo, criterios y herramientas disponibles; anotar diferencias de imagen y arranque. `agent --local` solo puede usar su estado si el Gateway está detenido: se comprobó el rechazo cuando existe otro propietario. Los estados `done`/`review` no son equivalentes a la aceptación confiable de ARGOS. Repetir A/B completos y adaptar la UI/voz antes de cualquier propuesta de sustitución. No apuntar Hermes y OpenClaw a los mismos proyectos.

## 5. Voz, navegador y cierre

Conservar la voz/persona actuales. En casa, seleccionar micrófono/dispositivo, recrear los entornos STT/TTS fijados y validar primero sin altavoces; después una prueba de voz explícita. El camino CUDA sigue en el código. La extensión firmada `argos-media-0.1.4-firmado.xpi` está en el otro equipo: instalar esa copia y registrar el native host, sin rebajar políticas de Firefox. No hay activación nueva de email, calendario, Discord, Telegram, publicación o impresoras.

Al cerrar: inspeccionar que no quedan intentos activos; detener los propietarios nativos **del laboratorio** por su hogar/perfil, el Gateway candidato y el servidor Ollama de la terminal; retirar solo sus contenedores identificados por montajes al candidato y copias derivadas de autenticación. Conservar los informes saneados y, fuera de Git, la evidencia de fallos. No usar `killall`, `docker prune` ni borrar modelos/estados del usuario.

Linux es la única plataforma validada de esta integración: `fcntl`, `/proc`, bubblewrap y la política de archivos son adapters concretos. Los contratos de capacidades, schemas y JSON Canvas no dependen de ellos. Windows sigue siendo requisito arquitectónico; falta su implementación/verificación de aislamiento y ciclo de proceso. No sustituir estos controles por ejecución sin sandbox para aparentar compatibilidad.
