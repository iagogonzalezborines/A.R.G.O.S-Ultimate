// Real Electron + native registry: no renderer/backend mocks. No audio or Codex execution.
const path=require('node:path'),fs=require('node:fs'),cp=require('node:child_process');
const P=path.resolve(__dirname,'..'),U=path.join(P,'ui-workbench'),root=process.argv[2],out=process.argv[3];
const {_electron:electron}=require(path.join(P,'source/node_modules/playwright'));
const report={checks:[],errors:[]};function check(name,ok){report.checks.push({name,ok});console.log(name,ok);if(!ok)throw Error(name)}
(async()=>{
 const env={HOME:path.join(U,'state/home'),PATH:'/usr/bin:/bin',LANG:'C.UTF-8',ARGOS_UI_QA:'1',ARGOS_UI_PLATFORM:'x11',ARGOS_UI_ORIGIN:'http://127.0.0.1:42722'};for(const k of ['DISPLAY','XDG_RUNTIME_DIR','DBUS_SESSION_BUS_ADDRESS'])if(process.env[k])env[k]=process.env[k];
 const app=await electron.launch({executablePath:path.join(P,'source/node_modules/electron/dist/electron'),args:[path.join(U,'desktop/main.cjs')],env});
 try{
  const page=await app.firstWindow();page.setDefaultTimeout(20000);page.on('pageerror',e=>report.errors.push(String(e)));await page.waitForFunction(()=>window.ARGOSWorkspace);
  const call=args=>page.evaluate(args=>window.argosDesktop.capability({tool:'projects',arguments:args}),args);
  await page.locator('#core-button').click();await page.getByRole('button',{name:'Proyectos 08'}).click();
  if(process.argv.includes('--disabled')){await page.getByText('Project Map no está habilitado en esta instalación.',{exact:true}).waitFor();await page.screenshot({path:path.join(out,'map-unavailable.png')});check('disabled installation explains unavailability',true);return;}
  await page.getByText(/No hay proyectos/).waitFor();await page.screenshot({path:path.join(out,'map-empty.png')});check('map discoverable and empty state',true);
  const proposal=await call({action:'propose',name:'Map Fixture',slug:'map-fixture',brief:{objective:'Observe real native decisions and dependency state'}});
  await page.getByRole('button',{name:'Aplicar cambio',exact:true}).click();await page.waitForFunction(()=>!document.querySelector('.file-review'));
  const p=await call({action:'resolve',project:(await call({action:'list'})).projects[0].id});
  const decision=await call({action:'task_create',project:p.id,expected_revision:p.revision,kind:'decision',title:'Formatos de archivo',goal:'Elegir formatos iniciales',verification:['Elección explícita']});
  const task=await call({action:'task_create',project:p.id,expected_revision:p.revision,title:'Crear índice',goal:'Indexar los formatos elegidos',verification:['Preservar originales'],parents:[decision.id]});
  await page.getByRole('button',{name:'Actualizar',exact:true}).click();await page.getByLabel('Proyecto',{exact:true}).selectOption(p.id);
  await page.locator(`[data-task="${decision.id}"]`).click();await page.getByLabel('Decisión o motivo').fill('STL y OBJ');await page.getByRole('button',{name:'Guardar decisión',exact:true}).click();await page.waitForFunction(id=>document.querySelector(`[data-task="${id}"]`)?.dataset.state==='done',decision.id);
  check('native decision saved from UI',(await call({action:'task',project:p.id,task_id:decision.id})).status==='done');
  await page.locator(`[data-task="${task.id}"]`).click();await page.getByText('Modificar tarea',{exact:true}).click();await page.getByLabel('Objetivo de tarea').fill('Indexar STL y OBJ sin mover originales');await page.getByRole('button',{name:'Guardar tarea',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('.project-detail')?.textContent.includes('Indexar STL y OBJ sin mover originales'));check('edit task persists actual native brief',(await call({action:'task',project:p.id,task_id:task.id})).body.includes('sin mover originales'));
  await page.screenshot({path:path.join(out,'map-dependencies.png')});
  await page.getByRole('button',{name:'Cancelar tarea',exact:true}).click();await page.waitForFunction(id=>document.querySelector(`[data-task="${id}"]`)?.dataset.state==='archived',task.id);check('native cancellation from UI',true);
  const panel=page.locator('[data-kind="project"]');await panel.getByRole('button',{name:'Cerrar',exact:true}).click();await page.evaluate(()=>window.ARGOSWorkspace.openPanel('project'));await page.waitForFunction(id=>document.querySelector(`[data-task="${id}"]`)?.dataset.state==='archived',task.id);check('close/reopen restores project and state',true);
  const review=await call({action:'task_create',project:p.id,expected_revision:p.revision,title:'Revisión controlada',goal:'Comprobar controles con un registro nativo de prueba',verification:['Prueba de interacción']});
  fs.writeFileSync(path.join(p.path,'test_review.py'),'import unittest\nclass Check(unittest.TestCase):\n def test_review(self): self.assertEqual(2+2,4)\n');
  const script="import sys\nfrom hermes_cli import kanban_db as kb\nfrom hermes_cli.kanban_db_connect import connect_closing\nwith connect_closing(board=sys.argv[1]) as c:\n kb.unblock_task(c,sys.argv[2])\n t=kb.claim_task(c,sys.argv[2])\n kb.request_review(c,t.id,summary='Controlled native fixture, not actual Engineering',expected_run_id=t.current_run_id)";
  cp.execFileSync(path.join(P,'env/bin/python'),['-c',script,p.board,review.id],{env:{HOME:path.join(root,'native/home'),PATH:'/usr/bin:/bin',HERMES_HOME:path.join(root,'native'),HERMES_KANBAN_HOME:path.join(root,'native'),PYTHONPATH:path.join(P,'source'),HERMES_QUIET:'1'}});
  await page.getByRole('button',{name:'Actualizar',exact:true}).click();await page.locator(`[data-task="${review.id}"]`).click();check('acceptance disabled before verification',await page.getByRole('button',{name:'Aceptar resultado',exact:true}).isDisabled());
  fs.writeFileSync(path.join(p.path,'test_review.py'),'import unittest\nclass Check(unittest.TestCase):\n def test_review(self): self.assertEqual(2+2,5)\n');
  await page.getByRole('button',{name:'Verificar artefactos',exact:true}).click();await page.getByText('Pruebas fallidas',{exact:true}).waitFor();check('failed verification keeps acceptance disabled',await page.getByRole('button',{name:'Aceptar resultado',exact:true}).isDisabled());await page.screenshot({path:path.join(out,'map-verification-failed.png')});
  fs.writeFileSync(path.join(p.path,'test_review.py'),'import unittest\nclass Check(unittest.TestCase):\n def test_review(self): self.assertEqual(2+2,4)\n');
  await page.getByRole('button',{name:'Verificar artefactos',exact:true}).click();await page.waitForFunction(()=>!Array.from(document.querySelectorAll('.project-detail button')).find(b=>b.textContent==='Aceptar resultado')?.disabled);check('verification enables acceptance',true);
  await page.getByLabel('Decisión o motivo').fill('Revisión controlada: revisar antes de aceptar');await page.getByRole('button',{name:'Rechazar resultado',exact:true}).click();await page.waitForFunction(id=>document.querySelector(`[data-task="${id}"]`)?.dataset.state==='blocked',review.id);await page.screenshot({path:path.join(out,'map-blocked.png')});check('rejection produces native blocked state',true);
  await page.getByRole('button',{name:'Autorizar un reintento',exact:true}).click();await page.getByText('Missing or oversized text',{exact:false}).waitFor();check('invalid action explains failure without changing state',(await call({action:'task',project:p.id,task_id:review.id})).status==='blocked');
  await page.getByLabel('Decisión o motivo').fill('Inspeccioné los archivos; autorizo un intento');await page.getByRole('button',{name:'Autorizar un reintento',exact:true}).click();await page.getByRole('button',{name:'Iniciar Engineering',exact:true}).waitFor();check('retry grant does not replay work',(await call({action:'task',project:p.id,task_id:review.id})).runs.filter(r=>r.kind==='execution').length===1);
  check('selected task/project are exposed as bounded conversation context',await page.evaluate(({project,task})=>window.ARGOSWorkspace.snapshot().some(w=>w.kind==='project'&&w.project===project&&w.task_id===task),{project:p.id,task:review.id}));
  await page.getByRole('button',{name:'Cancelar tarea',exact:true}).click();await page.waitForFunction(id=>document.querySelector(`[data-task="${id}"]`)?.dataset.state==='archived',review.id);
  await page.evaluate(()=>window.ARGOSWorkspace.apply({type:'window.move',id:'project-map',width:380,height:500}));await page.screenshot({path:path.join(out,'map-narrow.png')});
  check('narrow layout has no horizontal overflow',await page.locator('.project-map').evaluate(e=>e.scrollWidth<=e.clientWidth+2));
  await page.evaluate(()=>window.ARGOSWorkspace.openPanel('browser',{id:'regression-browser',url:'https://example.com/',title:'Navegación de prueba'}));
  await page.waitForFunction(()=>document.querySelector('[data-window="regression-browser"] .preview-message')?.textContent==='Haz clic para interactuar');
  check('existing native HTTPS browser loads',await app.evaluate(({webContents})=>webContents.getAllWebContents().some(w=>w.getURL()==='https://example.com/')));
  await page.locator('[data-window="regression-browser"]').getByRole('button',{name:'Cerrar',exact:true}).click();check('closing browser preserves Project Map',await page.locator('.project-map').count()===1);
  check('desktop remains fixed while panels scroll',await page.evaluate(()=>scrollX===0&&scrollY===0));
  check('no renderer exceptions',report.errors.length===0);
 }finally{try{const p=await app.firstWindow();await p.screenshot({path:path.join(out,'map-last.png')});report.last=await p.locator('body').innerText()}catch{}await app.close();fs.writeFileSync(path.join(out,process.argv.includes('--disabled')?'map-unavailable.json':'map-ui.json'),JSON.stringify(report,null,2))}
})().catch(e=>{console.error(e);process.exitCode=1});
