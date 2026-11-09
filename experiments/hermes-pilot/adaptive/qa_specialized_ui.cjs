const fs=require('node:fs'),cp=require('node:child_process'),path=require('node:path');
const P=path.resolve(__dirname,'..'),U=P+'/ui-workbench',T=process.env.HOME+'/.local/share/argos-desktop/visual-1';
if(!P.startsWith('/tmp/argos-desktop-qa/'))throw Error('Use a disposable QA installation');
const qaConfig=JSON.parse(fs.readFileSync(P+'/installation.json'));if(!qaConfig.projects_enabled||!qaConfig.project_map_enabled||!qaConfig.project_roots?.length||qaConfig.project_roots.some(p=>!path.resolve(p).startsWith('/tmp/argos-desktop-qa/home/'))||!path.resolve(qaConfig.project_state).startsWith(P+'/'))throw Error('QA project roots must be disposable and Projects enabled');
const out=P+'/reports/specialized-ui';fs.mkdirSync(out,{recursive:true});const report={checks:[],turns:[],errors:[],host_input:false};
function check(name,ok){report.checks.push({name,ok});console.log(name,ok);if(!ok)throw Error(name)}
const {_electron:electron}=require(P+'/source/node_modules/playwright');
const home=fs.mkdtempSync('/tmp/argos-ui-seat-');fs.mkdirSync(home+'/run',{mode:0o700});fs.mkdirSync(home+'/private',{mode:0o700});
fs.writeFileSync(home+'/sway.conf','xwayland disable\noutput HEADLESS-1 resolution 1600x1000\nseat seat0 fallback true\nfont monospace 12\ndefault_border pixel 0\n');
const env={PATH:'/usr/bin:/bin',LANG:'C.UTF-8',HOME:'/home/qa',XDG_RUNTIME_DIR:'/run/qa',WLR_BACKENDS:'headless',WLR_RENDERER:'pixman',WLR_HEADLESS_OUTPUTS:'1',SWAYSOCK:'/run/qa/ipc.sock',LD_LIBRARY_PATH:'/opt/visual/usr/lib'};
const args=['--unshare-all','--die-with-parent','--new-session','--ro-bind','/usr','/usr','--symlink','usr/lib','/lib','--symlink','usr/lib','/lib64','--symlink','usr/bin','/bin','--dev','/dev','--proc','/proc','--tmpfs','/tmp','--ro-bind','/etc/fonts','/etc/fonts','--ro-bind','/etc/ld.so.cache','/etc/ld.so.cache','--ro-bind',T,'/opt/visual','--bind',home+'/run','/run/qa','--bind',home+'/private','/home/qa','--ro-bind',home+'/sway.conf','/etc/sway/config','--','/opt/visual/usr/bin/sway','--unsupported-gpu','-c','/etc/sway/config'];
const seat=cp.spawn('/usr/bin/bwrap',args,{env,detached:true,stdio:'ignore'});let host,app;const pause=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{try{
 for(let i=0;i<100&&!fs.existsSync(home+'/run/wayland-1');i++)await pause(50);
 host=cp.spawn('/usr/bin/python3',[U+'/server.py','--text-only','--no-capture','--mute-playback','--port','42724','--session','argos-specialized-qa-'+Date.now()],{stdio:['ignore',fs.openSync('/tmp/argos-visual-host.log','a'),fs.openSync('/tmp/argos-visual-host.log','a')]});
 for(let i=0;i<100;i++){try{if((await(await fetch('http://127.0.0.1:42724/health')).json()).agent_connected)break}catch{}await pause(500)}
 console.log('launching',home);
 app=await electron.launch({executablePath:P+'/source/node_modules/electron/dist/electron',args:['--ozone-platform=wayland',U+'/desktop/main.cjs'],env:{HOME:home+'/private',PATH:'/usr/bin:/bin',LANG:'C.UTF-8',ARGOS_UI_QA:'1',ARGOS_UI_ORIGIN:'http://127.0.0.1:42724',XDG_RUNTIME_DIR:home+'/run',WAYLAND_DISPLAY:'wayland-1'}});
 const page=await app.firstWindow();await page.waitForFunction(()=>window.ARGOSWorkspace);await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].setFullScreen(true));
 page.on('pageerror',e=>report.errors.push(String(e)));
 const call=(tool,arguments_)=>page.evaluate(({tool,arguments_})=>window.argosDesktop.capability({tool,arguments:arguments_}),{tool,arguments_});
 await page.evaluate(()=>{window.__answers=[];window.argosDesktop.onRuntimeEvent(e=>{if(e.type==='voice.answer')window.__answers.push(e.text)})});
 async function send(text){const started=performance.now();await page.evaluate(()=>window.ARGOSWorkspace.openPanel('conversation'));const before=await page.evaluate(()=>window.__answers.length);await page.getByLabel('Mensaje para ARGOS',{exact:true}).fill(text);await page.getByRole('button',{name:'Enviar',exact:true}).click();await page.waitForFunction(n=>window.__answers.length>n,before,{timeout:180000});const answer=await page.evaluate(()=>window.__answers.at(-1));report.turns.push({request:text,answer,seconds:(performance.now()-started)/1000});console.log('General:',answer);return answer}
 const name='Especialidades ARGOS '+Date.now();const proposal=await call('projects',{action:'propose',name,brief:{objective:'Demostrar artefactos técnicos persistentes aislados',requirements:['Guardar fuentes editables y exportaciones en este proyecto','Trabajar sin red ni hardware'],decisions:['Diagramas explicativos, no autoridad de estado','Sin fabricación ni certificación mecánica'],verification:['Abrir y verificar los artefactos reales']}});
 const project=(await call('projects',{action:'confirm',proposal_id:proposal.id,approve:true})).project;report.project=project;await page.evaluate(()=>window.ARGOSWorkspace.clear());
 const requests=[
 ['diagram.architecture','Genera un diagrama interactivo pequeño del flujo de este proyecto: petición, requisitos, tarea, Engineering y revisión. Usa sus registros nativos y distingue la representación explicativa de su estado real. Guarda architecture.json y architecture.html; verifica la entrega estática.'],
 ['diagram.technical','Crea una explicación técnica interactiva pequeña de un comparador de carátula y tres bloques de referencia. Adapta el ejemplo del kit instalado, conserva el script editable y el HTML autónomo dentro del proyecto. Explica que es una ilustración, no una simulación mecánica.'],
 ['cad.parametric','Diseña un soporte paramétrico en L: base 40 por 30 mm, altura total 24 mm, espesor 4 mm, sin agujeros. Guarda bracket.py con función build(), bracket.step, bracket.stl y medidas.json. Usa la inspección geométrica de la biblioteca instalada, comprueba sólido válido, dimensiones 40 por 30 por 24 y volumen 7200 mm3; reabre STEP y verifica. Sin impresión ni certificación mecánica.'],
 ['design.blender','Modela un objeto decorativo azul sencillo en Blender. Guarda sculpture.py, sculpture.blend editable, sculpture.glb y preview.png de 320 por 240 píxeles con Cycles CPU y 4 muestras. Usa un solo objeto malla, cámara y luz. Verifica reabriendo la escena; sin GPU, addons ni servicios.']
 ];report.tasks=[];
 for(const [capability,request] of requests){
  const previous=(await call('projects',{action:'tasks',project:project.id})).tasks.map(t=>t.id);
  await send('En el proyecto «'+name+'», realiza ahora este trabajo autorizado mediante Engineering: '+request+' Crea una sola tarea especializada, despáchala y responde sin esperar a que termine.');
  let tasks=(await call('projects',{action:'tasks',project:project.id})).tasks;let task=tasks.find(t=>!previous.includes(t.id));check('natural request creates '+capability,!!task);
  let detail=await call('projects',{action:'task',project:project.id,task_id:task.id});check('General selected registered '+capability,JSON.parse(detail.body.split('\n').slice(1).join('\n')).specialized?.id===capability);
  if(!detail.current_run_id&&['blocked','todo','ready'].includes(detail.status)){await send('El alcance del proyecto ya está autorizado. Inicia ahora la tarea que acabas de crear sin crear otra.');}
  const started=performance.now();const appStart=performance.now();await call('apps',{action:'list'});report.apps_ms=performance.now()-appStart;
  if(capability==='diagram.architecture')await send('Mientras trabaja Engineering, responde brevemente: ¿sigues disponible para conversar? No esperes a que termine.');
  while(performance.now()-started<390000){detail=await call('projects',{action:'task',project:project.id,task_id:task.id});if(!detail.current_run_id&&detail.runs?.length)break;await call('projects',{action:'tasks',project:project.id});await pause(3000)}
  report.tasks.push({capability,...detail});fs.writeFileSync(out+'/progress.json',JSON.stringify(report,null,2));console.log(capability,detail.status,JSON.stringify(detail.runs?.map(r=>({status:r.status,summary:r.summary}))));
  if(detail.status!=='review'){report.checks.push({name:'Engineering reaches review '+capability,ok:false});continue}
  check('real outputs '+capability,detail.artifacts.length>0);
  await page.evaluate(()=>window.ARGOSWorkspace.clear());await page.evaluate(project=>window.ARGOSWorkspace.openPanel('project',{text:project}),project.id);const map=page.locator('[data-kind="project"]');await map.locator('[data-task="'+task.id+'"]').click();
  const artifact=detail.artifacts.find(a=>a.path.endsWith('.html'))||detail.artifacts.find(a=>a.path.endsWith('.png'))||detail.artifacts.find(a=>a.path.endsWith('.py'));
  if(artifact){await map.getByRole('button',{name:artifact.path,exact:true}).click();await pause(1500);await map.screenshot({path:out+'/'+capability+'.png'});if(artifact.path.endsWith('.html')){const frame=map.locator('iframe').contentFrame();await frame.locator('svg').first().waitFor({timeout:15000});check('rendered interactive SVG '+capability,true);report.frames=report.frames||[];report.frames.push({capability,buttons:await frame.locator('button').allTextContents()});}}
 }
 check('no renderer errors',report.errors.length===0);
 }catch(e){report.failure=String(e);console.error(e);process.exitCode=1;if(app)try{await(await app.firstWindow()).screenshot({path:out+'/failure.png'})}catch{}}finally{fs.writeFileSync(out+'/ui.json',JSON.stringify(report,null,2));if(app)await app.close();if(host){host.kill('SIGTERM');await pause(1000)}try{process.kill(-seat.pid,'SIGTERM')}catch{}}
})();
