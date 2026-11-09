# Especialidades técnicas y artefactos persistentes — 9 de noviembre de 2026

**Archify, Anatomy, CAD paramétrico y Blender están integrados con General, Engineering nativo y Project Map.** Las cuatro peticiones naturales produjeron archivos reales dentro de un proyecto desechable. LearnHarness queda evaluado y no habilitado. No se añadió un runtime, scheduler, base de tareas, memoria ni proveedor.

[Ejecución real](specialized-2026-11-09/execution.json) · [interfaz final](specialized-2026-11-09/ui.json) · [comprobación independiente de los diseños](specialized-2026-11-09/fixture-acceptance.json) · [ejemplos editables y exportaciones](specialized-2026-11-09/example-project/README.md) · [preparación selectiva](../adaptive/SPECIALIZED-SETUP.md).

## Integración e inspección

| Repositorio y revisión fijada | Licencia y mecanismo utilizado |
|---|---|
| [Archify](https://github.com/tt-a1i/archify/tree/11b0d6031853bdae89eed57e7979aabbf0034097) | Apache-2.0; renderizadores y comprobador estático Node sin instalar su entorno de desarrollo. HTML autónomo y JSON editable. |
| [Anatomy](https://github.com/wheresryan22/anatomy/tree/1482e8469b0a9e0d8cc18ea2740a01423d29ae80) | MIT; kit SVG, referencias y ejemplo de comparador. Sin galería, publicación, conducción de Chrome ni servicio nuevo. |
| [text-to-cad](https://github.com/earthtojake/text-to-cad/tree/1cfd73cbbf0be943e0ff7aa0c672f824935b98a7) | MIT; biblioteca `cad` 0.11.3 y su integración build123d, Python 3.14, entorno privado con 65 dependencias de ejecución fijadas por versión/hash. Se revisaron el empaquetado y su `.pth` de carga diferida, limitado a ese intérprete. Sin servidor/viewer/MCP, telemetría del servidor, extras FEA ni impresoras. |
| [blender-skills](https://github.com/EL4CTEO/blender-skills/tree/389f28addc79b87b28764898e38e7bf408d14b77) | MIT para skills; Blender conserva sus licencias GPL y de distribución. Blender **5.2.3 LTS**, archivo oficial Linux x86-64 con SHA-256 fijado. Scripting headless, configuración de fábrica, autoejecución desactivada, dos hilos y CPU. La prueba no certifica todas las 28 skills. |
| [LearnHarness](https://github.com/amosblomqvist/learnharness/tree/da08cb5f7d098598ba963c6689b22054c9f2a5a3) | AGPL-3.0-only; evaluación de código/documentación, sin instalación ni copia de su runtime. |

Las skills orientadas a Claude se pudieron utilizar como instrucciones y bibliotecas dentro de Codex; no se asumió compatibilidad por su nombre. Sus consejos de instalar, publicar o cambiar reglas globales no amplían la autorización de ARGOS. Se conservaron las licencias/avisos, también junto a los HTML exportados. No se ejecutaron los instaladores globales upstream ni se instalaron paquetes del sistema.

El catálogo compartido declara propósito, permisos, salidas, presupuesto, revisión, ejecutor y disponibilidad. Descargar fuentes deja `installed_unverified`; solo la validación privada permite `available_validated`. Dependencias ausentes, candidatos experimentales y herramientas no integradas se distinguen. Crear/despachar una tarea vuelve a comprobar fuentes y ejecutables; un cambio rechaza la admisión. Discovery no inicia modelos ni procesos gráficos.

General selecciona `capability` al crear una tarea **Engineering** existente. Su brief conserva requisitos, decisiones, instrucciones revisadas, comandos privados y criterios. Archify recibe una proyección acotada de registros nativos con IDs/revisión y aviso de snapshot; no posee estado editable del tablero. Las ediciones de una tarea no iniciada conservan la especialidad y actualizan esa proyección. Reintentos, CAS, deduplicación, dependencias, cancelación y recuperación siguen siendo nativos. Un escritor y una comprobación de memoria disponible limitan la admisión; no hay un nuevo planificador. Los presupuestos no constituyen un límite de RAM impuesto por el kernel.

## Recorrido real y correcciones

Electron y General/Codex reales, con Projects/Kanban reales y archivos desechables:

1. Una autorización de proyecto permitió cuatro solicitudes naturales. Se comprobó en el brief nativo que General eligió la especialidad registrada correspondiente, no solo que mencionara su nombre.
2. Archify produjo el flujo petición → requisitos → tarea → Engineering → revisión. El snapshot inicial no contenía tareas y el diagrama lo dice; no inventa IDs ni estados de esas etapas conceptuales. Su CLI exterior intentó un subprocess incompatible con el sandbox (`EPERM`). Se corrigió la integración para llamar directamente al renderizador y al comprobador registrados, conservando A.
3. Anatomy generó un comparador con tres bloques, HTML autónomo y script editable. Se probó que Home/End cambian su lectura; el aviso distingue ilustración y medición real.
4. CAD creó `bracket.py`, STEP, STL y medidas. Una lectura independiente del STEP confirmó **un sólido válido, 40 × 30 × 24 mm y 7.200 mm³**. No se comprobó resistencia, material, tolerancias de fabricación ni cargas.
5. Blender produjo un jarrón azul: fuente, `.blend`, `.glb` y PNG. La reapertura independiente, con autoejecución desactivada, confirmó una malla, cámara, luz y render **Cycles CPU, cuatro muestras, 320 × 240**. Es una vista previa pequeña y ruidosa, no un render final de calidad comercial.
6. Una tarea de corrección conservó los diseños, resolvió la comprobación de Archify y añadió imports portables, reproducción y licencias. Se preservó la evidencia del primer intento; no se volvió a generar todo el proyecto para ocultar el fallo.
7. Reiniciar servidor, conversación y Electron recuperó el mismo proyecto y los cuatro resultados, sin otra ejecución. Una tarea adicional de QA llegó a una espera real, siguió activa al cerrar los paneles y se canceló mediante la terminación nativa. La conversación siguió disponible.

Los cuatro trabajos iniciales tuvieron un intento cada uno: **154, 100, 95 y 261 segundos**, respectivamente. Una respuesta conversacional durante Engineering tardó **5,42 s**; una consulta de aplicaciones observada tardó **3,60 ms**. Son medidas de esta sesión, no garantías. El acuse de despacho de las peticiones especializadas tardó aproximadamente 34–55 s: no se presenta la delegación completa como instantánea.

El Project Map abre los HTML en una vista aislada, muestra PNG y conserva fichas de STEP/STL/GLB/BLEND sin ejecutarlos. Incluye catálogo, ampliación y verificación técnica. Las pruebas encontraron y corrigieron el control de ampliación dentro del contenido desplazable, la imagen abierta antes de terminar de cargar, una respuesta de sondeo que adelantaba el estado de una acción y la comparación de hashes que confundía archivos de otras tareas con evidencia antigua.

Capturas inspeccionadas: [arquitectura ampliada](specialized-2026-11-09/architecture-expanded.png), [comparador](specialized-2026-11-09/anatomy-expanded.png), [Blender](specialized-2026-11-09/blender-preview.png), [catálogo](specialized-2026-11-09/catalogue.png), [verificación](specialized-2026-11-09/verified.png), [panel estrecho](specialized-2026-11-09/narrow.png). La pasada final reúne **18 comprobaciones UI**; el recorrido inicial, **11**, además de comprobar los cuatro IDs de especialidad en registros reales. Las repeticiones de UI reutilizaron los trabajos existentes.

## Seguridad, verificación y recursos

Se mantuvieron el pin Hermes y la reparación de persistencia de A, las restricciones de red/credenciales y las autorizaciones de B. Los nuevos ejecutables viven en el directorio privado de herramientas ya permitido de solo lectura; las escrituras siguen limitadas al proyecto. El sandbox de validación comprobó realmente la ausencia de credenciales del host, archivos privados del controlador, bus del usuario, entrada física, GPU y salida de red: [resultado](specialized-2026-11-09/security.json).

El visor usa origen opaco, sandbox, CSP sin conexiones/formularios/subframes y bloqueo de navegación, ventanas emergentes y descargas. Las pruebas verificaron rechazo de acceso al documento padre, almacenamiento, bridge de ARGOS, Node, red y navegación al controlador. Los controles de exportación/portapapeles propios del HTML pueden quedar bloqueados: los archivos persistidos son la entrega. No se abre otra aplicación ni se concede autoridad al pulsar un artefacto.

**Integridad técnica** es un perfil fijo del controlador, offline y con proyecto de solo lectura, tiempo/CPU/salida/memoria acotados y evidencia firmada en comentarios nativos. Reabre CAD/Blender y comprueba estructura/formatos; no ejecuta los scripts generados para verificar sus propios resultados. La firma no convierte los requisitos del usuario en comprobados: la aceptación permanece separada. Los archivos modificados después invalidan la verificación. Los resultados de QA quedan en revisión, con integridad comprobada; no representan aceptación humana.

[Medición de toolchains](specialized-2026-11-09/toolchains.json), sobre fixtures pequeños sin inferencia:

| Herramienta | Ejecución observada | Máximo RSS sumado muestreado |
|---|---:|---:|
| Archify, render directo | 0,20 s | 87 MiB |
| Anatomy | 0,10 s | 61 MiB |
| CAD, construir/exportar/reabrir | 6,56 s | 467 MiB |
| Blender, escena/exportación/render | 3,74 s | 493 MiB |

Muestreo objetivo 50 ms, intervalo máximo observado inferior a 51 ms. Sumar RSS puede contar páginas compartidas; no mide el pico único del sistema ni GPU. No se usan los datos iniciales de `wait4` del supervisor como consumo del motor. CAD ocupa aproximadamente 874 MiB de disco y Blender 1,2 GiB; no permanecen ejecutándose cuando acaba el trabajo.

Regresiones: Core **420** (incluidas 50 de Desktop y cuatro nuevas de catálogo/integridad), lifecycle **21**, Desktop/artifacts **17**, mapa nativo **3**, especialidades nativas **3**, Adaptive **7**, Files **25**, almacenamiento/clipboard **21**, investigación **17**, arranque **10**, entrada escrita y PCM real a sumidero nulo. No se reprodujo por los altavoces ni se tocaron proyectos personales. [Registro de validación](specialized-2026-11-09/validation.json).

## LearnHarness y relevo

LearnHarness 0.5.0 es una aplicación Electron/Next con su propio runtime pi, sesiones, roles y grafo persistente. Documenta conexiones ChatGPT, Copilot y Grok, además de API keys, Claude Code y endpoints compatibles; el código de ChatGPT mantiene autenticación privada propia. **No se probó esa conexión con la suscripción de ARGOS**, ni se trasladaron sus credenciales. El almacenamiento local no evita que modelos, investigación o dictado envíen datos a proveedores. Su guardia de rutas no es un sandbox.

Puede estudiarse como aplicación independiente aislada con un alcance y login propios. No se justificó otro grafo/autoridad de memoria para este hito; por eso no se instaló ni anunció como herramienta ejecutable. Se conserva como candidato, sin inferir incompatibilidad por estar orientado a Claude ni por su licencia. No se incorporó código AGPL al runtime de ARGOS.

La instalación habitual quedó actualizada con el materializador; el [catálogo instalado](specialized-2026-11-09/installed.json) confirma las cuatro capacidades validadas, disponibles al próximo arranque. La [limpieza de QA](specialized-2026-11-09/cleanup.json) dejó cero tareas activas, retiró su autenticación derivada y terminó su gateway desechable sin alterar el login habitual. Preparación y reversión: [procedimiento](../adaptive/SPECIALIZED-SETUP.md). No copiar credenciales o bases privadas por Git. Los ejemplos exportados son archivos, no una migración del tablero entre máquinas.

Pendiente para casa: uso propio de las cuatro especialidades, lectura/teclado con el DPI real, voz/micrófono/altavoces y aceptación humana de los diseños. GPU, otros sistemas/arquitecturas, CAD complejo/FEA/fabricación y la aplicación LearnHarness no se dan por validados. Se preservan Firefox, Desktop semántico/visual, Projects, Engineering, conversación y voz. Commit: el que incorpora este informe, implementación y evidencia.
