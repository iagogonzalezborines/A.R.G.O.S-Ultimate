const {_electron:electron}=require('../source/node_modules/playwright');
const fs=require('node:fs'),path=require('node:path'),cp=require('node:child_process');
const ROOT=__dirname,BASE='http://127.0.0.1:42721',report={checks:[],errors:[]};
function check(name,ok,detail){report.checks.push({name,ok,detail});console.log(name,ok);if(!ok)throw Error(name)}
(async()=>{
 const env={PATH:'/usr/bin:/bin',HOME:path.join(ROOT,'state/home'),LANG:'C.UTF-8',ARGOS_UI_QA:'1',ARGOS_UI_PLATFORM:'x11',ARGOS_UI_ORIGIN:BASE};for(const key of ['XDG_RUNTIME_DIR','DISPLAY','DBUS_SESSION_BUS_ADDRESS'])if(process.env[key])env[key]=process.env[key];
 const app=await electron.launch({executablePath:path.join(ROOT,'../source/node_modules/electron/dist/electron'),args:[path.join(ROOT,'desktop/main.cjs')],env,timeout:25000});
 const token=fs.readFileSync(path.join(ROOT,'private/presentation.token'),'utf8').trim();
 const post=async(route,payload)=>{const r=await fetch(BASE+route,{method:'POST',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},body:JSON.stringify(payload)});const body=await r.json();if(!r.ok)throw Error(JSON.stringify(body));return body};
 const tool=(name,args)=>post('/api/capability',{tool:name,arguments:args});
 try{
  const page=await app.firstWindow();await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].setFullScreen(true));await page.waitForTimeout(700);page.on('pageerror',error=>report.errors.push(String(error)));await page.waitForFunction(()=>!!window.ARGOSWorkspace);await page.waitForTimeout(500);
  await page.evaluate(()=>{for(const kind of ['summary','sources','progress','video'])window.ARGOSWorkspace.openPanel(kind,{id:kind,title:kind,text:'Synthetic UI content'})});
  const sizes=await page.evaluate(()=>window.ARGOSWorkspace.snapshot());const area=k=>{const w=sizes.find(w=>w.kind===k);return w.width*w.height};
  check('summary larger than citations',area('summary')>area('sources'),sizes);check('video larger than summary',area('video')>area('summary'));check('progress smaller than citations',area('progress')<area('sources'));
  await tool('workspace',{action:'arrange'});const arranged=await page.evaluate(()=>window.ARGOSWorkspace.snapshot());const aa=k=>{const w=arranged.find(w=>w.kind===k);return w.width*w.height};check('weighted arrange preserves semantic importance',aa('video')>aa('summary')&&aa('summary')>aa('sources')&&aa('sources')>aa('progress'),arranged);
  await tool('workspace',{action:'maximize',id:'summary'});check('acknowledged maximize',await page.evaluate(()=>window.ARGOSWorkspace.snapshot().find(w=>w.id==='summary').maximized));await tool('workspace',{action:'maximize',id:'summary'});
  await tool('workspace',{action:'move',id:'summary',x:24,y:40,width:800,height:500});check('acknowledged geometry',await page.evaluate(()=>{const w=window.ARGOSWorkspace.snapshot().find(w=>w.id==='summary');return w.x===24&&w.y===40&&w.width===800}));
  await tool('workspace',{action:'minimize',id:'summary'});check('acknowledged minimize',await page.evaluate(()=>window.ARGOSWorkspace.snapshot().find(w=>w.id==='summary').minimized));await tool('workspace',{action:'restore',id:'summary'});
  await page.evaluate(()=>window.ARGOSWorkspace.clear());
  await page.locator('#core-button').click();await page.locator('[data-panel=files]').click();await page.locator('.file-roots').getByText('ARGOS',{exact:true}).click();check('custom explorer opens actual allowed roots',await page.locator('.file-toolbar input[aria-label=Carpeta]').inputValue()===path.resolve(ROOT,'../workspaces/files'));
  const native=cp.spawn('/usr/bin/python',[path.resolve(ROOT,'../checks/workspace_native_probe.py')],{stdio:['ignore','pipe','pipe']});let nativeOutput='';native.stdout.on('data',data=>{nativeOutput+=data.toString();console.log(data.toString().trim())});native.stderr.on('data',data=>console.error(data.toString()));const code=await new Promise(resolve=>native.on('exit',resolve));check('native Hermes MCP probe completed',code===0);
  const turns=JSON.parse(fs.readFileSync(path.join(ROOT,'reports/workspace-native-checks.json'))).turns;
  check('native reads actual selected file context',/cobalt blue/i.test(turns[2].response.speech)&&/80/.test(turns[2].response.speech));
  const snapshot=await tool('workspace',{action:'inspect'});check('native opened document through broker',snapshot.windows.some(w=>w.kind==='document'&&/workspace-pilot-context.txt$/.test(w.path)));
  const video=snapshot.windows.find(w=>w.kind==='video');check('native opened and minimized actual video panel',!!video&&video.minimized&&video.url?.includes('youtube.com/watch'));
  check('native prepared concrete rename',snapshot.windows.some(w=>w.kind==='change'));const fixture=path.resolve(ROOT,'../workspaces/files/workspace-pilot-context.txt');check('native cannot apply its own proposed edit',fs.existsSync(fixture)&&!fs.existsSync(fixture.replace('.txt','-renamed.txt')));
  await page.locator('.file-review .file-button').filter({hasText:'Aplicar cambio'}).click();await page.waitForTimeout(600);check('user can apply reviewed file change',!fs.existsSync(fixture)&&fs.existsSync(fixture.replace('.txt','-renamed.txt')));
  await page.evaluate(()=>window.ARGOSWorkspace.clear());
  const url='https://images-assets.nasa.gov/video/GSFC_20171107_Ionosphere_m12532_ICON/GSFC_20171107_Ionosphere_m12532_ICON~mobile.mp4';
  await tool('workspace',{action:'open',id:'nasa-video',kind:'video',title:'NASA / vídeo de prueba',url});
  let playback;
  for(let i=0;i<18;i++){await page.waitForTimeout(1000);playback=await app.evaluate(async({webContents})=>{const c=webContents.getAllWebContents().find(c=>c.getURL().includes('GSFC_20171107'));if(!c)return null;return c.executeJavaScript('(()=>{const v=document.querySelector("video");return v?{time:v.currentTime,ready:v.readyState,error:v.error?.code,paused:v.paused}:null})()').catch(()=>null)});if(playback?.time>0)break}
  check('real video renders and plays inside native panel',playback?.time>0,playback);
  const prefs=await app.evaluate(({webContents})=>webContents.getAllWebContents().filter(c=>c.getURL().startsWith('https:')).map(c=>({node:c.getLastWebPreferences().nodeIntegration,sandbox:c.getLastWebPreferences().sandbox})));check('remote video has no Node bridge',prefs.length>0&&prefs.every(c=>!c.node&&c.sandbox));
  await page.evaluate(()=>window.ARGOSWorkspace.openPanel('files',{path:'ARGOS'}));await page.waitForTimeout(500);await tool('workspace',{action:'arrange'});
  check('no renderer errors',report.errors.length===0,report.errors);const image=await app.evaluate(async({BrowserWindow})=>(await BrowserWindow.getAllWindows()[0].webContents.capturePage()).toPNG().toString('base64'));fs.writeFileSync(path.join(ROOT,'reports/workspace-files-video.png'),Buffer.from(image,'base64'));
 }finally{await app.close();fs.writeFileSync(path.join(ROOT,'reports/workspace-ui-checks.json'),JSON.stringify(report,null,2))}
})().catch(error=>{report.failure=String(error);fs.writeFileSync(path.join(ROOT,'reports/workspace-ui-checks.json'),JSON.stringify(report,null,2));console.error(error);process.exitCode=1});
