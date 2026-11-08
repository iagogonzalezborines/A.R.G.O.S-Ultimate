// Renderer startup transitions only: no microphone, speech, models or live broker.
const fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const ROOT=__dirname,P=path.dirname(ROOT),{_electron:electron}=require(path.join(P,'source/node_modules/playwright'));
const report={checks:[],errors:[]};
function check(name,ok){report.checks.push({name,ok});if(!ok)throw Error(name)}
const preparing={phase:'preparing',ready:false,listening:false,text_only:false,voice_ready:false};
const server=http.createServer((req,res)=>{
 if(req.url==='/events'){res.writeHead(200,{'Content-Type':'text/event-stream'});res.write(': fixture\n\n');return}
 if(req.url==='/voice-state'||req.url==='/api/workspace'){res.setHeader('Content-Type','application/json');res.end(JSON.stringify(req.url==='/voice-state'?preparing:{ok:true}));return}
 const file=path.resolve(ROOT,'dist','.'+(req.url==='/'?'/index.html':req.url));
 if(!file.startsWith(path.join(ROOT,'dist')+path.sep)||!fs.existsSync(file)||!fs.statSync(file).isFile()){res.writeHead(404);res.end();return}
 res.setHeader('Content-Type',file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':file.endsWith('.html')?'text/html':'application/octet-stream');res.end(fs.readFileSync(file));
});
(async()=>{await new Promise(r=>server.listen(0,'127.0.0.1',r));let app;
 try{
 const env={PATH:'/usr/bin:/bin',LANG:'C.UTF-8',HOME:path.join(ROOT,'state/home'),ARGOS_UI_QA:'1',ARGOS_UI_PLATFORM:'x11',ARGOS_UI_ORIGIN:'http://127.0.0.1:'+server.address().port};for(const k of ['DISPLAY','XDG_RUNTIME_DIR','DBUS_SESSION_BUS_ADDRESS'])if(process.env[k])env[k]=process.env[k];
 app=await electron.launch({executablePath:path.join(P,'source/node_modules/electron/dist/electron'),args:[path.join(ROOT,'desktop/main.cjs')],env});const page=await app.firstWindow();page.on('pageerror',e=>report.errors.push(String(e)));await page.waitForFunction(()=>window.ARGOSWorkspace);
 const send=event=>app.evaluate(({BrowserWindow},e)=>BrowserWindow.getAllWindows()[0].webContents.send('runtime-event',e),event);
 await send({type:'voice.state',...preparing});await send({type:'voice.caption',text:'Preparando voz · compilando audio local'});await page.getByText('Preparando voz · compilando audio local',{exact:true}).waitFor();check('startup preparation caption visible',true);
 const ready={...preparing,phase:'standby',ready:true,voice_ready:true,listening:true};await send({type:'voice.state',...ready});await page.getByText('Voz preparada.',{exact:true}).waitFor();check('readiness replaces stale startup caption',true);
 await send({type:'voice.answer',text:'Your files are ready.'});await send({type:'voice.state',...ready,phase:'speaking'});await send({type:'voice.state',...ready});await page.getByText('Your files are ready.',{exact:true}).waitFor();check('return to standby preserves actual answer',true);
 await send({type:'voice.state',...preparing});await send({type:'voice.caption',text:'Preparando Codex…'});await send({type:'voice.state',...ready,text_only:true,voice_ready:false,listening:false});await page.getByText('Conversación por texto disponible.',{exact:true}).waitFor();check('text-only readiness is not voice readiness',true);
 await send({type:'voice.state',...preparing});await send({type:'voice.caption',text:'Preparando voz…'});await send({type:'voice.state',...ready,voice_ready:false});await page.getByText('La voz no está disponible; puedes escribir.',{exact:true}).waitFor();check('degraded audio is explicit',true);
 await send({type:'voice.state',...ready,phase:'error',error:'Previous request failed'});await page.getByText('Previous request failed',{exact:true}).waitFor();
 await send({type:'voice.state',...ready,phase:'listening',error:null});await page.getByText('Te escucho.',{exact:true}).waitFor();check('new wake clears displayed previous error',true);
 await send({type:'voice.state',...ready,phase:'error',error:'Previous request failed'});await send({type:'voice.transcript',text:'Hello'});await send({type:'voice.state',...ready,phase:'thinking',error:null});await page.getByText('Tú · Hello',{exact:true}).waitFor();check('error recovery preserves the new transcript',true);
 check('no renderer errors',report.errors.length===0);await page.screenshot({path:path.join(ROOT,'reports/voice-ready-caption.png')});
 }finally{if(app)await app.close();server.closeAllConnections();await new Promise(r=>server.close(r));fs.writeFileSync(path.join(ROOT,'reports/voice-ready-caption.json'),JSON.stringify(report,null,2))}
 console.log(JSON.stringify(report));
})().catch(e=>{console.error(e);process.exitCode=1});
