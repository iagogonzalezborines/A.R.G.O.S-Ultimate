const {_electron:electron}=require('../source/node_modules/playwright');
const fs=require('node:fs'),path=require('node:path');
const ROOT=__dirname,BASE='http://127.0.0.1:42721',report={checks:[],errors:[]};
function check(name,ok,detail){report.checks.push({name,ok,detail});console.log(name,ok);if(!ok)throw Error(name)}
(async()=>{
 const env={PATH:'/usr/bin:/bin',HOME:path.join(ROOT,'state/home'),LANG:'C.UTF-8',ARGOS_UI_QA:'1',ARGOS_UI_PLATFORM:'x11',ARGOS_UI_ORIGIN:BASE};
 for(const key of ['XDG_RUNTIME_DIR','DISPLAY','DBUS_SESSION_BUS_ADDRESS'])if(process.env[key])env[key]=process.env[key];
 const app=await electron.launch({executablePath:path.join(ROOT,'../source/node_modules/electron/dist/electron'),args:[path.join(ROOT,'desktop/main.cjs')],env,timeout:25000});
 try{
  const page=await app.firstWindow();page.on('pageerror',error=>report.errors.push(String(error)));
  await page.waitForFunction(()=>window.ARGOSWorkspace?.voiceState().ready,null,{timeout:90000});
  check('native Hermes conversation connected',await page.evaluate(()=>window.ARGOSWorkspace.voiceState().ready));
  check('no research calls to action',await page.getByText(/Explorar una investigación|Repetir secuencia|Qué investigamos/).count()===0);
  check('no automatic research windows',await page.evaluate(()=>window.ARGOSWorkspace.snapshot().length===0));
  check('no permanent chat input or sidebar',await page.locator('input').count()===0);
  const previous=await page.evaluate(()=>window.ARGOSWorkspace.voiceState());
  for(const phase of ['thinking','synthesizing','speaking']){
   await app.evaluate(({BrowserWindow},{state,phase})=>BrowserWindow.getAllWindows()[0].webContents.send('runtime-event',{type:'voice.state',...state,phase}),{state:previous,phase});
   await page.waitForTimeout(50);check('no cylinder during '+phase,await page.locator('#workspace').getAttribute('data-phase')!=='expanding');
  }
  await app.evaluate(({BrowserWindow},state)=>BrowserWindow.getAllWindows()[0].webContents.send('runtime-event',{type:'voice.state',...state}),previous);
  await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].webContents.send('runtime-event',{type:'process.started',id:'test-process',title:'Proceso de prueba'}));
  await page.waitForTimeout(150);check('cylinder reserved for process start',await page.locator('#workspace').getAttribute('data-phase')==='expanding');
  await page.waitForTimeout(1400);check('process opens a status window',await page.locator('[data-window="test-process"]').count()===1);await page.evaluate(()=>window.ARGOSWorkspace.clear());

  await page.locator('#core-button').click();check('circle opens general controls',await page.locator('#core-menu').isVisible());
  await page.locator('[data-panel="agents"]').click();check('agent panel reports connected conversation',await page.locator('[data-window="agents"]').getByText('CONECTADA',{exact:true}).count()===1);
  const token=fs.readFileSync(path.join(ROOT,'private/presentation.token'),'utf8').trim();
  const post=async(path,payload)=>{const response=await fetch(BASE+path,{method:'POST',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},body:JSON.stringify(payload)});return {status:response.status,body:await response.json()}};
  await post('/api/presentation',{type:'window.open',id:'general-note',kind:'note',title:'Prueba de voz y contexto',text:'<script>window.pwned=true</script>'});
  await page.locator('[data-window="general-note"]').waitFor({state:'visible'});
  check('authenticated presentation event reaches desktop',await page.locator('[data-window="general-note"]').count()===1);
  check('untrusted text stays literal',await page.evaluate(()=>!window.pwned));
  await page.waitForTimeout(600);
  const start=await page.evaluate(()=>window.ARGOSWorkspace.snapshot().find(w=>w.id==='general-note'));
  const box=await page.locator('[data-window="general-note"] .window-title').boundingBox();await page.mouse.move(box.x+90,box.y+17);await page.mouse.down();await page.mouse.move(box.x+135,box.y+42,{steps:6});await page.mouse.up();
  await page.waitForTimeout(100);check('user can move windows',await page.evaluate(old=>{const w=window.ARGOSWorkspace.snapshot().find(w=>w.id==='general-note');return w.x!==old.x||w.y!==old.y},start));
  await page.locator('[data-window="general-note"] [aria-label="Minimizar"]').click();await page.locator('#window-dock button').click();check('minimize and restore',await page.locator('[data-window="general-note"]').isVisible());
  await page.evaluate(()=>window.ARGOSWorkspace.openPanel('browser',{url:'https://es.wikipedia.org/wiki/Aurora_polar'}));await page.waitForTimeout(2500);
  const remote=await app.evaluate(({webContents})=>webContents.getAllWebContents().filter(c=>c.getURL().startsWith('https:')).map(c=>({url:c.getURL(),node:c.getLastWebPreferences().nodeIntegration,sandbox:c.getLastWebPreferences().sandbox})));
  check('native browser remains isolated',remote.length>0&&remote.every(c=>!c.node&&c.sandbox),remote);
  let rejected=false;try{await page.evaluate(()=>window.argosDesktop.voice({op:'test-text',text:'Untrusted test'}))}catch{rejected=true}check('test entry absent from production renderer bridge',rejected);
  await page.evaluate(()=>window.argosDesktop.voice({op:'output',enabled:false}));await page.waitForFunction(()=>window.ARGOSWorkspace.voiceState().output_muted);
  check('sound control reaches actual speech backend',await page.evaluate(()=>window.ARGOSWorkspace.voiceState().output_muted));
  await page.evaluate(()=>window.argosDesktop.voice({op:'output',enabled:true}));
  await page.evaluate(()=>window.argosDesktop.voice({op:'listen',enabled:false}));await page.waitForFunction(()=>window.ARGOSWorkspace.voiceState().phase==='off');check('microphone off state is real',await page.evaluate(()=>!window.ARGOSWorkspace.voiceState().listening));
  check('no renderer errors',report.errors.length===0,report.errors);
  const image=await app.evaluate(async({BrowserWindow})=>(await BrowserWindow.getAllWindows()[0].webContents.capturePage()).toPNG().toString('base64'));fs.writeFileSync(path.join(ROOT,'reports/general-workspace.png'),Buffer.from(image,'base64'));
 }finally{await app.close();fs.writeFileSync(path.join(ROOT,'reports/general-ui-checks.json'),JSON.stringify(report,null,2))}
})().catch(error=>{report.failure=String(error);fs.writeFileSync(path.join(ROOT,'reports/general-ui-checks.json'),JSON.stringify(report,null,2));console.error(error);process.exitCode=1});
