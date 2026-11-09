"""Parametric, unperforated L bracket. All dimensions are in millimetres."""

from pathlib import Path
import json

import build123d as bd
from cad.build123d import is_sound, mass_properties, topology_errors


# Editable design parameters.
BASE_LENGTH = 40.0
BASE_DEPTH = 30.0
TOTAL_HEIGHT = 24.0
THICKNESS = 4.0


def build(
    base_length: float = BASE_LENGTH,
    base_depth: float = BASE_DEPTH,
    total_height: float = TOTAL_HEIGHT,
    thickness: float = THICKNESS,
) -> bd.Part:
    """Return an L section extruded through base_depth, with its bottom at z=0."""
    if min(base_length, base_depth, total_height, thickness) <= 0:
        raise ValueError("All bracket dimensions must be positive")
    if thickness >= min(base_length, total_height):
        raise ValueError("Thickness must be smaller than length and height")

    # The two touching boxes form a constant L cross-section. Their union has
    # no overlap volume: 40*4*30 + 4*(24-4)*30 = 7200 mm^3.
    base = bd.Box(
        base_length, base_depth, thickness,
        align=(bd.Align.MIN, bd.Align.MIN, bd.Align.MIN),
    )
    upright = bd.Pos(0, 0, thickness) * bd.Box(
        thickness, base_depth, total_height - thickness,
        align=(bd.Align.MIN, bd.Align.MIN, bd.Align.MIN),
    )
    result = base + upright
    result.label = "L bracket"
    return result


def inspect(shape: bd.Shape) -> dict:
    """Measure geometry using build123d and the installed CAD inspection API."""
    solids = shape.solids()
    if len(solids) != 1:
        raise AssertionError(f"Expected one solid, got {len(solids)}")
    solid = solids[0]
    bounds = solid.bounding_box()
    size = bounds.size
    props = mass_properties([(solid, 1.0)])
    errors = topology_errors(solid)
    report = {
        "valid": bool(solid.is_valid),
        "sound": bool(is_sound(solid)),
        "topology_errors": [str(issue.code) for issue in errors],
        "solid_count": len(solids),
        "dimensions_mm": {"x": float(size.X), "y": float(size.Y), "z": float(size.Z)},
        "volume_mm3": float(props.volume),
        "holes": 0,
    }
    if not report["valid"] or not report["sound"] or errors:
        raise AssertionError(f"Invalid bracket geometry: {report}")
    return report


def export(output_dir: Path | str = ".") -> dict:
    """Build, inspect, export, reopen STEP, and persist observed measurements."""
    from build123d import export_step, export_stl, import_step

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    shape = build()
    before = inspect(shape)
    expected = {"x": BASE_LENGTH, "y": BASE_DEPTH, "z": TOTAL_HEIGHT}
    if before["dimensions_mm"] != expected or abs(before["volume_mm3"] - 7200.0) > 1e-6:
        raise AssertionError(f"Unexpected dimensions or volume: {before}")

    step_path = out / "bracket.step"
    stl_path = out / "bracket.stl"
    export_step(shape, str(step_path))
    export_stl(shape, str(stl_path))

    reopened = import_step(str(step_path))
    after = inspect(reopened)
    if after["dimensions_mm"] != expected or abs(after["volume_mm3"] - 7200.0) > 1e-6:
        raise AssertionError(f"STEP round-trip changed geometry: {after}")

    measurements = {
        "units": {"length": "mm", "volume": "mm^3"},
        "design_parameters": {
            "base_length": BASE_LENGTH,
            "base_depth": BASE_DEPTH,
            "total_height": TOTAL_HEIGHT,
            "thickness": THICKNESS,
            "holes": 0,
        },
        "model_inspection": before,
        "step_reopened_inspection": after,
        "verification": "CAD geometry inspection only; no fabrication or mechanical certification.",
    }
    (out / "medidas.json").write_text(json.dumps(measurements, indent=2) + "\n", encoding="utf-8")
    return measurements


if __name__ == "__main__":
    print(json.dumps(export(Path(__file__).resolve().parent), indent=2))
