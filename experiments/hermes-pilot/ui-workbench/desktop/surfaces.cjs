// Presentation state only. Projects owns artifacts; no execution, conversation or approvals here.
const {BrowserWindow,ipcMain,screen,Tray,Menu,nativeImage,globalShortcut,app}=require('electron');
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {Displays}=require('./displays.cjs');
class Surfaces {
 constructor({main,root,origin,request,report,send}){Object.assign(this,{main,root,origin,request,report,send});this.displays=new Displays(screen);this.items=new Map();this.hidden=false;this.rows=[];this.queue=Promise.resolve();this.file=path.join(root,'state/surfaces.json');this.stopping=false;
  ipcMain.handle('surface:state',e=>this.stateFor(this.sender(e)));
  ipcMain.handle('surface:artifact',async e=>{const s=this.sender(e);if(!s.ref)return null;return this.artifact(s.ref)});
  ipcMain.handle('surface:action',(e,a)=>{const s=this.sender(e);if(!a||Object.keys(a).some(k=>!['operation','display'].includes(k))||!['move','return','close','fullscreen'].includes(a.operation))throw Error('Acción no admitida');return this.run({...a,id:s.id})});
  for(const name of ['display-added','display-removed','display-metrics-changed'])screen.on(name,()=>{clearTimeout(this.changedTimer);this.changedTimer=setTimeout(()=>this.run({operation:'refresh'}).catch(()=>{}),250)});
  // Relaunch is always a recovery path, even without a tray host or shortcut support.
  try{this.tray=new Tray(nativeImage.createFromPath(path.join(root,'dist/assets/argos.svg')));this.tray.setToolTip('ARGOS · Mostrar workspace');this.tray.setContextMenu(Menu.buildFromTemplate([{label:'Mostrar ARGOS',click:()=>this.run({operation:'show'})},{label:'Ocultar workspace',click:()=>this.run({operation:'hide'})},{type:'separator'},{label:'Salir de ARGOS',click:()=>app.quit()}]));this.tray.on('click',()=>this.run({operation:'show'}))}catch{}
  try{this.shortcut=globalShortcut.register('CommandOrControl+Alt+A',()=>this.run({operation:this.hidden?'show':'hide'}))}catch{this.shortcut=false}
  app.on('before-quit',()=>{this.stopping=true;clearTimeout(this.changedTimer);this.save();this.tray?.destroy();globalShortcut.unregister('CommandOrControl+Alt+A')});
 }
 sender(e){const s=[...this.items.values()].find(s=>s.win.webContents===e.sender);if(!s||e.senderFrame!==s.win.webContents.mainFrame||e.senderFrame.url!==this.origin+'/surface.html')throw Error('Untrusted surface');return s}
 async artifact(ref){if(!ref||Object.keys(ref).sort().join(',')!=='path,project,task_id'||!Object.values(ref).every(v=>typeof v==='string')||!ref.path||ref.path.length>2048||!/^[-\w]{1,80}$/.test(ref.project)||!/^[-\w]{1,80}$/.test(ref.task_id))throw Error('Referencia de artefacto inválida');return this.request('/api/capability',{tool:'projects',arguments:{action:'artifact',...ref}})}
 stateFor(s){return {id:s.id,ref:s.ref,display:s.display,error:s.error||'',displays:this.rows,title:s.ref?.path||'Superficie disponible'}}
 snapshot(){return {hidden:this.hidden,main_visible:this.main.isVisible(),backend:this.displays.backend,recovery:{launcher:true,tray_created:!!this.tray,shortcut:this.shortcut?'Ctrl+Alt+A':null},displays:this.rows.map(({workspace,native,...r})=>r),surfaces:[...this.items.values()].map(s=>({id:s.id,ref:s.ref,display:s.display,preferred_display:s.preferred,error:s.error||'',visible:s.win.isVisible(),placement_verified:!s.error&&!s.pending_display}))}}
 save(){if(this.stopping||this.restoring)return;const value={version:1,surfaces:[...this.items.values()].map(s=>({id:s.id,ref:s.ref,display:s.preferred||s.display}))};fs.mkdirSync(path.dirname(this.file),{recursive:true});fs.writeFileSync(this.file+'.tmp',JSON.stringify(value),{mode:0o600});fs.renameSync(this.file+'.tmp',this.file)}
 async initialize(){this.restoring=true;try{await this.refresh();let saved;try{if(fs.statSync(this.file).size<64000)saved=JSON.parse(fs.readFileSync(this.file,'utf8'))}catch{}if(saved?.version===1&&Array.isArray(saved.surfaces))for(const row of saved.surfaces.slice(0,8)){if(this.stopping)break;try{const s=await this.create(row.ref,row.display,row.id);s.restored=true}catch{}}}finally{this.restoring=false;if(!this.stopping){this.save();await this.publish()}}}
 async publish(){for(const s of this.items.values())if(!s.win.isDestroyed())s.win.webContents.send('surface:changed',this.stateFor(s));await this.report(this.snapshot())}
 async refresh(){this.rows=await this.displays.list();if(!this.rows.length)throw Error('No hay pantallas disponibles');this.main.setMinimumSize(Math.max(100,Math.min(850,...this.rows.map(r=>r.bounds.width))),Math.max(100,Math.min(620,...this.rows.map(r=>r.bounds.height))));for(const s of this.items.values()){const wanted=this.rows.find(r=>r.key===s.preferred),current=this.rows.find(r=>r.key===s.display);if(wanted&&wanted.key!==s.display||!current||s.pending_display){const target=(wanted||current||this.rows.find(r=>r.primary)||this.rows[0]).key;if(!s.win.isVisible()){s.pending_display=target;continue}try{await this.move(s,target,false)}catch(e){s.error=e.message}}}}
 async create(ref,display,id){if(this.stopping)throw Error('Workspace cerrándose');if(this.items.size>=8)throw Error('Cierra una superficie antes de abrir otra (máximo ocho)');if(ref&&(!/^[\w-]{1,80}$/.test(ref.project)||!/^[\w-]{1,80}$/.test(ref.task_id)||typeof ref.path!=='string'||ref.path.length>2048||Object.keys(ref).some(k=>!['project','task_id','path'].includes(k))))throw Error('Referencia de artefacto inválida');
  id=/^[a-f0-9]{16}$/.test(id||'')&&!this.items.has(id)?id:crypto.randomBytes(8).toString('hex');const target=this.rows.find(r=>r.key===display)||this.rows.find(r=>r.primary)||this.rows[0];
  const w=new BrowserWindow({width:Math.min(1000,target.bounds.width),height:Math.min(740,target.bounds.height),minWidth:320,minHeight:240,title:'ARGOS Surface '+id,show:false,backgroundColor:'#030b15',webPreferences:{preload:path.join(__dirname,'surface-preload.cjs'),contextIsolation:true,nodeIntegration:false,sandbox:true,webSecurity:true,backgroundThrottling:true}});
  w.on('page-title-updated',e=>e.preventDefault());w.webContents.setWindowOpenHandler(()=>({action:'deny'}));w.webContents.on('will-navigate',e=>e.preventDefault());w.webContents.on('will-frame-navigate',e=>{if(!e.isMainFrame&&e.frame?.url?.startsWith(this.origin+'/project-preview/'))e.preventDefault()});
  const s={id,win:w,ref:ref||null,display:target.key,preferred:display||target.key};this.items.set(id,s);w.on('closed',()=>{this.items.delete(id);if(!this.stopping){this.save();this.publish().catch(()=>{})}});
  await w.loadURL(this.origin+'/surface.html');if(!this.hidden){w.showInactive();try{await this.move(s,target.key,false)}catch(e){s.error=e.message}}else s.pending_display=target.key;this.save();return s;
 }
 async move(s,display,remember=true){const target=this.rows.find(r=>r.key===display);if(!target)throw Error('Inspecciona las pantallas y usa una referencia vigente');if(remember)s.preferred=display;if(!s.win.isVisible()){s.pending_display=display;s.error='Asignación pendiente hasta mostrar la superficie';this.save();return}await this.displays.place(s.win,target);s.display=display;s.error='';delete s.pending_display;this.save()}
 run(a){const next=this.queue.then(()=>this.apply(a));this.queue=next.catch(()=>{});return next}
 async apply(a){if(!a||Object.keys(a).some(k=>!['operation','id','display','ref','other'].includes(k)))throw Error('Campos de presentación inválidos');await this.refresh();let s=a.id?this.items.get(a.id):null;
  switch(a.operation){
   case 'inspect':case 'refresh':break;
   case 'hide':this.hidden=true;this.main.hide();for(const s of this.items.values())s.win.hide();break;
   case 'show':this.hidden=false;this.main.show();for(const s of this.items.values())s.win.showInactive();await this.refresh();break;
   case 'present':{if(!a.ref)throw Error('Selecciona un artefacto real');await this.artifact(a.ref);s=[...this.items.values()].find(s=>JSON.stringify(s.ref)===JSON.stringify(a.ref));if(!s){s=[...this.items.values()].find(s=>!s.ref&&(!a.display||s.display===a.display));if(s){s.ref=a.ref;await s.win.reload()}else s=await this.create(a.ref,a.display)}this.hidden=false;s.win.showInactive();if(a.display||s.pending_display)await this.move(s,a.display||s.pending_display);break}
   case 'distribute':if(this.rows.length>9)throw Error('Máximo ocho superficies adicionales');this.main.show();await this.displays.place(this.main,this.rows.find(r=>r.primary));for(const d of this.rows.filter(r=>!r.primary))if(![...this.items.values()].some(s=>s.display===d.key))await this.create(null,d.key);this.hidden=false;this.main.show();for(const s of this.items.values())s.win.showInactive();break;
   case 'primary':this.hidden=false;this.main.show();for(const s of this.items.values())s.win.showInactive();await this.displays.place(this.main,this.rows.find(r=>r.primary));for(const s of this.items.values())await this.move(s,this.rows.find(r=>r.primary).key);break;
   case 'move':if(!s)throw Error('Superficie no disponible');await this.move(s,a.display);break;
   case 'swap':{const other=this.items.get(a.other);if(!s||!other||s===other)throw Error('Elige dos superficies distintas');const target=s.display;await this.move(s,other.display);await this.move(other,target);break}
   case 'only':if(!s)throw Error('Elige la superficie que debe quedar visible');this.main.hide();for(const item of this.items.values())item===s?item.win.showInactive():item.win.hide();await this.refresh();break;
   case 'fullscreen':if(!s)throw Error('Superficie no disponible');s.win.setFullScreen(!s.win.isFullScreen());break;
   case 'return':if(!s?.ref)throw Error('La superficie no tiene artefacto');this.main.show();this.hidden=false;this.send({type:'artifact.integrate',ref:s.ref});s.win.close();break;
   case 'close':if(!s)throw Error('Superficie no disponible');s.win.close();break;
   default:throw Error('Operación visual desconocida');
  }
  this.save();await this.publish();return {ok:true,...this.snapshot(),...(s?{selected_surface:s.id}:{})};
 }
}
module.exports={Surfaces};
