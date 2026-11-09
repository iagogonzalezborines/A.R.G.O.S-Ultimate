import {artifactView} from './artifact-view.js';
// Presentation only. Native Projects/Kanban own tasks, claims and dependencies.
export async function renderProjectMap(w,{make,manager}){
 let closed=false,busy=false,snapshot=null,selected=null,timer,requestVersion=0,revision='',project=w.spec.text||localStorage.getItem('argos-project-selection')||'';
 const shell=make('div','project-map'),toolbar=make('div','project-toolbar'),chooser=make('select'),refresh=make('button','','Actualizar'),status=make('p','project-status','Cargando proyectos…'),layout=make('div','project-layout'),graph=make('div','project-graph'),detail=make('div','project-detail');
 chooser.setAttribute('aria-label','Proyecto');status.setAttribute('role','status');graph.setAttribute('aria-label','Tareas y dependencias');detail.setAttribute('aria-label','Detalles de la selección');const capabilities=make('button','','Herramientas especializadas');capabilities.onclick=()=>perform(async()=>{const result=await call({action:'catalog'});detail.replaceChildren(make('h2','','Herramientas bajo demanda'));for(const item of result.capabilities){detail.append(make('h3','',item.id),make('p','',({available_validated:'Disponible y validada',installed_unverified:'Instalada sin validar',missing_dependencies:'Faltan dependencias',experimental:'Experimental',unsupported:'No integrada'})[item.status]),make('p','',item.purpose),make('p','',item.reason))}},false);const artifactToggle=make('button','','Ampliar artefacto');artifactToggle.disabled=true;artifactToggle.onclick=()=>{const expanded=shell.classList.toggle('project-artifact-expanded');artifactToggle.textContent=expanded?'Volver a las tareas':'Ampliar artefacto';if(expanded)detail.scrollTop=detail.scrollHeight};toolbar.append(chooser,refresh,capabilities,artifactToggle);layout.append(graph,detail);shell.append(toolbar,status,layout);w.body.append(shell);
 const artifactViews=[];w.visibility=visible=>artifactViews.forEach(v=>v.setVisible(visible));
 const call=args=>window.argosDesktop.capability({tool:'projects',arguments:args});
 const labels={desktop_pending:'Preparada para escritorio',artifacts_delivered:'Archivos entregados · tarea pendiente',queued:'En cola',ready:'En cola',todo:'En cola',running:'En ejecución',blocked:'Bloqueada',review:'Pendiente de revisión',done:'Completada',archived:'Cancelada',failed:'Fallida',decision:'Decisión pendiente',unavailable:'No disponible'};
 function show(value){const pre=make('pre','project-evidence',typeof value==='string'?value:JSON.stringify(value,null,2));detail.append(pre)}
 function button(name,action,mutates=true){const b=make('button','',name);b.onclick=()=>perform(action,mutates);detail.append(b);return b}
 async function perform(action,mutates=true){if(busy||closed)return;busy=true;++requestVersion;const affected=[...detail.querySelectorAll('button')].map(b=>[b,b.disabled]);affected.forEach(([b])=>b.disabled=true);status.textContent='Procesando…';try{await action();if(mutates){revision='';await load()}else status.textContent='Estado nativo actualizado'}catch(e){status.textContent=e.message;status.dataset.error='true'}finally{busy=false;affected.forEach(([b,disabled])=>{if(b.isConnected)b.disabled=disabled})}}
 function inspect(){
  shell.classList.remove('project-artifact-expanded');artifactToggle.disabled=true;artifactToggle.textContent='Ampliar artefacto';artifactViews.splice(0).forEach(v=>v.dispose());delete w.spec.selected_artifact;detail.replaceChildren();if(!snapshot)return;
  const task=snapshot.tasks.find(t=>t.id===selected);
  graph.querySelectorAll('[data-task]').forEach(n=>n.setAttribute('aria-pressed',String(n.dataset.task===selected)));
  if(!task){detail.append(make('h2','',snapshot.project.name),make('p','',snapshot.project.brief.objective));for(const key of ['requirements','decisions','verification']){detail.append(make('h3','',{requirements:'Requisitos',decisions:'Decisiones',verification:'Criterios'}[key]));show(snapshot.project.brief[key]||[])}return}
  detail.append(make('h2','',task.title),make('p','',labels[task.state]||task.state),make('p','',task.goal||task.capability));
  if(task.verification_snapshot_current===false)detail.append(make('p','project-status','Los archivos observados ya no coinciden con esta verificación histórica. Consulta la tarea más reciente.'));
  if(task.blocked_reason)detail.append(make('p','project-status',task.blocked_reason));
  const args={project:snapshot.project.id,task_id:task.id,expected_revision:snapshot.project.revision,task_revision:task.revision};
  if(task.criteria?.length){detail.append(make('h3','','Criterios'));show(task.criteria)}
  if(task.parents.length){detail.append(make('h3','','Depende de'));for(const id of task.parents)button(snapshot.tasks.find(t=>t.id===id)?.title||id,async()=>{selected=id;w.spec.selected_task=id;manager.changed();inspect()},false)}
  const reason=make('textarea');reason.placeholder=task.kind==='decision'?'Tu decisión':'Motivo o corrección para la revisión';reason.setAttribute('aria-label','Decisión o motivo');
  const act=op=>()=>call({action:'map_action',...args,operation:op,...(['decide','accept_semantic','retry','reject'].includes(op)?{reason:reason.value}:{})});
  if(task.kind==='desktop')button('Archivos de escritorio',()=>window.ARGOSWorkspace.openPanel('desktop',{text:JSON.stringify({project:snapshot.project.id,task_id:task.id})}),false);
  if(task.kind==='decision'&&!['done','archived'].includes(task.status)){detail.append(reason);button('Guardar decisión',act('decide'))}
  else if(task.kind==='engineering'&&['blocked','ready','todo'].includes(task.status)&&(!task.runs.length||task.status==='ready')){
   button('Iniciar Engineering',()=>call({action:'dispatch',...args}));
   if(!task.runs.length){const edit=make('details'),summary=make('summary','','Modificar tarea'),title=make('input'),goal=make('textarea'),criteria=make('textarea'),save=make('button','','Guardar tarea');title.value=task.title;title.setAttribute('aria-label','Título de tarea');goal.value=task.goal;goal.setAttribute('aria-label','Objetivo de tarea');criteria.value=task.criteria.join('\n');criteria.setAttribute('aria-label','Criterios de tarea');save.onclick=()=>perform(()=>call({action:'task_update',...args,title:title.value,goal:goal.value,verification:criteria.value.split('\n').filter(Boolean)}));edit.append(summary,title,goal,criteria,save);detail.append(edit)}
  }
  if(task.status==='review'){
   detail.append(reason);
   if(task.kind==='auxiliary')button('Aceptar semántica del borrador',act('accept_semantic'));
   else{const profile=make('select');profile.setAttribute('aria-label','Verificación');for(const [value,name] of [['specialized_integrity','Integridad técnica (revisar requisitos aparte)'],['python_unittest','Pruebas Python'],['model_library_v2','Biblioteca 3D: API y CLI'],['model_library_v1','Biblioteca 3D: solo API']]){const o=make('option','',name);o.value=value;profile.append(o)}profile.value=task.capability?.includes(' · Codex Engineering')?'specialized_integrity':'python_unittest';detail.append(profile);button('Verificar artefactos',()=>call({action:'map_action',...args,operation:'verify',profile:profile.value}));button('Aceptar resultado',act('accept')).disabled=task.controller_evidence.filter(e=>e.kind==='verification'&&e.run_id===task.runs.at(-1)?.id).at(-1)?.passed!==true||task.verification_snapshot_current===false}
   button('Rechazar resultado',act('reject'));
  }
  if(['review','blocked'].includes(task.status)&&task.runs.length){if(!reason.isConnected)detail.append(reason);button('Autorizar un reintento',act('retry'))}
  if(!['done','archived'].includes(task.status))button('Cancelar tarea',act('cancel'));
  detail.append(make('h3','','Ejecución y revisiones'));
  if(!task.runs.length)detail.append(make('p','','Sin intentos.'));
  for(const run of task.runs){const d=make('details'),s=make('summary','',`${run.kind==='state_transition'?'Cambio de estado':'Ejecución'} · registro ${String(run.id).slice(0,10)} · ${run.status} · ${run.outcome||'sin resultado'}`),pre=make('pre','project-evidence',JSON.stringify(run,null,2));d.append(s,pre);detail.append(d)}
  detail.append(make('h3','','Verificación del controlador'));
  if(!task.controller_evidence.length)detail.append(make('p','','Todavía no hay verificación independiente.'));
  for(const evidence of task.controller_evidence){const d=make('details'),label=evidence.kind==='verification'?(evidence.passed?'Pruebas superadas':'Pruebas fallidas'):{accepted:'Resultado aceptado',retry:'Reintento autorizado',rejected:'Revisión rechazada',decision:'Decisión registrada',semantic_acceptance:'Borrador aceptado',desktop_session:'Espacio de aplicación autorizado',desktop_verified:'Documento verificado',desktop_export_intent:'Entrega autorizada',desktop_exported:'Archivo entregado'}[evidence.kind]||evidence.kind;d.append(make('summary','',label),make('pre','project-evidence',JSON.stringify(evidence,null,2)));detail.append(d)}
  detail.append(make('h3','','Artefactos observados'));
  for(const artifact of task.artifacts)button(artifact.path,async()=>{const value=await call({action:'artifact',project:snapshot.project.id,task_id:task.id,path:artifact.path});const file=make('details');file.open=true;file.append(make('summary','',value.path));artifactToggle.disabled=false;const ref={project:snapshot.project.id,task_id:task.id,path:artifact.path};w.spec.selected_artifact=ref;manager.changed();const view=artifactView(value,{ref,refresh:()=>call({action:'artifact',...ref}),onDetach:async ref=>{try{const result=await window.argosDesktop.capability({tool:'workspace',arguments:{action:'visual',operation:'present',ref}});if(!result.ok)throw Error(result.error||'No confirmado')}catch(e){status.textContent=e.message}}});artifactViews.push(view);file.append(view);detail.append(file);detail.scrollTop=detail.scrollHeight},false);
  if(!task.artifacts.length)detail.append(make('p','','Sin archivos declarados y observados.'));
  const events=make('details');events.append(make('summary','','Eventos nativos'),make('pre','project-evidence',JSON.stringify(task.events,null,2)));detail.append(events);
 }
 function draw(){graph.replaceChildren();const p=make('button','project-root',snapshot.project.name+' · Objetivo');p.onclick=()=>{selected=null;delete w.spec.selected_task;manager.changed();inspect()};graph.append(p);
  if(!snapshot.tasks.length)graph.append(make('p','','Aún no hay tareas. Pide a ARGOS que prepare el trabajo de este proyecto.'));
  for(const task of snapshot.tasks){const node=make('button','project-node');node.dataset.task=task.id;node.dataset.state=task.state;node.append(make('strong','',task.title),make('span','',labels[task.state]||task.state),make('small','',task.capability));if(task.parents.length)node.append(make('small','project-edge','↑ '+task.parents.map(id=>snapshot.tasks.find(t=>t.id===id)?.title||id).join(' · ')));node.onclick=()=>{selected=task.id;w.spec.selected_task=task.id;manager.changed();detail.scrollTop=0;inspect()};graph.append(node)}inspect()}
 async function load(){
  if(closed)return;
  const version=++requestVersion;
  try{
   const next=await call({action:'map',...(project?{project}:{})});if(closed||version!==requestVersion)return;
   delete status.dataset.error;
   if(next.needs_selection){snapshot=null;revision='';graph.replaceChildren();detail.replaceChildren();status.textContent=next.projects.length?'Selecciona un proyecto.':'No hay proyectos. Dile a ARGOS qué quieres crear; te mostrará la carpeta y el alcance antes de autorizarlo.';return}
   project=next.project.id;chooser.value=project;localStorage.setItem('argos-project-selection',project);if(w.spec.text!==project){w.spec.text=project;manager.changed()}
   status.textContent='Estado nativo actualizado'+(next.truncated?' · Se muestran hasta 100 tareas por tablero':'');
   if(next.revision!==revision){const focus=detail.contains(document.activeElement);if(focus&&!busy){status.textContent+=' · Hay cambios; pulsa Actualizar al terminar de editar';return}snapshot=next;revision=next.revision;draw()}
  }catch(e){if(!closed&&version===requestVersion){status.textContent='Sin actualizar: '+e.message;status.dataset.error='true'}}
 }
 async function populate(){const available=await call({action:'availability'});if(!available.project_map)throw Error('Project Map no está habilitado en esta instalación.');const result=await call({action:'list'});chooser.replaceChildren();const blank=make('option','','Selecciona proyecto');blank.value='';chooser.append(blank);for(const p of result.projects){const o=make('option','',p.name);o.value=p.id;chooser.append(o)}if(!result.projects.some(p=>p.id===project))project='';chooser.value=project}
 chooser.onchange=()=>{project=chooser.value;w.spec.text=project;delete w.spec.selected_task;manager.changed();selected=null;snapshot=null;revision='';graph.replaceChildren();detail.replaceChildren();status.textContent='Cargando proyecto…';load()};refresh.onclick=async()=>{if(busy)return;try{await populate();revision='';await load()}catch(e){status.textContent=e.message;status.dataset.error='true'}};
 w.dispose=()=>{closed=true;clearTimeout(timer);artifactViews.splice(0).forEach(v=>v.dispose())};
 async function poll(){if(closed)return;if(!w.minimized&&!document.hidden&&!busy)await load();if(!closed)timer=setTimeout(poll,2500)}
 try{await populate();await load();if(!closed)timer=setTimeout(poll,2500)}catch(e){status.textContent=e.message;status.dataset.error='true'}
}
