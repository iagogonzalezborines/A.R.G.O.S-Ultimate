"""Controller-owned file integrity checks, run offline against a read-only project."""
import json
from pathlib import Path
import struct
import subprocess
import sys


def main():
    capability,paths_json,tool,tool_root=sys.argv[1:]
    files=[Path(p) for p in json.loads(paths_json)]
    assert files and all(p.is_file() and p.stat().st_size for p in files)
    by_suffix=lambda suffix:[p for p in files if p.suffix.lower()==suffix]
    measurements={}
    if capability.startswith('diagram.'):
        pages=by_suffix('.html');assert pages,'HTML missing'
        for path in pages:
            text=path.read_text();assert '<svg' in text and '<script' in text,'Interactive SVG missing'
        assert by_suffix('.json') if capability=='diagram.architecture' else by_suffix('.mjs'),'Editable source missing'
        if capability=='diagram.architecture':
            for path in pages:
                result=subprocess.run([tool,str(Path(tool_root)/'archify/archify/scripts/check-render-output.mjs'),str(path)],capture_output=True,text=True,timeout=15)
                assert result.returncode==0,result.stdout[-2000:]
        measurements={'html_count':len(pages),'check':'structure and Archify static checks where applicable; interaction requires browser inspection'}
    elif capability=='cad.parametric':
        from build123d import import_step
        from cad.build123d import is_sound,topology_errors
        assert by_suffix('.py') and by_suffix('.stl') and (by_suffix('.step') or by_suffix('.stp')),'CAD source/exports missing'
        for path in by_suffix('.step')+by_suffix('.stp'):
            shape=import_step(str(path));assert is_sound(shape) and not topology_errors(shape) and shape.volume>0
            measurements[str(path)]={'volume_mm3':shape.volume,'dimensions_mm':list(shape.bounding_box().size),'solids':len(shape.solids())}
        for path in by_suffix('.stl'):
            data=path.read_bytes();assert len(data)>84 and (len(data)==84+50*struct.unpack_from('<I',data,80)[0] or data.lstrip().startswith(b'solid')),'Invalid STL'
    elif capability=='design.blender':
        assert by_suffix('.py') and by_suffix('.blend') and by_suffix('.glb'),'Blender source/exports missing'
        for path in by_suffix('.blend'):
            # Auto-run is disabled, and no generated script is executed to verify the scene.
            code="import bpy,json; meshes=[o for o in bpy.data.objects if o.type=='MESH']; assert meshes and all(len(o.data.vertices)>0 for o in meshes); print('SCENE_VERIFIED',json.dumps([o.name for o in meshes]))"
            result=subprocess.run([tool,'--background','--factory-startup','--disable-autoexec',str(path),'--threads','2','--python-exit-code','1','--python-expr',code],capture_output=True,text=True,timeout=25)
            assert result.returncode==0 and 'SCENE_VERIFIED' in result.stdout,result.stdout[-1000:]
        for path in by_suffix('.glb'):
            data=path.read_bytes();assert data[:4]==b'glTF' and struct.unpack_from('<II',data,4)==(2,len(data)),'Invalid GLB'
        for path in by_suffix('.png'):assert path.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'),'Invalid preview'
        measurements={'scene':'reopened with auto-execution disabled','export':'GLB 2 header and size verified'}
    else:raise ValueError('Unsupported specialized verification')
    print('ARGOS_SPECIALIZED_INTEGRITY: '+json.dumps(measurements))
    print('Integrity only; compare measurements/visual output against task requirements before accepting. No mechanical certification.')


if __name__=='__main__':main()
