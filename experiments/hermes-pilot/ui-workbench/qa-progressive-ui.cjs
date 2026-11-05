const {_electron:electron}=require('../source/node_modules/playwright');
const fs=require('fs'),path=require('path');
const ROOT=__dirname,BASE='http://127.0.0.1:42721',report={checks:[],errors:[]};
function check(name,ok){report.checks.push({name,ok});if(!ok)throw Error(name)}
(async()=>{
 const env={PATH:'/usr/bin:/bin',HOME:path.join(ROOT,'state/home'),LANG:'C.UTF-8',ARGOS_UI_QA:'1',ARGOS_UI_PLATFORM:'x11',ARGOS_UI_ORIGIN:BASE};
 for(const k of ['DISPLAY','XDG_RUNTIME_DIR','DBUS_SESSION_BUS_ADDRESS'])if(process.env[k])env[k]=process.env[k];
 const app=await electron.launch({executablePath:path.join(ROOT,'../source/node_modules/electron/dist/electron'),args:[path.join(ROOT,'desktop/main.cjs')],env});
 try{
  const page=await app.firstWindow();page.on('pageerror',e=>report.errors.push(String(e)));await page.waitForFunction(()=>window.ARGOSWorkspace);
  await app.evaluate(({ipcMain})=>{global.openCommands=[];const original=ipcMain._invokeHandlers.get('ui:browser');ipcMain.removeHandler('ui:browser');ipcMain.handle('ui:browser',(e,p)=>{if(p.type==='open')global.openCommands.push(p);return original(e,p)})});
  const token=fs.readFileSync(path.join(ROOT,'private/presentation.token'),'utf8').trim();
  const post=async args=>{const r=await fetch(BASE+'/api/capability',{method:'POST',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},body:JSON.stringify({tool:'workspace',arguments:args})});const value=await r.json();if(!r.ok)throw Error(JSON.stringify(value));return value};
  const event=e=>app.evaluate(({BrowserWindow},e)=>BrowserWindow.getAllWindows()[0].webContents.send('runtime-event',e),e);
  await post({action:'clear'});
  await event({type:'process.started',id:'web-research',title:'Incremental delivery check',status:'Searching sources…',language:'en'});
  await page.waitForSelector('[data-window="web-research"] progress:not([value])');
  check('actual work has an immediate indeterminate loading bar',true);
  await post({action:'research_sources',sources:[{title:'NASA',url:'https://science.nasa.gov/'}],open_sources:1});
  await page.waitForFunction(()=>document.querySelectorAll('.process-source').length===1);
  check('first source is visible before the next is submitted',(await page.locator('.process-sources').innerText()).includes('NASA'));
  await post({action:'research_sources',sources:[{title:'ESA',url:'https://www.esa.int/'}],open_sources:1});
  await page.waitForFunction(()=>document.querySelectorAll('.process-source').length===2);
  check('source feed grows one by one',(await page.locator('.process-sources').innerText()).includes('ESA'));
  await post({action:'research_sources',sources:[{title:'NASA',url:'https://science.nasa.gov/'}],open_sources:1});
  check('repeated source is not reloaded',await app.evaluate(()=>global.openCommands.filter(p=>p.url==='https://science.nasa.gov/').length===1));
  await event({type:'process.completed',id:'web-research',status:'Research complete'});
  await page.waitForSelector('[data-window="web-research"] progress[value="1"]');
  check('completion resolves the loading indicator',true);
  await page.waitForTimeout(1600);report.pages=await app.evaluate(({webContents})=>webContents.getAllWebContents().filter(w=>w.getURL().startsWith('https:')).map(w=>({url:w.getURL(),title:w.getTitle(),loading:w.isLoading()})));
  await page.screenshot({path:path.join(ROOT,'reports/progressive-ui-sources.png')});
  await post({action:'clear'});await event({type:'process.source',id:'web-research',source:{url:'https://example.com/',title:'Late source'},stage:'selected',selected_sources:3});
  check('late progress cannot recreate a cleared panel',await page.evaluate(()=>window.ARGOSWorkspace.snapshot().length===0));
  check('no renderer exceptions',report.errors.length===0);
  await page.screenshot({path:path.join(ROOT,'reports/progressive-ui-cleared.png')});
 }finally{await app.close();fs.writeFileSync(path.join(ROOT,'reports/progressive-ui.json'),JSON.stringify(report,null,2))}
 console.log(JSON.stringify({passed:report.checks.length}));
})().catch(e=>{console.error(String(e));process.exitCode=1});
