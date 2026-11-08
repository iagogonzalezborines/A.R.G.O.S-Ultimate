# Agent Desktop de Vercel — evaluación para ARGOS

8 de noviembre de 2026. **Evaluación documental y comprobación de prerrequisitos locales. No instalado, registrado como MCP ni habilitado en ARGOS. No se ha leído contenido de ventanas ni enviado entradas al escritorio.**

El repositorio confirmado por el usuario es [vercel-labs/agent-desktop](https://github.com/vercel-labs/agent-desktop). La release consultada es [v1.2.0](https://github.com/vercel-labs/agent-desktop/releases/tag/v1.2.0), publicada el 5 de noviembre. Su [README fijado a esa versión](https://github.com/vercel-labs/agent-desktop/blob/v1.2.0/README.md) describe una CLI/biblioteca que consulta accesibilidad y opera elementos mediante referencias de snapshot. El razonamiento permanece en el agente que la llama: no necesita otro modelo o coordinador dentro de ARGOS.

## Encaje con el equipo de casa

La sesión es Wayland/Hyprland. Está instalado `at-spi2-core 2.62.1-1.1` y el bus de sesión anuncia `org.a11y.Bus`. No existe un ejecutable `agent-desktop` en el PATH observado. Esto acredita prerrequisitos, **no** que el backend de Agent Desktop funcione aquí; la prueba real debe empezar por su propio `status`.

La [documentación Linux](https://agent-browser.dev/desktop/platforms/linux) describe observación y acciones semánticas sobre AT-SPI en X11 y Wayland. GNOME es el escritorio medido por el proyecto. Esas capacidades dependen de lo que cada aplicación expone; no equivalen a control universal de un escritorio Hyprland.

| Función | Evaluación para ARGOS en Hyprland |
|---|---|
| Observar una aplicación/ventana y sus controles | Candidata inicial; hay que verificar registro AT-SPI y selección inequívoca |
| Click semántico, valor de campo, selección o toggle | Candidata cuando el control expone esa acción; verificar el resultado con un nuevo snapshot |
| Referencias antiguas o ambiguas | Rechazar y volver a observar; el identificador pertenece al snapshot y proceso originales |
| Teclas en Wayland | La documentación exige Mutter RemoteDesktop; no afirmar compatibilidad con Hyprland |
| Ratón físico, arrastre y doble click | La ruta documentada es X11; Wayland devuelve operación no soportada |
| Enfocar/mover/redimensionar ventanas nativas | No soportado por esa ruta Wayland; los controles internos del workspace actual siguen siendo independientes |
| Capturas | Wayland usa portal con consentimiento; captura de ventana no soportada en la ruta documentada. Fuera de la primera prueba |
| Qt, Chromium y Electron | Registro accesible dependiente del toolkit. No reiniciar aplicaciones del usuario ni deshabilitar su sandbox para forzar una prueba |

Las notas de plataforma son documentación vigente, no mediciones locales de rendimiento o compatibilidad. Deben contrastarse con las guías incluidas en el binario fijado cuando se prepare el piloto.

## Integración propuesta

Conservar General, Hermes, el Broker y las capacidades actuales. Añadir una capacidad opcional de escritorio en el Broker, desactivada inicialmente. Para abrir una app conocida o reproducir música se mantiene la implementación específica existente; usar accesibilidad cuando una operación requiera interactuar con controles.

El primer alcance sería una calculadora de prueba elegida explícitamente. El controlador fija ejecutable, estado privado y ventana/proceso autorizado. Expone solo observación acotada y acciones semánticas permitidas sobre las referencias emitidas para ese alcance. Valida revisión, identidad del proceso y referencia antes de actuar, y observa de nuevo para comprobar el efecto. La selección visual no concede autoridad y el texto leído en una app es evidencia no confiable.

No conceder el bus del escritorio al trabajador Engineering ni al shell aislado. El componente confiable del Broker es quien opera el escritorio autorizado. Una herramienta gráfica que escribiese comandos en un terminal podría eludir el alcance de archivos/red de Engineering; no se incluye esa vía en el piloto.

El [MCP nativo de Agent Desktop](https://agent-browser.dev/desktop/guides/mcp) publica toda su superficie, incluido lanzamiento arbitrario. Su documentación indica que debe tratarse con el alcance de una shell del usuario. Por eso la propuesta no conecta ese servidor completo sin mediación: envuelve llamadas concretas mediante argumentos estructurados y un ejecutable fijo, sin shell ni flags de entrada elegidos por el modelo.

La primera superficie excluye terminales, lanzamiento arbitrario, entrada física global, portapapeles, capturas, credenciales, cuentas remotas y envío/publicación. Ampliar a un editor o explorador requiere revisar sus efectos posibles y el alcance de archivos. Un permiso de carpeta no confina por sí solo lo que una app gráfica puede hacer; no se presentará la allowlist como un sandbox de aplicaciones.

## Primera prueba propuesta

1. Preparar una copia privada de v1.2.0 con origen y checksum revisados; conservar ejecutable y helper Linux juntos. No instalación global ni autoinicio.
2. Leer la guía de plataforma incluida y ejecutar `status` con entorno de sesión explícito. Registrar solo capacidades/errores, no contenido personal.
3. Abrir una calculadora desechable mediante el catálogo existente, observar sus controles y comprobar una operación sencilla por acciones semánticas. No tomar el foco de otra app para superar un rechazo.
4. Probar referencias caducadas, proceso reiniciado, ventana no autorizada y operaciones no soportadas. Todo debe fallar sin actuar en otra ventana ni recurrir a una shell.
5. Medir observación, acción y verificación; después probar una petición natural mediante la misma conversación de General. No añadir una inferencia previa para routing ni otro runtime.

Hasta superar esa prueba, Agent Desktop es un candidato documentado, no una capacidad anunciada. La versión, el entorno y la superficie efectiva se fijarán en la configuración del controlador antes de cualquier activación.
