from build123d import Box, export_step, export_stl, import_step
from cad.build123d import is_sound, mass_properties, topology_errors
import json
shape=Box(40,20,4)
assert is_sound(shape) and not topology_errors(shape)
assert abs(mass_properties([(s,1.0) for s in shape.solids()]).volume-3200)<1e-5
export_step(shape,"part.step");export_stl(shape,"part.stl")
reopened=import_step("part.step")
assert abs(reopened.volume-3200)<1e-5
print(json.dumps({"volume_mm3":reopened.volume,"dimensions_mm":list(reopened.bounding_box().size)}))
