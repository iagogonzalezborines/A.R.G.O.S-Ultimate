// Real Electron, General, Broker and native AT-SPI; disposable data, explicit QA run.
const fs=require('node:fs'),path=require('node:path'),cp=require('node:child_process');
const P=path.resolve(__dirname,'..'),U=path.join(P,'ui-workbench');
if(!P.startsWith('/tmp/argos-desktop-qa/'))throw Error('Prepared disposable installation required');
const out=path.join(P,'reports/background-ui');fs.mkdirSync(out,{recursive:true});
const {_electron:electron}=require(path.join(P,'source/node_modules/playwright'));
const pause=ms=>new Promise(r=>setTimeout(r,ms));const report={checks:[],renderer_errors:[],audio:false};let host,app,page,fixture;
function check(name,ok){report.checks.push({name,ok});console.log(name,ok);if(!ok)throw Error(name)}
(async()=>{try{
 const env={...process.env,NO_AT_BRIDGE:'0',GDK_BACKEND:'wayland',GTK_MODULES:'gail:atk-bridge'};
 fixture=cp.spawn('/usr/bin/python3',[path.join(P,'desktop/qa_semantic_app.py'),path.join(out,'target')],{env,stdio:'ignore'});
 host=cp.spawn('/usr/bin/python3',[path.join(U,'server.py'),'--text-only','--no-capture','--mute-playback','--port','42724','--session','argos-background-window-qa'],{stdio:['ignore',fs.openSync(path.join(out,'host.log'),'a'),fs.openSync(path.join(out,'host.log'),'a')]});
 for(let i=0;i<75;i++){try{if((await(await fetch('http://127.0.0.1:42724/health')).json()).agent_connected)break}catch{}await pause(1000)}
 const uiEnv={HOME:path.join(U,'state/home'),PATH:'/usr/bin:/bin',LANG:'C.UTF-8',ARGOS_UI_QA:'1',ARGOS_UI_PLATFORM:'x11',ARGOS_UI_ORIGIN:'http://127.0.0.1:42724'};for(const k of ['DISPLAY','XDG_RUNTIME_DIR','DBUS_SESSION_BUS_ADDRESS'])if(process.env[k])uiEnv[k]=process.env[k];
 app=await electron.launch({executablePath:path.join(P,'source/node_modules/electron/dist/electron'),args:[path.join(U,'desktop/main.cjs')],env:uiEnv});page=await app.firstWindow();page.on('pageerror',e=>report.renderer_errors.push(String(e)));await page.waitForFunction(()=>window.ARGOSWorkspace);
 await page.evaluate(()=>window.argosDesktop.fullscreen());await pause(700);
 await page.locator('#core-button').click();await page.getByRole('button',{name:'Control de aplicaciones'}).click();
 const panel=page.locator('[data-kind="desktop"]');await panel.getByText('Selecciona una ventana para autorizar su lectura.').waitFor();
 const row=panel.locator('.desktop-control-row').filter({hasText:'ARGOS desktop isolation fixture target'});await row.getByRole('button',{name:'Autorizar lectura',exact:true}).click();
 await panel.getByLabel('Texto de Draft',{exact:true}).waitFor();check('menu discovers and authorizes real window',await panel.getByLabel('Texto de Draft',{exact:true}).inputValue()==='Initial draft');
 const before=JSON.parse(fs.readFileSync(path.join(out,'target/events.json')));
 await panel.getByLabel('Texto de Draft',{exact:true}).fill('Borrador desde la interfaz');await panel.getByRole('button',{name:'Revisar texto',exact:true}).click();
 const review=page.locator('[data-kind="change"]').last();await review.getByText('Autorizar operación de escritorio',{exact:true}).waitFor();
 check('review does not mutate native text',JSON.parse(fs.readFileSync(path.join(out,'target/events.json'))).text===before.text);
 await page.evaluate(()=>window.ARGOSWorkspace.apply({type:'workspace.arrange'}));await pause(650);
 await page.screenshot({path:path.join(out,'review.png')});
 await review.getByRole('button',{name:'Aplicar cambio',exact:true}).click();
 const call=arguments_=>page.evaluate(arguments_=>window.argosDesktop.capability({tool:'desktop',arguments:arguments_}),arguments_);
 for(let i=0;i<60;i++){const status=await call({action:'status'});if(status.state==='idle')break;await pause(100)}
 await panel.getByRole('button',{name:'Observar de nuevo',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('.desktop-field')?.value==='Borrador desde la interfaz');
 check('trusted UI applies and verifies actual native field',JSON.parse(fs.readFileSync(path.join(out,'target/events.json'))).text==='Borrador desde la interfaz');
 await panel.getByRole('button',{name:'Cerrar',exact:true}).click();await page.evaluate(()=>window.ARGOSWorkspace.openPanel('desktop'));
 check('closing panel retains authorized scope',(await call({action:'status'})).scopes.some(s=>s.application==='accessible-window'));
 if(process.env.ARGOS_QA_SKIP_GENERAL==='1'){
  await panel.getByRole('button',{name:'Reabrir acceso · ARGOS desktop isolation fixture target',exact:true}).click();await pause(650);
  await page.screenshot({path:path.join(out,'verified-interface.png')});
  await panel.getByRole('button',{name:'Maximizar',exact:true}).click();
  await app.evaluate(({BrowserWindow})=>{const win=BrowserWindow.getAllWindows()[0];win.setFullScreen(false);win.setBounds({width:600,height:700})});await pause(700);
  check('narrow panel contains its form',await panel.evaluate(el=>{const box=el.getBoundingClientRect();return box.right<=innerWidth&&box.left>=0&&el.querySelector('.desktop-field').clientWidth>150}));
  await page.screenshot({path:path.join(out,'narrow.png')});
  fixture.kill('SIGTERM');await pause(200);await panel.getByRole('button',{name:'Observar de nuevo',exact:true}).click();
  await panel.getByText(/aplicación se ha cerrado|Application closed|identity|changed|gone/).waitFor({timeout:5000});
  check('closed application produces visible error',true);
  await page.screenshot({path:path.join(out,'closed.png')});
  check('no renderer errors',report.renderer_errors.length===0);return;
 }
 // General naturally resolves the authorized scope and proposes the concrete edit.
 await page.evaluate(()=>{window.__answers=[];window.argosDesktop.onRuntimeEvent(e=>{if(e.type==='voice.answer')window.__answers.push(e.text)});window.ARGOSWorkspace.openPanel('conversation')});
 await page.getByLabel('Mensaje para ARGOS',{exact:true}).fill('En la ventana de prueba que ya he autorizado, sustituye el campo Draft por "Borrador natural de ARGOS". Usa la herramienta desktop y prepara la revisión de texto; no pulses Apply draft.');await page.getByRole('button',{name:'Enviar',exact:true}).click();
 await page.waitForFunction(()=>window.__answers.length>0,null,{timeout:120000});report.answer=await page.evaluate(()=>window.__answers.at(-1));
 const naturalReview=page.locator('[data-kind="change"]').last();await naturalReview.getByText(/Reemplazar el texto por:\s*Borrador natural de ARGOS/).waitFor({timeout:15000});
 check('natural request reaches desktop review',true);await naturalReview.getByRole('button',{name:'Aplicar cambio',exact:true}).click();
 for(let i=0;i<60;i++){if(JSON.parse(fs.readFileSync(path.join(out,'target/events.json'))).text==='Borrador natural de ARGOS')break;await pause(100)}
 check('natural request produces real verified artifact',JSON.parse(fs.readFileSync(path.join(out,'target/events.json'))).text==='Borrador natural de ARGOS');
 check('drafting did not activate Apply draft',JSON.parse(fs.readFileSync(path.join(out,'target/events.json'))).applied===0);
 await page.evaluate(()=>window.ARGOSWorkspace.clear());
 await page.evaluate(()=>window.ARGOSWorkspace.openPanel('desktop'));await pause(250);
 await panel.getByRole('button',{name:'Reabrir acceso · ARGOS desktop isolation fixture target',exact:true}).click();await panel.getByLabel('Texto de Draft',{exact:true}).waitFor();
 await page.screenshot({path:path.join(out,'verified.png')});
 const size=await page.evaluate(()=>({width:innerWidth,height:innerHeight,scrollX,scrollY}));report.geometry=size;check('no document layout overflow',size.scrollX===0&&size.scrollY===0);
 await panel.getByRole('button',{name:'Retirar acceso',exact:true}).click();check('revoking does not close user application',fixture.exitCode===null);
 check('no renderer errors',report.renderer_errors.length===0);
 }catch(e){report.failure=String(e);console.error(e);process.exitCode=1;try{await page.screenshot({path:path.join(out,'failure.png')})}catch{}}
 finally{fs.writeFileSync(path.join(out,'ui.json'),JSON.stringify(report,null,2));if(app)await app.close();if(host){host.kill('SIGTERM');await pause(1500)}if(fixture)fixture.kill('SIGTERM')}
})();
