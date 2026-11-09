"""Read-only model presentation. STEP tessellation runs in the existing sandbox."""
import base64,hashlib,json,os,resource,signal,subprocess,tempfile
from pathlib import Path


def step_mesh(data):
    from adaptive.specialized import context,ROOT
    from maintenance.controller import validation_sandbox
    context('cad.parametric')  # Do not execute a missing/unvalidated or changed toolchain.
    script="from build123d import import_step,export_stl; import base64; s=import_step('/workspace/input.step'); export_stl(s,'/tmp/view.stl',tolerance=0.1,angular_tolerance=0.2); print('ARGOS_STL:'+base64.b64encode(open('/tmp/view.stl','rb').read()).decode())"
    pilot=Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='argos-step-preview-') as d,tempfile.TemporaryFile() as output:
        root=Path(d);(root/'input.step').write_bytes(data)
        cmd=validation_sandbox(root,[str(ROOT/'cad-env/bin/python'),'-B','-c',script]);at=cmd.index('--');cmd[at:at]=['--ro-bind',str(pilot/'tools'),str(pilot/'tools'),'--ro-bind',str((pilot/'tools').resolve()),str((pilot/'tools').resolve()),'--setenv','OPENBLAS_NUM_THREADS','1','--setenv','OMP_NUM_THREADS','1']
        def limits():
            resource.setrlimit(resource.RLIMIT_CPU,(15,15));resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3));resource.setrlimit(resource.RLIMIT_FSIZE,(12*1024**2,12*1024**2))
        child=subprocess.Popen(cmd,stdout=output,stderr=output,start_new_session=True,preexec_fn=limits)
        try:code=child.wait(timeout=18)
        except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait();raise ValueError('STEP preview exceeded its time budget')
        output.seek(0);value=output.read(12*1024**2).decode('ascii','replace');line=next((l[10:] for l in value.splitlines() if l.startswith('ARGOS_STL:')),None)
        if code or not line:raise ValueError('STEP tessellation unavailable; source preserved')
        mesh=base64.b64decode(line,validate=True)
        if len(mesh)>8*1024**2:raise ValueError('STEP preview too large')
        return mesh


def html(data,suffix):
    if suffix in {'.step','.stp'}:data=step_mesh(data);suffix='.step'
    payload={'format':'glb' if suffix=='.glb' else 'stl','units':'m (glTF)' if suffix=='.glb' else 'mm (STEP)' if suffix=='.step' else 'unidades del archivo (STL no declara unidades)','data':base64.b64encode(data).decode()}
    bundle=(Path(__file__).resolve().parents[1]/'ui-workbench/viewer/model.bundle.js').read_text()
    return '''<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>html,body{height:100%;margin:0;background:#040c17;color:#d1e7f6;font:14px system-ui}body{display:flex;flex-direction:column}header,footer{padding:10px;display:flex;gap:8px;flex-wrap:wrap;border-bottom:1px solid #235471}button{background:#092237;color:#aee4ff;border:1px solid #31627b;border-radius:5px;padding:7px}button:focus-visible{outline:2px solid #7fe1ff}#model{flex:1;min-height:140px;overflow:hidden;background:radial-gradient(ellipse,#0c2538,#030a12)}#model>svg,#model>canvas{display:block;touch-action:none}#status{font-size:12px;color:#9eb7ca}#dimensions{padding:0 12px}footer{border-top:1px solid #235471}</style><header><button data-view="iso">Isométrica</button><button data-view="front">Frontal</button><button data-view="top">Superior</button><button data-view="side">Lateral</button><button id="mode">Vista holográfica</button><button id="animate" disabled>Animación</button></header><p id="dimensions"></p><div id="model"></div><footer id="status" role="status">Preparando geometría…</footer><script id="model-data" type="application/json">'''+json.dumps(payload)+'''</script><script>'''+bundle.replace('</script','<\\/script')+'</script></html>'
