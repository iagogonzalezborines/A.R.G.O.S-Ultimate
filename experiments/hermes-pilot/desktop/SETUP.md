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
