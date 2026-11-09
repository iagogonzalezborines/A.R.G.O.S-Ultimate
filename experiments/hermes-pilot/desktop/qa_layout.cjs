// Real Electron/Wayland layout and progress check; no model, microphone or audio.
const fs=require('node:fs'),path=require('node:path'),cp=require('node:child_process');
const P=path.resolve(__dirname,'..'),U=path.join(P,'ui-workbench');
if(!P.startsWith('/tmp/argos-desktop-qa/'))throw Error('Use disposable desktop QA installation');
const {_electron:electron}=require(path.join(P,'source/node_modules/playwright'));
const pause=ms=>new Promise(r=>setTimeout(r,ms));let host,app,page;const report={checks:[],audio:false,model_turns:0};
function check(name,ok){report.checks.push({name,ok});console.log(name,ok);if(!ok)throw Error(name)}
(async()=>{try{
 host=cp.spawn('/usr/bin/python3',[path.join(U,'server.py'),'--port','42724'],{stdio:'ignore'});
 for(let n=0;n<50;n++){try{if((await fetch('http://127.0.0.1:42724/health')).ok)break}catch{}await pause(100)}
 const env={HOME:path.join(U,'state/home'),PATH:'/usr/bin:/bin',LANG:'C.UTF-8',ARGOS_UI_QA:'1',ARGOS_UI_PLATFORM:'x11',ARGOS_UI_ORIGIN:'http://127.0.0.1:42724'};for(const k of ['DISPLAY','XDG_RUNTIME_DIR','DBUS_SESSION_BUS_ADDRESS'])if(process.env[k])env[k]=process.env[k];
 app=await electron.launch({executablePath:path.join(P,'source/node_modules/electron/dist/electron'),args:[path.join(U,'desktop/main.cjs')],env});page=await app.firstWindow();await page.waitForFunction(()=>window.ARGOSWorkspace);
 const geometry=()=>page.evaluate(()=>({width:innerWidth,height:innerHeight,scrollX,scrollY}));
 await page.evaluate(()=>window.argosDesktop.fullscreen());await pause(800);
 const v=await page.evaluate(()=>window.argosDesktop.capability({tool:'apps',arguments:{action:'open',id:'calculator'}}));check('deterministic apps route opens verified calculator',v.window_verified&&v.name==='Calculadora');
 report.background_geometry=await geometry();
 await page.evaluate(()=>window.argosDesktop.fullscreen());await pause(800);report.restored_geometry=await geometry();
 check('one user gesture restores fullscreen after Wayland app launch',report.restored_geometry.width>=850&&report.restored_geometry.height>=620);
 const call=arguments_=>page.evaluate(arguments_=>window.argosDesktop.capability({tool:'desktop',arguments:arguments_}),arguments_);
 const fresh=await call({action:'observe',scope:v.scope});
 let job=await call({action:'act',scope:v.scope,snapshot:fresh.snapshot,buttons:['AC','1','2','+','2','5','=']});
 for(let i=0;i<160&&job.state==='running';i++){await pause(100);job=await call({action:'status',job:job.id})}
 check('real calculator result independently observed',job.state==='completed'&&job.result.texts[0].text==='37');
 report.action={state:job.state,buttons:job.buttons,steps:job.completed_steps,seconds:job.seconds,display:job.result.texts};
 const progress=page.locator('[data-kind="progress"]').last();await progress.getByText('7 / 7 acciones entregadas',{exact:true}).waitFor();
 check('desktop progress shows actual actions',await progress.getByText('7 / 7 acciones entregadas',{exact:true}).isVisible());
 check('desktop does not show research counters',!(await progress.innerText()).includes('seleccionadas'));
 await page.evaluate(()=>window.argosDesktop.capability({tool:'workspace',arguments:{action:'open',kind:'note',id:'desktop-observed-result',title:'Calculadora · verificación programática',text:'12 + 25 = 37\nResultado leído en la calculadora nativa mediante AT-SPI.\n7 acciones entregadas; sin entrada física global.'}}));
 await pause(750);await page.screenshot({path:path.join(P,'reports/desktop-live/desktop-verified.png')});
 check('desktop root does not scroll outside panels',(await geometry()).scrollX===0&&(await geometry()).scrollY===0);
 const partial=await call({action:'observe',scope:v.scope});let cancelled=await call({action:'act',scope:v.scope,snapshot:partial.snapshot,buttons:Array(16).fill('1')});await call({action:'cancel',job:cancelled.id});
 for(let i=0;i<60&&cancelled.state==='running';i++){await pause(100);cancelled=await call({action:'status',job:cancelled.id})}
 check('cancelled work is not presented as complete',cancelled.state==='cancelled');await pause(750);await page.screenshot({path:path.join(P,'reports/desktop-live/desktop-cancelled.png')});
 }catch(e){report.failure=String(e);console.error(e);process.exitCode=1}
 finally{fs.writeFileSync(path.join(P,'reports/desktop-live/layout-report.json'),JSON.stringify(report,null,2));if(app)await app.close();if(host){host.kill('SIGTERM');await pause(1000)}}
})();
