// Opt-in real Electron -> General/Codex -> MCP -> Broker -> native Wayland apps.
// Run only from the prepared disposable installation; no microphone or speakers.
const fs=require('node:fs'),path=require('node:path'),cp=require('node:child_process');
const P=path.resolve(__dirname,'..'),U=path.join(P,'ui-workbench');
if(!P.startsWith('/tmp/argos-desktop-qa/'))throw Error('Use the disposable desktop QA installation');
const out=path.join(P,'reports/desktop-live');fs.mkdirSync(out,{recursive:true});
const {_electron:electron}=require(path.join(P,'source/node_modules/playwright'));
const testStarted=Date.now()/1000;
const report={checks:[],turns:[],renderer_errors:[],audio:false};let host,app,page;
const pause=ms=>new Promise(r=>setTimeout(r,ms));
const save=()=>fs.writeFileSync(path.join(out,'report.json'),JSON.stringify(report,null,2));
function check(name,ok){report.checks.push({name,ok});save();console.log(name,ok);if(!ok)throw Error(name)}
async function start(){host=cp.spawn('/usr/bin/python3',[path.join(U,'server.py'),'--text-only','--no-capture','--mute-playback','--port','42724','--session','argos-desktop-native-qa-v6'],{stdio:['ignore',fs.openSync(path.join(out,'host.log'),'a'),fs.openSync(path.join(out,'host.log'),'a')]});for(let n=0;n<60;n++){try{const v=await(await fetch('http://127.0.0.1:42724/health')).json();if(v.agent_connected)return}catch{}if(host.exitCode!==null)throw Error('Host exited');await pause(1000)}throw Error('General startup timeout')}
async function stop(){if(host&&host.exitCode===null){host.kill('SIGTERM');await Promise.race([new Promise(r=>host.once('exit',r)),pause(10000)]);if(host.exitCode===null)host.kill('SIGKILL')}}
async function launch(){const env={HOME:path.join(U,'state/home'),PATH:'/usr/bin:/bin',LANG:'C.UTF-8',ARGOS_UI_QA:'1',ARGOS_UI_PLATFORM:'x11',ARGOS_UI_ORIGIN:'http://127.0.0.1:42724'};for(const k of ['DISPLAY','XDG_RUNTIME_DIR','DBUS_SESSION_BUS_ADDRESS'])if(process.env[k])env[k]=process.env[k];app=await electron.launch({executablePath:path.join(P,'source/node_modules/electron/dist/electron'),args:[path.join(U,'desktop/main.cjs')],env});await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].setFullScreen(true));page=await app.firstWindow();page.on('pageerror',e=>report.renderer_errors.push(String(e)));await page.waitForFunction(()=>window.ARGOSWorkspace);await page.evaluate(()=>{window.__answers=[];window.argosDesktop.onRuntimeEvent(e=>{if(e.type==='voice.answer')window.__answers.push(e.text)})})}
async function send(text){await page.evaluate(()=>window.ARGOSWorkspace.openPanel('conversation'));const before=await page.evaluate(()=>window.__answers.length);await page.getByLabel('Mensaje para ARGOS',{exact:true}).fill(text);await page.getByRole('button',{name:'Enviar',exact:true}).click();return async()=>{await page.waitForFunction(n=>window.__answers.length>n,before,{timeout:90000});const answer=await page.evaluate(()=>window.__answers.at(-1));report.turns.push({request:text,answer});save();return answer}}
const call=args=>page.evaluate(arguments_=>window.argosDesktop.capability({tool:'desktop',arguments:arguments_}),args);
async function finish(job){for(let i=0;i<160&&job.state==='running';i++){await pause(100);job=await call({action:'status',job:job.id})}return job}
(async()=>{try{
 await start();await launch();check('real application and General ready in text mode',await page.evaluate(()=>window.ARGOSWorkspace.voiceState().ready));
 check('desktop discovered through trusted renderer IPC',(await call({action:'availability'})).enabled);
 check('ordinary native turn before desktop request',!!await(await send('Argos, ¿estás ahí? Responde brevemente sin usar herramientas.'))());
 const answer=await(await send('ARGOS, abre la calculadora y úsala para calcular 12 + 25. Comprueba lo que aparece en su pantalla y dime el resultado.'))();console.log('General:',answer);
 let status=await call({action:'status'});report.native_action=status;
 // Completed jobs remain available by their returned IDs; idle status is only availability.
 const audit=fs.readFileSync(path.join(U,'reports/workspace-capability-audit.jsonl'),'utf8').trim().split('\n').map(JSON.parse).filter(x=>x.tool==='desktop'&&x.time>=testStarted);report.desktop_calls=audit;
 check('natural request used real desktop open and act',audit.some(x=>x.action==='open'&&x.ok)&&audit.some(x=>x.action==='act'&&x.ok));
 let view=await call({action:'open',application:'calculator'});report.calculator_display=view.texts;
 const clients=JSON.parse(cp.execFileSync('/usr/bin/hyprctl',['-j','clients']));report.wayland=clients.filter(c=>{try{return fs.readFileSync('/proc/'+c.pid+'/environ').includes(Buffer.from('/tmp/argos-desktop-qa/scopes/'))}catch{return false}}).map(c=>({class:c.class,pid:c.pid,xwayland:c.xwayland,mapped:c.mapped}));check('calculator is native Wayland',report.wayland.some(c=>c.class==='galculator'&&c.xwayland===false&&c.mapped));
 check('actual calculator displays 37',view.texts.some(x=>x.text==='37'));check('General reports observed answer',/37/.test(answer));
 await page.screenshot({path:path.join(out,'conversation-calculator.png')});
 let rejected=false;try{await call({action:'act',scope:view.scope,snapshot:'expired',refs:[view.elements[0].ref]})}catch{rejected=true}check('stale snapshot rejected in real application',rejected);
 const refs=Object.fromEntries(view.elements.map(x=>[x.name,x.ref]));const operation={action:'act',scope:view.scope,snapshot:view.snapshot,refs:['AC','1','2','3','4','5','6','7','8','9','+','1','='].map(x=>refs[x])};
 let job=await call(operation);check('desktop operation hands back running job',job.state==='running');
 const timer=performance.now();await page.evaluate(()=>window.argosDesktop.capability({tool:'apps',arguments:{action:'list'}}));report.apps_ms=performance.now()-timer;check('app discovery stays responsive during desktop work',report.apps_ms<1000);
 await page.evaluate(id=>window.argosDesktop.capability({tool:'workspace',arguments:{action:'close',id}}),'desktop-'+job.id.slice(0,12));check('closing progress panel does not cancel desktop work',(await call({action:'status',job:job.id})).state!=='cancelled');
 const talk=await send('Mientras tanto, dime en una frase qué diferencia hay entre un archivo y una carpeta. No uses herramientas.');const jobDuringTalk=await call({action:'status',job:job.id});report.foreground_started_while_job=jobDuringTalk.state;
 await page.evaluate(()=>window.ARGOSWorkspace.openPanel('conversation'));
 job=await finish(job);check('background sequence completes',job.state==='completed');const duplicate=await call(operation);check('duplicate action does not replay',duplicate.id===job.id&&duplicate.completed_steps===job.completed_steps);
 report.foreground_answer=await talk();check('ordinary conversation remains available',!!report.foreground_answer);
 view=job.result;const next=Object.fromEntries(view.elements.map(x=>[x.name,x.ref]));let cancelled=await call({action:'act',scope:view.scope,snapshot:view.snapshot,refs:Array(16).fill(next['1'])});await call({action:'cancel',job:cancelled.id});cancelled=await finish(cancelled);check('actual cancellation stops remaining clicks',cancelled.state==='cancelled'&&cancelled.completed_steps<16);report.cancelled={state:cancelled.state,steps:cancelled.completed_steps};
 const root=JSON.parse(fs.readFileSync(path.join(P,'installation.json'))).user_home;fs.writeFileSync(path.join(root,'before.txt'),'STL and OBJ\n3MF pending\n');fs.writeFileSync(path.join(root,'after.txt'),'STL and OBJ\n3MF accepted\n');
 const comparison=await call({action:'open',application:'comparison',left:path.join(root,'before.txt'),right:path.join(root,'after.txt')});report.comparison=comparison;check('real Meld comparison is observed read-only',comparison.read_only&&comparison.texts.some(t=>t.text.includes('3MF pending'))&&comparison.texts.some(t=>t.text.includes('3MF accepted')));
 check('comparison preserved originals',fs.readFileSync(path.join(root,'before.txt'),'utf8')==='STL and OBJ\n3MF pending\n');await call({action:'release',scope:comparison.scope});
 await call({action:'release',scope:view.scope});let closed=false;try{await call({action:'observe',scope:view.scope})}catch{closed=true}check('closed application scope rejected',closed);
 await app.close();app=null;await stop();await start();await launch();check('restart preserves configured availability without replay',(await call({action:'status'})).state==='idle');
 let old=false;try{await call({action:'status',job:job.id})}catch{old=true}check('old action not resumed after restart',old);check('no renderer errors',report.renderer_errors.length===0);
 }catch(e){report.failure=String(e);console.error(e);process.exitCode=1;try{await page.screenshot({path:path.join(out,'failure.png')})}catch{}}
 finally{save();if(app)await app.close();await stop()}
})();
