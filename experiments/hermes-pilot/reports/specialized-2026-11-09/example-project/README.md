# Artefactos explicativos de especialidades

Fuentes editables y exportaciones locales de diagramas e ilustraciones. Los diagramas son explicativos; no son autoridad de estado. Las medidas CAD describen un diseño paramétrico y no implican fabricación ni certificación mecánica. Flujo offline: no requiere red ni hardware externo.

Defina la raíz de la instalación local (en esta ejecución):

```sh
export ARGOS_SPECIALIZED_ROOT="${ARGOS_SPECIALIZED_ROOT:-$HOME/.local/share/argos-hermes-pilot/tools/specialized}"
```

## Arquitectura (Archify)

```sh
node "$ARGOS_SPECIALIZED_ROOT/archify/archify/renderers/architecture/render-architecture.mjs" architecture.json architecture.html
node "$ARGOS_SPECIALIZED_ROOT/archify/archify/scripts/check-render-output.mjs" architecture.html
```

El render directo conserva `architecture.json`; el checker confirma estructura y composición, no revisión visual. No usar `deliver` ni `finalize` para esta reproducción.

## Comparador de referencias (Anatomy)

```sh
node comparador-referencias.mjs
node comparador-referencias.mjs --light
```

Genera `comparador-referencias.html` en esta carpeta, importando el kit de Anatomy bajo `$ARGOS_SPECIALIZED_ROOT/anatomy`.

## Soporte CAD

```sh
PYTHONPATH="$ARGOS_SPECIALIZED_ROOT/text-to-cad/packages/cad/src" \
  "$ARGOS_SPECIALIZED_ROOT/cad-env/bin/python" bracket.py
```

Exporta `bracket.step`, `bracket.stl` y `medidas.json`; el script inspecciona el sólido y reabre STEP para comparar geometría. Estas comprobaciones no son análisis de cargas ni certificación.

## Objeto Blender

```sh
"$ARGOS_SPECIALIZED_ROOT/blender-5.2.3-linux-x64/blender" \
  --background --factory-startup --disable-autoexec --threads 2 \
  --python-exit-code 1 --python sculpture.py
```

Genera `sculpture.blend`, `sculpture.glb` y `preview.png` con render CPU. El render es una vista previa, no evaluación física.

## Límites y licencias

Sin red, control de hardware, fabricación ni certificación mecánica. Avisos de Anatomy y Archify en [LICENSES](LICENSES/).
