# Preparación selectiva de especialidades

Requiere el piloto A/B validado, Projects habilitado, Linux x86-64, Python 3.14, bubblewrap y los Node/uv privados del piloto. Se conserva el login independiente de Codex. No se instala otro proveedor, agente, servidor CAD, addon de Blender ni skill global.

Desde el repositorio, preparar solo lo necesario:

```sh
python scripts/prepare_specialized.py diagram.architecture diagram.technical
python scripts/validate_specialized.py diagram.architecture diagram.technical --evidence /tmp/argos-toolchain-check
```

CAD y Blender son opcionales y requieren espacio adicional: en esta máquina el entorno CAD ocupa unos 874 MiB y Blender 1,2 GiB. El archivo de Blender necesita unos 385 MB temporales; el preparador lo elimina tras comprobar y extraerlo. No son modelos de IA.

```sh
python scripts/prepare_specialized.py cad.parametric design.blender
python scripts/prepare_specialized_runtime.py --cad --blender
python scripts/validate_specialized.py cad.parametric design.blender --evidence /tmp/argos-toolchain-check-3d
python scripts/prepare_hermes_pilot.py --projects on --project-map on --register
```

Los preparadores admiten `--pilot` para otro destino. Las fuentes se fijan por commit, los paquetes Python por versión y hashes en `cad-requirements.lock`, y el archivo Blender 5.2.3 LTS por SHA-256. Se conservan licencias, avisos y metadatos de las dependencias. No se ejecutan los instaladores upstream ni se altera el portal/Hyprland. No hay descargas al consultar el catálogo ni al despachar trabajo. Una preparación interrumpida deja la capacidad sin validar; inspeccionar y retirar únicamente su directorio privado incompleto antes de repetir, sin sobreescribir una instalación activa.

Reiniciar **ARGOS (Hermes)**. En **Proyectos → Herramientas especializadas** aparecen los estados. Pedir por texto o conversación un diagrama técnico, la arquitectura del proyecto, una pieza paramétrica o un objeto Blender. General consulta el catálogo y crea una tarea Engineering con la especialidad; la autorización sigue siendo la del proyecto. Solo hace falta un escritor, sin mantener modelos o aplicaciones cargados. La ausencia de dependencias se presenta como limitación de preparación.

Abrir los artefactos desde la tarea del Project Map. HTML usa un iframe opaco con red, formularios, popups, IPC y navegación bloqueados; **Ampliar artefacto** da más espacio. PNG se muestra directamente. STEP/STL/GLB/BLEND se conservan como archivos del proyecto: abrir su ficha no los ejecuta ni lanza una aplicación externa. Los controles de exportación/portapapeles de visores upstream pueden estar bloqueados dentro del iframe; usar los archivos persistidos del proyecto.

**Integridad técnica** ejecuta comprobaciones independientes en sandbox de lectura: estructura/check estático de diagramas, reapertura STEP y topología, reapertura Blender sin autoejecución y cabeceras GLB/PNG. No demuestra por sí sola todos los requisitos ni seguridad mecánica. Revisar medidas, interacción y criterios antes de aceptar. Los cambios posteriores invalidan la verificación. Los trabajos interrumpidos no se reproducen; se inspeccionan y requieren la autorización nativa de reintento.

Reversión selectiva: con la especialidad sin trabajo activo, retirar su manifest `tools/specialized/<repositorio>.json` la deja no disponible. Retirar después solo sus fuentes/runtime privados si se desea liberar disco. No borrar proyectos, tableros, credenciales ni herramientas compartidas. No modificar pins o marcar `validated` manualmente: ejecutar el validador y repetir las pruebas de integración tras un cambio.

LearnHarness no se instala ni anuncia como operativo. Su evaluación está en el informe; necesita una decisión separada sobre su aplicación, proveedor y persistencia. Tampoco se habilitan FEA, impresoras, fabricación, servidores MCP upstream, cuentas o acceso a red por instalar estas skills.
