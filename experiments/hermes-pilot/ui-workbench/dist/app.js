import {renderDesktopControl} from './desktop-control.js';
import {renderProjectMap} from './project-map.js';
import {renderProgress,updateProgress} from './progress.js';
import {renderMaintenance} from './maintenance.js';
import {renderFiles,renderDocument,renderChange,renderStorage} from './files.js';
import {Orbital} from './orbital.js';
import {FeedbackAudio} from './sounds.js';
import {WindowManager} from './window-manager.js';
const $=s=>document.querySelector(s),root=$('#workspace'),orb=new Orbital($('#orb')),sound=new FeedbackAudio(orb);
const processes=new Map();
let voice={phase:'preparing',ready:false,listening:false},toastTimer,lastAnswer='',streamText='',processOpening=false,processTimer,processStatus='',preparingCaption=false;
function isVideo(url){return /(?:youtube\.com\/(?:watch|shorts|embed)|youtu\.be\/|\.(?:mp4|webm)(?:[?#]|$))/i.test(url)}
function make(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e}
function caption(text){preparingCaption=false;$('#subtitle-text').textContent=text}
function toast(text){$('#toast').textContent=text;$('#toast').classList.add('visible');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').classList.remove('visible'),3000)}
function placement(){const panels=manager.windows.size>0;root.dataset.phase=panels?'working':processOpening?'expanding':'idle';orb.setPhase(processOpening?'expanding':'idle')}
function state(value){const previousError=voice.error;voice=value;const labels={preparing:'PREPARANDO',standby:'ESPERANDO «ARGOS»',listening:'ESCUCHANDO',transcribing:'RECONOCIENDO',thinking:'PENSANDO',synthesizing:'PREPARANDO VOZ',speaking:'HABLANDO',off:'MICRÓFONO APAGADO',error:'REQUIERE ATENCIÓN'};if(value.text_only){labels.standby=labels.off='CONVERSACIÓN POR TEXTO'}$('#core-state').textContent=labels[value.phase]||'EN REPOSO';$('#workspace-status').textContent=labels[value.phase]||'ESPACIO ACTIVO';$('#microphone').setAttribute('aria-pressed',String(value.listening));$('#microphone').title=value.listening?'Silenciar '+value.microphone:'Activar micrófono';$('#microphone').setAttribute('aria-label',$('#microphone').title);const canRetry=!value.ready&&!!value.startup_error_component&&value.phase==='error';if(canRetry){$('#microphone').title='Reintentar inicio de ARGOS';$('#microphone').setAttribute('aria-label',$('#microphone').title)}$('#microphone').disabled=(!value.ready&&!canRetry)||(value.text_only&&!canRetry);root.dataset.voicePhase=value.phase;const speaker=$('#voice-output');speaker.disabled=!!value.text_only;$('#mute-voice').disabled=!!value.text_only;speaker.setAttribute('aria-pressed',String(!value.output_muted));speaker.title=value.output_muted?'Activar voz':'Silenciar voz';speaker.setAttribute('aria-label',speaker.title);$('#mute-voice').firstChild.textContent=value.output_muted?'Activar voz ':'Silenciar voz ';if(value.error)caption(value.error);else if(previousError&&$('#subtitle-text').textContent===previousError)caption(value.listening?'Te escucho.':value.text_only?'Conversación por texto disponible.':'Listo.');else if(preparingCaption&&value.ready&&['standby','off'].includes(value.phase))caption(value.text_only?'Conversación por texto disponible.':value.voice_ready?'Voz preparada.':'La voz no está disponible; puedes escribir.');placement();for(const w of manager.windows.values())if(w.kind==='agents')renderAgents(w)}
function renderAgents(w){w.body.replaceChildren();const pad=make('div','panel-pad');pad.innerHTML='<div class="eyebrow-blue">ARGOS / SESIÓN ACTUAL</div><div class="agents-diagram"><div class="agents-line"></div><div class="agent-node root">ARGOS<small>VOZ Y WORKSPACE</small></div><div class="agent-node a">HERMES<small>CONVERSACIÓN</small></div><div class="agent-node b">CODEX<small>INFERENCIA LIGERA</small></div></div>';for(const [name,value] of [['Conversación',voice.ready?'CONECTADA':'PREPARANDO'],['Codex',voice.codex_ready?'LISTO':voice.components?.codex==='starting'?'INICIANDO':'PENDIENTE'],['Modelo',voice.model||'gpt-6-luna'],['Voz',voice.voice||'Qwen + Peter'],['Workspace','CONECTADO'],['Archivos','LECTURA / CAMBIOS REVISADOS'],['Micrófono',voice.listening?'ACTIVO':'APAGADO']]){const line=make('div','agent-status');line.append(make('span','',name),make('b','',value));pad.append(line)}pad.append(make('div','prepared','La sesión y el historial pertenecen a Hermes. Las herramientas de proyectos, PC, diseño y fabricación se conectan por capacidades; no se simulan tareas.'));w.body.append(pad)}
function render(w){
 if(w.kind==='desktop')return renderDesktopControl(w,{make,manager});
 if(w.kind==='project')return renderProjectMap(w,{make,manager});
 if(w.kind==='conversation'){
  const form=make('form','panel-pad conversation-form'),input=make('textarea'),send=make('button','','Enviar'),answer=make('p','note-body',lastAnswer||'Escribe una petición para ARGOS.'),status=make('p');input.setAttribute('aria-label','Mensaje para ARGOS');input.placeholder='¿Qué hacemos?';input.maxLength=12000;send.type='submit';answer.setAttribute('aria-live','polite');answer.classList.add('conversation-answer');form.append(input,send,status,answer);w.body.append(form);
  form.onsubmit=async e=>{e.preventDefault();if(!input.value.trim())return;send.disabled=true;try{await window.argosDesktop.voice({op:'text',text:input.value});input.value='';status.textContent='Petición recibida.'}catch(e){status.textContent=e.message}finally{send.disabled=false}};return;
 }

 if(w.kind==='maintenance')return renderMaintenance(w,{make,manager,toast});
 if(w.kind==='storage')return renderStorage(w,{make,manager,toast});
 if(w.kind==='files')return renderFiles(w,{make,manager,openPanel,toast});
 if(w.kind==='document')return renderDocument(w,{make,manager,openPanel,toast});
 if(w.kind==='change')return renderChange(w,{make,manager,toast});
 if(w.kind==='agents'){renderAgents(w);return}
 if(w.kind==='summary'||w.kind==='note'){const pad=make('div','panel-pad');pad.append(make('div','eyebrow-blue',w.kind==='summary'?'ARGOS / CONTEXTO':'ARGOS / OBSERVACIÓN'),make('h2','',w.title),make('p','note-body',w.spec.text||lastAnswer||'Todavía no hay contenido para mostrar.'));w.body.append(pad);return}
 if(w.kind==='sources'){const pad=make('div','panel-pad');pad.append(make('div','eyebrow-blue','ARGOS / FUENTES'),make('h2','','Fuentes citadas'));if(w.spec.text){for(const url of [...new Set(w.spec.text.match(/https:\/\/[^\s)>\]]+/g)||[])]){const lines=w.spec.text.split('\n'),at=lines.indexOf(url),label=at>0&&!lines[at-1].startsWith('https://')?lines[at-1]:new URL(url).hostname;const button=make('button','source-link');button.append(make('strong','',label),make('small','',new URL(url).hostname));button.title=url;button.onclick=()=>openPanel(isVideo(url)?'video':'browser',{id:'source-'+Array.from(url).reduce((n,c)=>Math.imul(n^c.charCodeAt(0),16777619),2166136261).toString(16).replace('-','n'),url,title:new URL(url).hostname});pad.append(button)}}else pad.append(make('p','note-body','Las fuentes que se abran durante una tarea aparecerán en este espacio.'));w.body.append(pad);return}
 if(w.kind==='progress'){renderProgress(w,make);return}
 if(w.kind==='browser'||w.kind==='video'){
  const bar=make('form','browser-bar'),back=make('button','','←'),reload=make('button','','↻'),address=make('input');back.type=reload.type='button';back.setAttribute('aria-label','Atrás');reload.setAttribute('aria-label','Recargar');address.type='url';address.value=w.spec.url||'';address.placeholder='https://…';address.setAttribute('aria-label','Dirección de la página');bar.append(back,reload,address);
  const host=make('div','browser-host'),preview=make('div','browser-preview'),message=make('div','preview-message',w.spec.url?'Cargando página…':'Navegación pública HTTPS');w.browserHost=host;w.preview=preview;w.address=address;preview.append(message);host.append(preview);w.body.append(bar,host);
  const navigate=async()=>{w.error=null;if(!address.value)return;if(!window.argosDesktop){toast('La navegación interna requiere la aplicación de escritorio.');return}try{await window.argosDesktop.browser({type:'open',id:w.id,url:address.value,kind:w.kind});w.spec.url=address.value;manager.changed();if(w.actor==='user')manager.focus(w.id);manager.syncNative()}catch(e){w.error=e.message;message.textContent=e.message||'No se pudo abrir la página.'}};
  bar.onsubmit=e=>{e.preventDefault();navigate()};back.onclick=()=>window.argosDesktop?.browser({type:'back',id:w.id});reload.onclick=()=>window.argosDesktop?.browser({type:'reload',id:w.id});preview.onclick=()=>{manager.focus(w.id);manager.syncNative()};const loading=w.spec.url?navigate():Promise.resolve();w.resizeObserver=new ResizeObserver(()=>manager.syncNative());w.resizeObserver.observe(host);return loading
 }
}
const manager=new WindowManager($('#desktop'),{render,onChange:windows=>{$('#window-count').textContent=String(windows.length).padStart(2,'0')+' VENTANAS';placement()},onSound:kind=>sound.chime(kind)});
function openPanel(kind,options={},actor='user'){return manager.open({id:options.id||(kind==='project'?'project-map':kind),kind,title:{desktop:'Control de aplicaciones',project:'Proyectos',conversation:'Conversar por texto',summary:'Contexto de conversación',sources:'Fuentes',browser:'Navegador',video:'Vídeo',files:'Archivos',storage:'Almacenamiento',agents:'Agentes',note:'Observación',progress:'Estado'}[kind]||kind,...options},{actor})}
function closeMenu(){$('#core-menu').hidden=true;manager.suspend(false)}
$('#core-button').onclick=()=>{const menu=$('#core-menu');menu.hidden=!menu.hidden;manager.suspend(!menu.hidden)};
document.addEventListener('pointerdown',e=>{if(!e.target.closest('#core-menu')&&!e.target.closest('#core-button'))closeMenu()});
document.querySelectorAll('[data-panel]').forEach(b=>b.onclick=()=>{openPanel(b.dataset.panel);closeMenu()});
$('#clear-workspace').onclick=()=>{window.argosDesktop?.capability({tool:'workspace',arguments:{action:'clear'}}).catch(e=>toast(e.message));closeMenu()};$('#arrange').onclick=()=>manager.arrange();
$('#fullscreen').onclick=()=>window.argosDesktop?window.argosDesktop.fullscreen():document.fullscreenElement?document.exitFullscreen():document.documentElement.requestFullscreen();$('#exit').onclick=()=>window.argosDesktop?.close();
async function voiceCommand(payload){if(!window.argosDesktop)return;try{return await window.argosDesktop.voice(payload)}catch{toast('No se pudo contactar con la conversación.')}}
$('#microphone').onclick=()=>voiceCommand(!voice.ready&&voice.startup_error_component?{op:'retry'}:{op:'listen',enabled:!voice.listening});$('#interrupt-voice').onclick=()=>{voiceCommand({op:'interrupt'});closeMenu()};
function soundButton(){const b=$('#sound');b.setAttribute('aria-pressed',String(sound.enabled));b.title=sound.enabled?'Silenciar efectos de sonido':'Activar efectos de sonido';b.setAttribute('aria-label',b.title)}
$('#sound').onclick=async()=>{sound.toggle();await sound.unlock();soundButton();if(sound.enabled)sound.chime()};soundButton();function toggleVoice(){voiceCommand({op:'output',enabled:voice.output_muted});closeMenu()}$('#mute-voice').onclick=toggleVoice;$('#voice-output').onclick=toggleVoice;
document.addEventListener('keydown',e=>{if(e.target.matches('input,textarea,select'))return;if(e.key==='Escape'){voiceCommand({op:'interrupt'});closeMenu()}if(e.altKey&&e.key.toLowerCase()==='a'){e.preventDefault();manager.arrange()}if(e.key==='F11'){e.preventDefault();$('#fullscreen').click()}});
async function runtimeEvent(event){
 if(event.type==='voice.state'){state(event);return}
 if(event.type==='voice.transcript'){streamText='';caption('Tú · '+event.text);return}
 if(event.type==='voice.delta'){streamText+=event.text;caption(streamText);return}
 if(event.type==='voice.answer'){lastAnswer=event.text;caption(event.text);document.querySelectorAll('.conversation-answer').forEach(el=>el.textContent=event.text);return}
 if(event.type==='voice.caption'){caption(event.text);preparingCaption=voice.phase==='preparing';return}
 if(event.type==='voice.level'){orb.setEnergy(event.level);sound.bars.forEach((bar,i)=>bar.style.height=(3+event.level*17*(.3+.7*Math.sin((i+1)*Math.PI/14)))+'px');return}
 if(['process.started','process.update','process.source','process.completed','process.cancelled','process.failed'].includes(event.type)){
  const old=processes.get(event.id)||{sources:[],selected_sources:0,opened_windows:0};
  const next={...old,...event,phase:event.type==='process.completed'?'completed':event.type==='process.cancelled'?'cancelled':event.type==='process.failed'?'failed':old.phase||'running'};
  if(event.type==='process.started'){
   next.sources=[];next.phase='running';next.selected_sources=0;next.opened_windows=0;
   processOpening=true;placement();clearTimeout(processTimer);processTimer=setTimeout(()=>{processOpening=false;placement()},650);
  }
  if(event.source){
   const sources=[...old.sources],index=sources.findIndex(s=>s.url===event.source.url),source={...event.source,stage:event.stage};
   if(index<0)sources.push(source);else sources[index]=source;next.sources=sources;
   const en=next.language==='en';next.status=event.stage==='opening'?(en?'Opening source…':'Abriendo fuente…'):event.stage==='opened'?(en?'Source window opened':'Fuente abierta'):event.stage==='found'?(en?'Sources arriving':'Recibiendo fuentes'):(en?'Source selected':'Fuente seleccionada');
  }
  processes.set(event.id,next);
  // A cancelled or cleared process must not recreate its old panel.
  let w=manager.windows.get(event.id);
  if(event.type==='process.started'){
   openPanel('progress',{id:event.id,title:event.title||'Proceso',status:next.status,process:next},'argos');w=manager.windows.get(event.id);manager.arrange({automatic:true});
  }
  if(w)updateProgress(w,next,make);
  if(next.phase!=='running'){processOpening=false;clearTimeout(processTimer);placement()}
  return;
 }
 if(event.type==='context.compaction'){caption(event.stage==='started'?(event.language==='en'?'Organising conversation context…':'Organizando el contexto de conversación…'):'');return}

 if(event.type==='maintenance.changed'){for(const w of manager.windows.values())if(w.kind==='maintenance'){clearTimeout(w.refreshTimer);w.refreshTimer=setTimeout(()=>w.refresh?.(),500)}return}
 if(event.type==='app.restart'){window.argosDesktop?.close();return}
 if(event.type==='app.close'){window.argosDesktop?.close();return}
 if(event.type==='files.progress'){for(const w of manager.windows.values())if(w.kind==='files'||w.kind==='change'){const status=w.body.querySelector('.file-status');if(status)status.textContent='Copiando '+event.name+' · '+(event.bytes/1048576).toFixed(1)+' / '+(event.total_bytes/1048576).toFixed(1)+' MiB'}return}
 if(event.type==='files.changed'){for(const w of manager.windows.values())if(w.kind==='files')w.refresh?.();return}
 if(event.intent){let error;try{if(event.intent.type==='workspace.clear'){clearTimeout(processTimer);processOpening=false;processStatus='';processes.clear()}const id=manager.apply(event.intent,{actor:event.actor==='user'?'user':'argos'});if(event.intent.type==='workspace.clear')await id;if(event.intent.type==='window.open'){const w=manager.windows.get(id);await w?.ready;if(w?.error)throw Error(w.error);if(!['files','document','change'].includes(w?.kind))manager.arrange({automatic:true})}placement()}catch(e){error=String(e);toast('No se pudo actualizar la ventana.')}if(event.request_id)await window.argosDesktop?.workspaceState({windows:manager.snapshot(),ack:event.request_id,...(error?{error}:{})});}
}
let snapshotTimer;function reportWorkspace(){clearTimeout(snapshotTimer);snapshotTimer=setTimeout(()=>window.argosDesktop?.workspaceState({windows:manager.snapshot()}).catch(()=>{}),100)}
const originalChange=manager.onChange;manager.onChange=windows=>{originalChange(windows);reportWorkspace()};
window.argosDesktop?.onRuntimeEvent(runtimeEvent);
reportWorkspace();setInterval(reportWorkspace,15000);
window.argosDesktop?.onBrowserEvent(event=>{if(event.type==='source-open'){openPanel(isVideo(event.url)?'video':'browser',{url:event.url});return}const w=manager.windows.get(event.id);if(!w)return;const status=w.preview.querySelector('.preview-message');if(event.url){w.address.value=event.url;manager.changed()}if(event.snapshot){let img=w.preview.querySelector('img');if(!img){img=make('img');img.alt='Página en segundo plano';w.preview.prepend(img)}img.src=event.snapshot;status.textContent='Haz clic para interactuar'}if(event.error){status.textContent='No se pudo cargar la página.';window.argosDesktop?.diagnostic({component:'browser',message:'Page load failed for workspace panel '+event.id+' (code '+String(event.error_code??'unknown')+')'}).catch(()=>{})}if(event.ready){status.textContent='Haz clic para interactuar';manager.syncNative()}});
if(window.argosDesktop){sound.unlock().then(()=>sound.chime()).catch(()=>{});window.argosDesktop.voiceState().then(value=>{state(value);if(value.ready)caption(value.listening?'Di «Argos» cuando me necesites.':'Micrófono apagado.');localStorage.removeItem('argos-voice-output-muted')}).catch(()=>state({phase:'error',ready:false,listening:false,error:'La conversación no está conectada.'}))}
else state({phase:'off',ready:false,listening:false,error:'Abre la aplicación ARGOS para conversar por voz.'});
setInterval(()=>$('#clock').textContent=new Date().toLocaleTimeString('es-ES',{hour:'2-digit',minute:'2-digit',second:'2-digit'}),1000);
window.ARGOSWorkspace={openPanel,snapshot:()=>manager.snapshot(),apply:intent=>manager.apply(intent,{actor:'argos'}),phase:()=>root.dataset.phase,voiceState:()=>voice,clear:()=>manager.clear()};

window.addEventListener('error',e=>window.argosDesktop?.diagnostic({component:'renderer',message:String(e.message||'Renderer error').slice(0,800)}).catch(()=>{}));
window.addEventListener('unhandledrejection',e=>window.argosDesktop?.diagnostic({component:'renderer',message:String(e.reason?.message||e.reason||'Unhandled promise').slice(0,800)}).catch(()=>{}));
