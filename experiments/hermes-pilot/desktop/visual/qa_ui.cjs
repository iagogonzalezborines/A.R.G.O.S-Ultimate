const fs=require('node:fs'),cp=require('node:child_process'),path=require('node:path');
const P=path.resolve(__dirname,'../..'),U=P+'/ui-workbench',T=process.env.HOME+'/.local/share/argos-desktop/visual-1';
if(!P.startsWith('/tmp/argos-desktop-qa/'))throw Error('Use a disposable QA installation');
const out=P+'/reports/visual-ui';fs.mkdirSync(out,{recursive:true});const report={checks:[],turns:[],errors:[],host_input:false};
function check(name,ok){report.checks.push({name,ok});console.log(name,ok);if(!ok)throw Error(name)}
const {_electron:electron}=require(P+'/source/node_modules/playwright');
const home=fs.mkdtempSync('/tmp/argos-ui-seat-');fs.mkdirSync(home+'/run',{mode:0o700});fs.mkdirSync(home+'/private',{mode:0o700});
fs.writeFileSync(home+'/sway.conf','xwayland disable\noutput HEADLESS-1 resolution 1600x1000\nseat seat0 fallback true\nfont monospace 12\ndefault_border pixel 0\n');
const env={PATH:'/usr/bin:/bin',LANG:'C.UTF-8',HOME:'/home/qa',XDG_RUNTIME_DIR:'/run/qa',WLR_BACKENDS:'headless',WLR_RENDERER:'pixman',WLR_HEADLESS_OUTPUTS:'1',SWAYSOCK:'/run/qa/ipc.sock',LD_LIBRARY_PATH:'/opt/visual/usr/lib'};
const args=['--unshare-all','--die-with-parent','--new-session','--ro-bind','/usr','/usr','--symlink','usr/lib','/lib','--symlink','usr/lib','/lib64','--symlink','usr/bin','/bin','--dev','/dev','--proc','/proc','--tmpfs','/tmp','--ro-bind','/etc/fonts','/etc/fonts','--ro-bind','/etc/ld.so.cache','/etc/ld.so.cache','--ro-bind',T,'/opt/visual','--bind',home+'/run','/run/qa','--bind',home+'/private','/home/qa','--ro-bind',home+'/sway.conf','/etc/sway/config','--','/opt/visual/usr/bin/sway','--unsupported-gpu','-c','/etc/sway/config'];
const seat=cp.spawn('/usr/bin/bwrap',args,{env,detached:true,stdio:'ignore'});let host,app;const pause=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{try{
 for(let i=0;i<100&&!fs.existsSync(home+'/run/wayland-1');i++)await pause(50);
 host=cp.spawn('/usr/bin/python3',[U+'/server.py','--text-only','--no-capture','--mute-playback','--port','42724','--session','argos-visual-qa-'+Date.now()],{stdio:['ignore',fs.openSync('/tmp/argos-visual-host.log','a'),fs.openSync('/tmp/argos-visual-host.log','a')]});
 for(let i=0;i<100;i++){try{if((await(await fetch('http://127.0.0.1:42724/health')).json()).agent_connected)break}catch{}await pause(500)}
 console.log('launching',home);
 app=await electron.launch({executablePath:P+'/source/node_modules/electron/dist/electron',args:['--ozone-platform=wayland',U+'/desktop/main.cjs'],env:{HOME:home+'/private',PATH:'/usr/bin:/bin',LANG:'C.UTF-8',ARGOS_UI_QA:'1',ARGOS_UI_ORIGIN:'http://127.0.0.1:42724',XDG_RUNTIME_DIR:home+'/run',WAYLAND_DISPLAY:'wayland-1'}});
 const page=await app.firstWindow();await page.waitForFunction(()=>window.ARGOSWorkspace);await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].setFullScreen(true));
 page.on('pageerror',e=>report.errors.push(String(e)));
 const call=arguments_=>page.evaluate(arguments_=>window.argosDesktop.capability({tool:'desktop',arguments:arguments_}),arguments_);
 await page.evaluate(()=>{window.__answers=[];window.argosDesktop.onRuntimeEvent(e=>{if(e.type==='voice.answer')window.__answers.push(e.text)})});
 async function send(text){await page.evaluate(()=>window.ARGOSWorkspace.openPanel('conversation'));const before=await page.evaluate(()=>window.__answers.length);await page.getByLabel('Mensaje para ARGOS',{exact:true}).fill(text);await page.getByRole('button',{name:'Enviar',exact:true}).click();await page.waitForFunction(n=>window.__answers.length>n,before,{timeout:150000});const answer=await page.evaluate(()=>window.__answers.at(-1));report.turns.push({request:text,answer});console.log('General:',answer);return answer}
 await page.locator('#core-button').click();await page.getByRole('button',{name:'Control de aplicaciones'}).click();
 const panel=page.locator('[data-kind="desktop"]');await panel.getByRole('button',{name:'Abrir lienzo visual aislado'}).waitFor();
 check('visual session discoverable in real application',true);
 await panel.getByRole('button',{name:'Abrir lienzo visual aislado'}).click();
 const review=page.locator('[data-kind="change"]').last();await review.getByText(/Autorizar captura, clic/).waitFor();
 check('scope review precedes launch',(await call({action:'status'})).scopes.length===0);await review.screenshot({path:out+'/scope-review.png'});
 await review.getByRole('button',{name:'Aplicar cambio',exact:true}).click();await page.waitForFunction(()=>!document.querySelector('[data-kind="change"]'),null,{timeout:15000});
 await panel.getByRole('button',{name:'Actualizar ventanas'}).click();await panel.getByRole('button',{name:'Reabrir acceso · Visual · pad'}).click();await panel.locator('.desktop-visual-image').waitFor();
 const img=panel.locator('.desktop-visual-image');const rect=await img.boundingBox();await img.click({position:{x:rect.width*.1,y:rect.height*120/700}});
 await pause(500);await panel.getByLabel('Texto para la sesión aislada').fill('Texto desde interfaz');await panel.getByRole('button',{name:'Escribir en el campo enfocado'}).click();await pause(500);
 const scopes=(await call({action:'status'})).scopes;const scope=scopes.find(s=>s.application==='isolated-visual').scope;
 const config=JSON.parse(fs.readFileSync(P+'/installation.json'));const state=()=>JSON.parse(fs.readFileSync(path.join(config.desktop.state,scope,'work/result.json')));
 check('UI screenshot click and text reach real canvas',state().text==='Texto desde interfaz');
 await panel.getByRole('button',{name:'Cerrar',exact:true}).click();await page.evaluate(()=>window.ARGOSWorkspace.openPanel('desktop'));await panel.getByRole('button',{name:'Reabrir acceso · Visual · pad'}).click();check('panel reopening preserves isolated scope',(await call({action:'status'})).scopes.some(s=>s.scope===scope));
 await panel.locator('.desktop-visual-image').waitFor();await panel.screenshot({path:out+'/canvas-ui.png'});
 // General sees actual pixels through MCP; no coordinates are supplied in the request.
 await send('En el lienzo visual aislado que ya he autorizado, observa la captura. Sustituye el texto de Draft por "Prueba visual natural", pulsa Apply draft, desplaza la lista hacia abajo y arrastra la tarjeta azul MODEL.STL a DROP HERE. Usa desktop visual_act, verifica con otra captura y dime lo que observas. No abras otras aplicaciones.');
 const actual=state();report.canvas=actual;check('General visual loop changes real application',actual.applied==='Prueba visual natural'&&actual.scroll>0&&actual.dropped);
 await page.evaluate(()=>window.ARGOSWorkspace.clear());await page.evaluate(()=>window.ARGOSWorkspace.openPanel('desktop'));await panel.getByRole('button',{name:'Reabrir acceso · Visual · pad'}).click();await panel.locator('.desktop-visual-image').waitFor();await panel.screenshot({path:out+'/natural-verified.png'});
 const panelId=await panel.getAttribute('data-window');await page.evaluate(id=>window.ARGOSWorkspace.apply({type:'window.move',id,width:390,height:700}),panelId);await pause(200);check('narrow visual panel contains its screenshot',await panel.evaluate(el=>{const image=el.querySelector('img');return image.getBoundingClientRect().right<=el.getBoundingClientRect().right}));await panel.screenshot({path:out+'/narrow.png'});await page.evaluate(id=>window.ARGOSWorkspace.apply({type:'window.move',id,width:780,height:700}),panelId);
 let view=await call({action:'observe',scope});let job=await call({action:'visual_act',scope,snapshot:view.snapshot,actions:[{type:'drag',x:720,y:460,to_x:800,to_y:500,duration_ms:3000}]});check('background job returns promptly',job.state==='running');
 await panel.getByRole('button',{name:'Cerrar',exact:true}).click();check('panel close does not cancel active job',(await call({action:'status',job:job.id})).state==='running');await page.evaluate(()=>window.ARGOSWorkspace.openPanel('desktop'));await panel.getByText('Trabajo en curso. Puedes detenerlo o volver a observar cuando termine.').waitFor();check('reopening busy panel preserves stop control',await panel.getByRole('button',{name:'Detener acciones'}).isEnabled());
 const start=performance.now();await page.evaluate(()=>window.argosDesktop.capability({tool:'apps',arguments:{action:'list'}}));report.apps_ms=performance.now()-start;check('applications remain responsive during visual work',report.apps_ms<1000);
 await send('Mientras trabajas, dime brevemente qué es una carpeta. No uses herramientas.');
 check('conversation remains available',report.turns.at(-1).answer.length>0);
 while((await call({action:'status'})).state==='running')await pause(100);
 await page.evaluate(()=>window.ARGOSWorkspace.clear());await page.evaluate(()=>window.ARGOSWorkspace.openPanel('desktop'));await panel.getByRole('button',{name:'Reabrir acceso · Visual · pad'}).click();
 view=await call({action:'observe',scope});job=await call({action:'visual_act',scope,snapshot:view.snapshot,actions:[{type:'drag',x:800,y:500,to_x:100,to_y:350,duration_ms:3000}]});await panel.getByRole('button',{name:'Detener acciones'}).click();await pause(350);const cancelled=await call({action:'status',job:job.id});check('UI stop releases held input',cancelled.state==='cancelled'&&cancelled.held_input_released);
 await panel.getByRole('button',{name:'Observar de nuevo'}).click();await panel.locator('.desktop-visual-image').waitFor();await panel.screenshot({path:out+'/cancelled.png'});
 await panel.getByRole('button',{name:'Retirar acceso',exact:true}).click();check('UI revocation destroys private scope',!(await call({action:'status'})).scopes.some(s=>s.scope===scope));
 // A separate native comparison uses the real ARGOS file policy and temporary copies.
 const left=path.join(config.user_home,'visual-left.txt'),right=path.join(config.user_home,'visual-right.txt');fs.writeFileSync(left,'Original left\n');fs.writeFileSync(right,'Original right\n');
 await call({action:'visual_open',application:'comparison',left,right});const comparisonReview=page.locator('[data-kind="change"]').last();await comparisonReview.getByRole('button',{name:'Aplicar cambio',exact:true}).click();await page.waitForFunction(()=>!document.querySelector('[data-kind="change"]'),null,{timeout:15000});
 const compare=(await call({action:'status'})).scopes.find(s=>s.application==='isolated-visual');check('real Broker admits comparison of authorized files',!!compare);await call({action:'release',scope:compare.scope});check('comparison preserves originals',fs.readFileSync(left,'utf8')==='Original left\n');
 check('no renderer errors',report.errors.length===0);

 }catch(e){report.failure=String(e);console.error(e);process.exitCode=1;if(app)try{await(await app.firstWindow()).screenshot({path:out+'/failure.png'})}catch{}}finally{fs.writeFileSync(out+'/ui.json',JSON.stringify(report,null,2));if(app)await app.close();if(host){host.kill('SIGTERM');await pause(1000)}try{process.kill(-seat.pid,'SIGTERM')}catch{}}
})();
