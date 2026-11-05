const {_electron:electron}=require('../source/node_modules/playwright');
const fs=require('node:fs'),path=require('node:path');
const ROOT=__dirname,BASE='http://127.0.0.1:42721',report={checks:[],turns:[],errors:[]};
const check=(name,ok,detail)=>{report.checks.push({name,ok,detail});console.log(name,ok);if(!ok)throw Error(name)};
(async()=>{
 const env={PATH:'/usr/bin:/bin',HOME:path.join(ROOT,'state/home'),LANG:'C.UTF-8',ARGOS_UI_QA:'1',ARGOS_UI_PLATFORM:'x11',ARGOS_UI_ORIGIN:BASE};for(const k of ['XDG_RUNTIME_DIR','DISPLAY','DBUS_SESSION_BUS_ADDRESS'])if(process.env[k])env[k]=process.env[k];
 const app=await electron.launch({executablePath:path.join(ROOT,'../source/node_modules/electron/dist/electron'),args:[path.join(ROOT,'desktop/main.cjs')],env,timeout:25000});
 const token=fs.readFileSync(path.join(ROOT,'private/presentation.token'),'utf8').trim();
 const post=async(route,payload)=>{let r=await fetch(BASE+route,{method:'POST',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},body:JSON.stringify(payload)});let body=await r.json();if(!r.ok)throw Error(JSON.stringify(body));return body};
 try{
  const page=await app.firstWindow();page.on('pageerror',e=>report.errors.push(String(e)));
  await page.waitForFunction(()=>window.ARGOSWorkspace?.voiceState().ready,null,{timeout:90000});
  check('Turbo and Qwen coexist ready',await page.evaluate(()=>window.ARGOSWorkspace.voiceState().recognition_model==='large-v3-turbo'&&window.ARGOSWorkspace.voiceState().recognition_device==='cuda'&&window.ARGOSWorkspace.voiceState().voice_streaming));
  await post('/api/voice',{op:'output',enabled:true});
  for(const text of ['Research who created Batman. Use two primary sources, show the sources in the workspace during the research, and give me just the key finding aloud.','Is the sky green?','Perfecto. Responde solo: Listo para continuar.']){
   await page.evaluate(()=>{window.qaEvents=[];window.qaStart=performance.now();if(!window.qaWatching){window.qaWatching=true;window.argosDesktop.onRuntimeEvent(e=>{window.qaEvents.push({seconds:(performance.now()-window.qaStart)/1000,...e})})}});
   await post('/api/voice',{op:'test-text',text});
   const events=await page.evaluate(()=>window.qaEvents);const windows=await page.evaluate(()=>window.ARGOSWorkspace.snapshot());
   const metrics=fs.readFileSync(path.join(ROOT,'reports/voice-latency.jsonl'),'utf8').trim().split('\n').map(JSON.parse).filter(r=>r.session_id==='argos-incremental-voice-check').at(-1);
   const answer=events.filter(e=>e.type==='voice.answer').at(-1)?.text;
   report.turns.push({input:text,answer,metrics,windows,events:events.filter(e=>['presentation','process.started','process.update','process.completed'].includes(e.type)).map(e=>({...e,intent:e.intent?{...e.intent,text:e.intent.text?.slice(0,100)}:undefined}))});
   console.log(JSON.stringify({answer,first_audio:metrics.first_audio_ready_seconds,model:metrics.model_seconds,web_calls:metrics.web_calls,delivery:metrics.research_delivery,windows:windows.map(w=>w.id)}));
   if(text.startsWith('Research')){
    check('immediate genuine dispatch feedback',metrics.first_audio_ready_seconds<1.5,metrics.first_audio_ready_seconds);
    check('native live web search used',metrics.web_calls>0);
    check('sources appear before final report',metrics.sources_displayed_seconds<metrics.report_displayed_seconds,metrics);
    check('separate detailed report delivered',metrics.research_delivery&&windows.some(w=>w.id==='research-summary'));
    check('source page actually opened',windows.some(w=>w.id.startsWith('source-')&&w.kind==='browser'));
    check('complete model-authored spoken conclusion',metrics.chunks.filter(c=>c.kind==='conclusion').length===1);
    await post('/api/capability',{tool:'workspace',arguments:{action:'clear'}});
   }else check('ordinary conversation remains direct',!metrics.web_calls&&!metrics.chunks.some(c=>c.kind==='progress'));
  }
  check('no renderer errors',report.errors.length===0,report.errors);
 }finally{await app.close();fs.writeFileSync(path.join(ROOT,'reports/incremental-voice-checks.json'),JSON.stringify(report,null,2))}
})().catch(e=>{report.failure=String(e);fs.writeFileSync(path.join(ROOT,'reports/incremental-voice-checks.json'),JSON.stringify(report,null,2));console.error(e);process.exitCode=1});
