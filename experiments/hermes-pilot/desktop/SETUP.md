# Escritorio acotado: Linux / Wayland

Agent Desktop **1.2.0** y galculator **2.1.4-12** quedan fijados en [pin.json](pin.json). La preparación descarga unos 3,5 MB, verifica SHA-256 y conserva binario/helper/recursos juntos en una carpeta privada. Requiere Python con soporte tar/zstd (aquí 3.14), GTK3, GI/AT-SPI, libquadmath y bubblewrap ya instalados. No instala paquetes globales ni modelos. El paquete de calculadora utilizado también se verificó con el keyring Arch del equipo.

Desde el repositorio, con el piloto A/B ya preparado:

```sh
python scripts/prepare_hermes_pilot.py --register
python scripts/prepare_agent_desktop.py --activate
```

Reabrir **ARGOS (Hermes)**. `--activate` declara los perfiles autorizados y añade la herramienta opcional al conector existente. Sin esa opción solo prepara los archivos. El login se conserva. Un binario modificado o un bus de accesibilidad no disponible impide anunciar la herramienta; no impide iniciar General. Para desactivarla, establecer `desktop_enabled: false` en la configuración privada y reiniciar.

- «Abre la calculadora» usa el camino determinista existente de aplicaciones.
- «Usa la calculadora para calcular 12 + 25 y comprueba la pantalla» usa General → Broker → controles reales → lectura del resultado. Se prefieren nombres observados de botones a copiar referencias opacas.
- «Compara estos dos archivos de texto» puede abrir **copias** en Meld, si está instalado; máximo 4.096 caracteres por archivo, sin controles de edición expuestos al modelo. Los originales siguen bajo la política Files existente. `ready=false` indica que la observación aún no acredita que se cargaron los documentos.
- `status`, `cancel`, `observe` y `release` operan únicamente los procesos creados por este controlador. Cerrar un panel no cancela una secuencia. Cancelar puede dejar efectos parciales; nunca repite automáticamente los clics. Reiniciar no recupera ni reproduce acciones de escritorio.

Wayland: se usa AT-SPI, con `GDK_BACKEND=wayland` en las aplicaciones probadas. Un lector complementario recupera el texto de la ventana por PID y ruta AT-SPI cuando Agent Desktop omite el documento. No hay entrada global, ratón virtual, portapapeles ni capturas. La allowlist no confina por sí sola una aplicación: los buses de sesión/accesibilidad siguen siendo autoridad ambiental. No se entrega ese acceso a Engineering. Los snapshots se guardan en el directorio privado del alcance y se eliminan al liberarlo/cerrar el controlador.

No se ha bifurcado upstream ni se necesita otro agente. Si se amplía a aplicaciones que exijan teclas/foco/arrastre, hace falta una ruta específica y probada del compositor o portal. No se asume que Mutter RemoteDesktop funcione en Hyprland, ni se sustituye un rechazo semántico por entrada física silenciosa.

## Repetir la prueba real sin audio

La instalación desechable usa credenciales derivadas y las dependencias existentes. No modifica proyectos del usuario. Debe empezar sin `/tmp/argos-desktop-qa/pilot`; conservar antes cualquier evidencia anterior.

```sh
python experiments/hermes-pilot/desktop/qa_prepare.py
node /tmp/argos-desktop-qa/pilot/desktop/qa_live.cjs
node /tmp/argos-desktop-qa/pilot/desktop/qa_layout.cjs
python experiments/hermes-pilot/desktop/qa_prepare.py --cleanup
```

El último comando debe ejecutarse también si falla la prueba. Resultados y captura: `/tmp/argos-desktop-qa/pilot/reports/desktop-live/`. El test abre calculadora/Meld reales y una ventana Electron de prueba; no usa micrófono ni altavoces. La suite normal `PYTHONPATH=src python -m unittest discover -s tests -v` no toca aplicaciones reales.

## Ventanas accesibles y segundo plano

La ampliación de Hyprland se instala con el mismo materializador. En ARGOS, abre **Control de aplicaciones**, autoriza la lectura de una ventana y revisa cada modificación o activación. Retirar acceso no cierra una aplicación del usuario. Las autorizaciones no sobreviven al reinicio. Informe, evidencia, límites de entrada física y plan de reversión: [segundo plano](../reports/desktop-background-2026-11-09.md).

Prueba nativa optativa, solo con autorización para enfocar ventanas desechables y producir entrada sintética de prueba:

```sh
python experiments/hermes-pilot/desktop/qa_background.py --foreground-consent --output /tmp/argos-background-evidence
```

La automatización de interfaz `desktop/qa_windows_ui.cjs` se ejecuta desde una instalación desechable preparada por `qa_prepare.py`; exige sesión gráfica y usa General real. `ARGOS_QA_SKIP_GENERAL=1` limita la repetición a los controles deterministas. Al terminar, ejecuta `qa_prepare.py --cleanup` para retirar credenciales derivadas. No ejecutar estos harnesses durante un trabajo del usuario que necesite conservar el foco.

## Sesión visual independiente (opcional y fijada)

En el piloto ya preparado, con Agent Desktop operativo, cerrar antes cualquier sesión visual en uso:

```sh
python scripts/prepare_hermes_pilot.py --register
python scripts/prepare_visual_desktop.py --activate
```

Instala paquetes fijados en `~/.local/share/argos-desktop/visual-1`, compila dos auxiliares pequeños y registra su manifiesto en la configuración privada. Requiere Linux x86_64, bubblewrap, GTK3/GI, compilador C, wayland-scanner y las bibliotecas Wayland/XKB del sistema. El pin se probó sobre este entorno Arch; no se presume compatibilidad binaria con cualquier distribución. No cambia servicios ni portales, no descarga modelos y no abre una aplicación. Sin `--activate`, solo prepara los componentes. Si el espejo retira una versión, buscar el mismo archivo en un archivo oficial y verificar el hash; no actualizar el pin silenciosamente.

Próximo arranque → **Control de aplicaciones → Abrir lienzo visual aislado**. La revisión autoriza capturas e interacción exclusivamente dentro de esa sesión sin red. General puede interpretar las capturas mediante el Codex configurado. Meld admite copias de dos archivos pequeños ya autorizados; los cambios son temporales. Retirar acceso elimina las copias. [Alcance, seguridad y evidencia](../reports/desktop-visual-2026-11-09.md).

Prueba nativa, sin entrada física al host ni audio:

```sh
python experiments/hermes-pilot/desktop/visual/qa_native.py --output /tmp/argos-visual-new-evidence
```

Prueba completa de aplicación/General: preparar la instalación desechable mediante `desktop/qa_prepare.py`, activar allí el conjunto con `prepare_visual_desktop.py --pilot /tmp/argos-desktop-qa/pilot --activate`, y ejecutar `node /tmp/argos-desktop-qa/pilot/desktop/visual/qa_ui.cjs`. Este harness crea otro compositor privado para Electron, separado del scope de ARGOS. Usa la suscripción existente. Ejecutar siempre `desktop/qa_prepare.py --cleanup` al terminar para retirar las credenciales derivadas. Los tests normales no abren estos compositores.

## Aplicaciones reales y documentos de proyecto

Sobre la instalación anterior, sin descargar paquetes:

```sh
python scripts/prepare_hermes_pilot.py --register
```

En **Control de aplicaciones**, revisar la habilitación de **Meld · editor de documentos** o **Thunar · archivos de trabajo** si están instalados. La habilitación comprueba el ejecutable y los recursos declarados y realiza un arranque/captura privados. El catálogo `visual/applications.json` contiene definiciones revisadas, nunca comandos recibidos del modelo. Un cambio de definición, ejecutable o recursos declarados invalida la habilitación. Las bibliotecas del sistema siguen dependiendo de la instalación de la distribución; no es un pin completo del sistema operativo.

Pedir, por ejemplo: «En el proyecto Biblioteca 3D, abre un editor, prepara sus requisitos y presenta la entrega a docs/requisitos.md». General resuelve el proyecto y una tarea nativa de escritorio. La primera revisión autoriza la aplicación, las copias importadas y la carpeta de entrega; la segunda muestra el documento concreto y el estado anterior del destino. Una acción de escritorio no confirma su propia revisión. Para documentos simples se mantiene el camino directo de Files.

Los documentos guardados se conservan en `project_state/desktop-artifacts/<sesión>/work`, vinculados mediante evidencia firmada al proyecto/tarea nativos. Las copias verificadas están fuera del montaje de la aplicación. Reiniciar no restaura permisos ni reproduce entrada/exportaciones. Desde **Proyectos → tarea → Archivos de escritorio** se inspecciona y propone la reapertura. Retirar acceso cierra la sesión; cancelar la tarea también cierra su aplicación y conserva lo guardado. El texto sin guardar no tiene recuperación garantizada.

Formatos entregables: UTF-8 `.md`, `.txt`, `.csv` y JSON válido, hasta 256 KiB por archivo. Importación explícita de hasta ocho archivos pequeños, con presupuesto conjunto de 28 KB de texto serializado. No se monta el proyecto completo. Hasta ocho espacios conservados por tarea, 64 archivos inspeccionados y profundidad cuatro; no hay eliminación automática de documentos guardados ni sincronización entre equipos. Revisar el tamaño del estado nativo antes de acumular trabajos. La carpeta de entrega autorizada puede tener hasta tres componentes; la entrega va directamente dentro de ella. Nombres y contenidos que parezcan credenciales quedan excluidos.

**Reproducir la prueba:** empezar sin `/tmp/argos-desktop-qa/pilot`, conservando antes la evidencia de cualquier ensayo anterior. `qa_prepare.py --projects` prepara el login derivado, habilita Projects/Project Map y la herramienta Projects y configura exclusivamente las raíces desechables. Los harnesses rechazan raíces personales. El conjunto visual debe estar previamente preparado en la instalación de origen:

```sh
python experiments/hermes-pilot/desktop/qa_prepare.py --projects
python /tmp/argos-desktop-qa/pilot/projects/qa_desktop.py
python /tmp/argos-desktop-qa/pilot/desktop/visual/qa_artifacts_native.py
node /tmp/argos-desktop-qa/pilot/desktop/visual/qa_artifacts_ui.cjs
python experiments/hermes-pilot/desktop/qa_prepare.py --cleanup
```

Usar el Python del piloto para los checks nativos si el Python del sistema no tiene sus dependencias. El segundo check habilita los dos perfiles en QA y usa aplicaciones reales; el tercero usa Electron y General/Codex reales en otro compositor privado. Los tests no escriben proyectos personales ni usan micrófono/altavoces. Ejecutar la limpieza de credenciales derivadas también después de un fallo. Evidencia y límites: [aplicaciones y entregas](../reports/desktop-artifacts-2026-11-09.md).

**Reversión:** retirar los accesos visuales y eliminar las habilitaciones de `desktop.state/visual-profiles.json` impide nuevas aperturas de esos perfiles; reiniciar ARGOS. Para volver al código anterior, materializar el commit `2ca8855` en un destino separado, conservando configuración y estado privados. No borrar `project_state/desktop-artifacts` ni las tablas/comentarios nativos si se desea recuperar documentos. Los archivos ya entregados permanecen en el proyecto. No hay paquetes globales, portales ni reglas de Hyprland que restaurar.
