const {_electron:electron}=require('../source/node_modules/playwright');const fs=require('fs'),path=require('path'),cp=require('child_process');const ROOT=__dirname,BASE='http://127.0.0.1:42721',report={checks:[],errors:[]};
function check(name,ok,detail){report.checks.push({name,ok,detail});console.log(name,ok);if(!ok)throw Error(name)}
(async()=>{const env={PATH:'/usr/bin:/bin',HOME:path.join(ROOT,'state/home'),LANG:'C.UTF-8',ARGOS_UI_QA:'1',ARGOS_UI_PLATFORM:'x11',ARGOS_UI_ORIGIN:BASE};for(const k of ['DISPLAY','XDG_RUNTIME_DIR','DBUS_SESSION_BUS_ADDRESS'])if(process.env[k])env[k]=process.env[k];const app=await electron.launch({executablePath:path.join(ROOT,'../source/node_modules/electron/dist/electron'),args:[path.join(ROOT,'desktop/main.cjs')],env});
 const token=fs.readFileSync(path.join(ROOT,'private/presentation.token'),'utf8').trim();const post=async(route,data)=>{const r=await fetch(BASE+route,{method:'POST',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},body:JSON.stringify(data)});const body=await r.json();if(!r.ok)throw Error(JSON.stringify(body));return body};
 try{const page=await app.firstWindow();page.on('pageerror',e=>report.errors.push(String(e)));await page.waitForFunction(()=>window.ARGOSWorkspace?.voiceState().ready,null,{timeout:200000});const state=await page.evaluate(()=>window.ARGOSWorkspace.voiceState());report.startup=state;
  check('Codex ready before any conversation input',state.codex_ready===true&&state.api_mode==='codex_app_server');
  check('all startup components confirmed separately',['codex','recognition','speech'].every(k=>state.components[k]==='ready'),state.components);
  check('startup timing identifies each component',['codex','recognition','speech'].every(k=>state.startup_seconds[k]>0),state.startup_seconds);
  check('no cylinder for ordinary startup readiness',await page.locator('#workspace').getAttribute('data-phase')!=='expanding');
  await page.evaluate(()=>window.ARGOSWorkspace.openPanel('agents'));check('agent panel reports actual Codex readiness',await page.locator('[data-window=agents]').getByText('LISTO',{exact:true}).count()===1);
  // Disposable incident only. Production autolog is never rewritten by this UI test.
  const script="from maintenance.controller import Maintenance,BASE; m=Maintenance(state=BASE/'qa/argos-eager-boot-check');m.incident('capability',PermissionError('Operational ARGOS is protected'),notify=False)";
  cp.execFileSync(path.join(ROOT,'../env/bin/python'),['-c',script],{env:{PATH:'/usr/bin:/bin',PYTHONPATH:path.join(ROOT,'..')}});
  await post('/api/capability',{tool:'development',arguments:{action:'show'}});await page.locator('[data-window=maintenance]').waitFor();const card=page.locator('[data-window=maintenance] [data-incident]').filter({hasText:'Operational ARGOS is protected'});
  check('denial is explained as a protection',(await card.textContent()).includes('Es una protección'));
  check('no repair button for authorization denials',await card.getByRole('button',{name:'Preparar corrección con Codex'}).count()===0);
  await post('/api/voice',{op:'output',enabled:true});await post('/api/voice',{op:'test-text',text:'Say exactly: Ready.'});
  const metrics=fs.readFileSync(path.join(ROOT,'reports/voice-latency.jsonl'),'utf8').trim().split('\n').map(JSON.parse).filter(r=>r.session_id==='argos-eager-boot-check').at(-1);check('first real turn produces voice after eager startup',metrics.audio_packets.length>0);report.first_turn=metrics;
  check('no renderer errors',report.errors.length===0,report.errors);
 }finally{await app.close();fs.writeFileSync(path.join(ROOT,'reports/eager-boot-ui-checks.json'),JSON.stringify(report,null,2))}
})().catch(e=>{report.failure=String(e);fs.writeFileSync(path.join(ROOT,'reports/eager-boot-ui-checks.json'),JSON.stringify(report,null,2));console.error(e);process.exitCode=1});
