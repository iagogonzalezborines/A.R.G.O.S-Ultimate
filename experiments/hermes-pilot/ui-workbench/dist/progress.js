// Presentation of observed work only; no simulated completion percentages.
export function renderProgress(w,make){
 const pad=make('div','panel-pad process-panel');
 const label=make('div','eyebrow-blue','ARGOS / PROCESO');
 const status=make('p','progress-copy',w.spec.status||'Iniciando…');
 const bar=make('progress','process-meter');bar.setAttribute('aria-label','Proceso en curso');
 const counts=make('div','process-counts');
 const sources=make('div','process-sources');sources.setAttribute('aria-live','polite');
 pad.append(label,status,bar,counts,sources);w.body.append(pad);
 updateProgress(w,w.spec.process||{},make);
}
export function updateProgress(w,data,make){
 w.spec.process={...(w.spec.process||{}),...data};const p=w.spec.process;
 const status=w.body.querySelector('.progress-copy'),bar=w.body.querySelector('progress');
 if(!bar)return;
 if(p.status)status.textContent=p.status;
 const ended=['completed','failed','cancelled'].includes(p.phase);
 bar.max=1;if(ended)bar.value=1;else bar.removeAttribute('value');
 bar.setAttribute('aria-label',ended?'Proceso finalizado':'Proceso en curso');
 w.body.dataset.processPhase=p.phase||'running';
 w.body.querySelector('.process-counts').textContent=`${p.found_sources??p.selected_sources??0} ${p.language==='en'?'found':'encontradas'} · ${p.selected_sources||0} ${p.language==='en'?'selected':'seleccionadas'} · ${p.opened_windows||0} ↗`;
 const list=w.body.querySelector('.process-sources');list.replaceChildren();
 for(const source of (p.sources||[])){
  const row=make('div','process-source');
  row.append(make('span','source-state',source.stage==='opened'?'↗':source.stage==='opening'?'…':'•'),make('span','',source.title));
  list.append(row);
 }
}
