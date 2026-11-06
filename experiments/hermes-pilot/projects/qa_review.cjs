const path=require('node:path'),fs=require('node:fs');
const P=path.resolve(__dirname,'..'),U=path.join(P,'ui-workbench'),root=process.argv[2];
const {_electron:electron}=require(path.join(P,'source/node_modules/playwright'));
const report={checks:[],errors:[]};
function check(name,ok){report.checks.push({name,ok});console.log(name,ok);if(!ok)throw Error(name)}
(async()=>{
 const env={HOME:path.join(U,'state/home'),PATH:'/usr/bin:/bin',LANG:'C.UTF-8',ARGOS_UI_QA:'1',ARGOS_UI_PLATFORM:'x11',ARGOS_UI_ORIGIN:'http://127.0.0.1:42722'};
 for(const key of ['DISPLAY','XDG_RUNTIME_DIR','DBUS_SESSION_BUS_ADDRESS'])if(process.env[key])env[key]=process.env[key];
 const app=await electron.launch({executablePath:path.join(P,'source/node_modules/electron/dist/electron'),args:[path.join(U,'desktop/main.cjs')],env});
 try{
  const page=await app.firstWindow();page.on('pageerror',e=>report.errors.push(String(e)));
  await page.waitForFunction(()=>window.ARGOSWorkspace);
  const call=(tool,args)=>page.evaluate(({tool,args})=>window.argosDesktop.capability({tool,arguments:args}),{tool,args});
  const proposal=await call('projects',{action:'propose',name:'UI Fixture',slug:'ui-fixture',brief:{objective:'Disposable review control check'}});
  await page.getByText('Autorizar carpeta y trabajo del proyecto',{exact:true}).waitFor();
  check('project is not created before the click',!fs.existsSync(path.join(root,'repositories/ui-fixture')));
  check('exact scope is visible',(await page.locator('.file-review').innerText()).includes(path.join(root,'repositories/ui-fixture')));
  await page.getByRole('button',{name:'Aplicar cambio',exact:true}).click();
  await page.waitForFunction(()=>!document.querySelector('.file-review'));
  const listed=await call('projects',{action:'list'});
  check('trusted UI creates one native project',listed.projects.length===1&&fs.existsSync(path.join(root,'repositories/ui-fixture')));
  await call('files',{action:'propose',operation:'write',path:'QA/file-review.txt',content:'Existing file review still works.'});
  await page.getByText('Guardar archivo',{exact:true}).waitFor();
  check('file write still waits for review',!fs.existsSync(path.join(root,'file-review.txt')));
  await page.getByRole('button',{name:'Aplicar cambio',exact:true}).click();
  await page.waitForFunction(()=>!document.querySelector('.file-review'));
  check('existing file approval still works',fs.readFileSync(path.join(root,'file-review.txt'),'utf8')==='Existing file review still works.');
  check('no renderer exceptions',report.errors.length===0);
 }finally{await app.close();fs.writeFileSync(path.join(P,'reports/block-b-review-ui.json'),JSON.stringify(report,null,2))}
})().catch(e=>{console.error(e);process.exitCode=1});
