const {_electron:electron}=require('../source/node_modules/playwright');const fs=require('fs'),path=require('path');
const ROOT=__dirname,BASE='http://127.0.0.1:42721',report={checks:[],errors:[],answers:[]};
const check=(name,ok,detail)=>{report.checks.push({name,ok,detail});console.log(name,ok);if(!ok)throw Error(name)};
(async()=>{const env={PATH:'/usr/bin:/bin',HOME:path.join(ROOT,'state/home'),LANG:'C.UTF-8',ARGOS_UI_QA:'1',ARGOS_UI_PLATFORM:'x11',ARGOS_UI_ORIGIN:BASE};for(const k of ['DISPLAY','XDG_RUNTIME_DIR','DBUS_SESSION_BUS_ADDRESS'])if(process.env[k])env[k]=process.env[k];
 const app=await electron.launch({executablePath:path.join(ROOT,'../source/node_modules/electron/dist/electron'),args:[path.join(ROOT,'desktop/main.cjs')],env});
 const token=fs.readFileSync(path.join(ROOT,'private/presentation.token'),'utf8').trim(),fixture=JSON.parse(fs.readFileSync(path.join(ROOT,'reports/development-ui-fixture.json')));
 const post=async(route,body)=>{const r=await fetch(BASE+route,{method:'POST',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},body:JSON.stringify(body)});const result=await r.json();if(!r.ok)throw Error(JSON.stringify(result));return result};
 try{const page=await app.firstWindow();page.on('pageerror',e=>report.errors.push(String(e)));await page.waitForFunction(()=>window.ARGOSWorkspace?.voiceState().ready,null,{timeout:90000});await post('/api/voice',{op:'output',enabled:true});
  await post('/api/capability',{tool:'workspace',arguments:{action:'clear'}});await post('/api/capability',{tool:'workspace',arguments:{action:'open',id:'qa-context-note',kind:'note',title:'Cobalt enclosure planning',text:'Synthetic context probe'}});
  await page.evaluate(()=>{window.qaAnswers=[];window.argosDesktop.onRuntimeEvent(e=>{if(e.type==='voice.answer')window.qaAnswers.push(e.text)})});
  await post('/api/voice',{op:'test-text',text:'Which window is currently open in the workspace? Give only its exact title.'});let answer=await page.evaluate(()=>window.qaAnswers.at(-1));report.answers.push(answer);check('native agent receives current workspace context',answer.includes('Cobalt enclosure planning'),answer);
  await post('/api/voice',{op:'test-text',text:'Open the ARGOS development and error log panel.'});answer=await page.evaluate(()=>window.qaAnswers.at(-1));report.answers.push(answer);await page.locator('[data-window=maintenance]').waitFor();check('native development tool opens actual review panel',await page.locator('[data-window=maintenance]').isVisible(),answer);
  await page.evaluate(()=>window.argosDesktop.diagnostic({component:'renderer',message:'Synthetic QA rendering failure password=DO_NOT_PERSIST'}));await page.waitForTimeout(700);await page.locator('[data-window=maintenance]').getByRole('button',{name:'Actualizar',exact:true}).click();await page.waitForTimeout(500);
  check('structured incident appears in autolog',await page.locator('[data-window=maintenance]').getByText(/Synthetic QA rendering failure/).count()>0);
  check('secret excluded from visible incident',!(await page.locator('[data-window=maintenance]').textContent()).includes('DO_NOT_PERSIST'));
  const before=await post('/api/capability',{tool:'development',arguments:{action:'status'}});const prior=new Set(before.proposals.map(p=>p.id));
  await post('/api/voice',{op:'test-text',text:'Improve the ARGOS agent map: change the label Modelo to Modelo de conversación. Prepare the patch for my review; do not install it.'});
  let prepared;const deadline=Date.now()+150000;
  while(Date.now()<deadline){const status=await post('/api/capability',{tool:'development',arguments:{action:'status'}});prepared=status.proposals.find(p=>!prior.has(p.id));if(prepared&&prepared.status!=='preparing')break;await new Promise(r=>setTimeout(r,600))}
  check('conversation dispatches native Codex programming',prepared?.status==='awaiting_review',prepared);
  const actual=await post('/api/capability',{tool:'development',arguments:{action:'review',proposal_id:prepared.id}});report.native_proposal={id:actual.id,native_thread_id:actual.native_thread_id,validation:actual.validation,changed_files:actual.changed_files,events:actual.events};
  check('coding commands pass the real permission preflight',actual.events.some(e=>e.type==='sandbox.preflight'&&e.ok));
  await post('/api/capability',{tool:'development',arguments:{action:'confirm',proposal_id:prepared.id,review_digest:actual.review_digest,approve:false}});
  check('rejecting native improvement preserves running source',fs.readFileSync(path.join(ROOT,'dist/app.js'),'utf8').includes("['Modelo',voice.model"));
  await page.locator('[data-window=maintenance]').getByRole('button',{name:'Actualizar',exact:true}).click();await page.waitForTimeout(400);
  const card=page.locator(`[data-proposal="${fixture.id}"]`);await card.waitFor();check('review displays complete concrete diff',(await card.textContent()).includes('Synthetic QA review fixture'));
  check('review identifies validation limits',(await card.textContent()).includes('feature correctness'));
  const inventory=await post('/api/capability',{tool:'development',arguments:{action:'status'}});check('actual capability inventory and workspace',inventory.capabilities.includes('isolated Codex programming')&&inventory.workspace.some(w=>w.id==='qa-context-note'));
  // Exercise the trusted button only on an isolated QA grant; the production launcher never reads this ledger.
  await card.getByRole('button',{name:'Aprobar actualización y reiniciar'}).click();await page.waitForEvent('close',{timeout:10000}).catch(()=>{});
  const row=JSON.parse(fs.readFileSync(path.join(ROOT,'../maintenance/qa/argos-self-development-check/proposals',fixture.id,'proposal.json')));check('trusted user review grants exact patch',row.status==='approved');
  check('QA grant never hot-writes live code',fs.readFileSync(path.join(ROOT,'dist/style.css'),'utf8').includes('Synthetic QA review fixture')===false);
  check('no renderer errors',report.errors.length===0,report.errors);
 }finally{await app.close().catch(()=>{});fs.writeFileSync(path.join(ROOT,'reports/self-development-ui.json'),JSON.stringify(report,null,2))}
})().catch(e=>{report.failure=String(e);fs.writeFileSync(path.join(ROOT,'reports/self-development-ui.json'),JSON.stringify(report,null,2));console.error(e);process.exitCode=1});
