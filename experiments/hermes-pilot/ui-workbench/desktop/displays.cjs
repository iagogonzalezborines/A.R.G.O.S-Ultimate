// Only ARGOS-owned windows. Public compositor IPC, never input injection or rules.
const {execFile}=require('node:child_process');
const {promisify}=require('node:util'),crypto=require('node:crypto');
const run=promisify(execFile);
const key=parts=>crypto.createHash('sha256').update(JSON.stringify(parts)).digest('hex').slice(0,20);
const call=async(bin,args)=>{const {stdout}=await run(bin,args,{timeout:1800,maxBuffer:2*1024*1024});return stdout};
const pause=ms=>new Promise(r=>setTimeout(r,ms));
class Displays {
 constructor(screen){this.screen=screen;this.backend=process.env.HYPRLAND_INSTANCE_SIGNATURE?'hyprland':process.env.SWAYSOCK?'sway':process.env.ARGOS_UI_PLATFORM==='x11'||!process.env.WAYLAND_DISPLAY?'x11':'wayland';this.sway=process.env.ARGOS_UI_QA==='1'&&process.env.ARGOS_QA_SWAYMSG?process.env.ARGOS_QA_SWAYMSG:'/usr/bin/swaymsg'}
 async list(){
  let rows;
  if(this.backend==='hyprland'){const monitors=JSON.parse(await call('/usr/bin/hyprctl',['-j','monitors']));rows=monitors.filter(m=>!m.disabled).map(m=>{let width=m.width,height=m.height;if(m.transform%2)[width,height]=[height,width];return {key:key([m.name,m.make,m.model,m.serial]),name:m.name,label:m.description||m.name,bounds:{x:m.x,y:m.y,width:Math.floor(width/m.scale),height:Math.floor(height/m.scale)},scale:m.scale,rotation:m.transform,workspace:m.activeWorkspace.id,native:m.id}})}
  else if(this.backend==='sway'){rows=JSON.parse(await call(this.sway,['-r','-t','get_outputs'])).filter(m=>m.active).map(m=>({key:key([m.name,m.make,m.model,m.serial]),name:m.name,label:m.name,bounds:m.rect,scale:m.scale,rotation:m.transform,native:m.name}))}
  else rows=this.screen.getAllDisplays().map(m=>({key:key([m.label||String(m.id),m.internal]),name:m.label||String(m.id),label:m.label||'Pantalla '+m.id,bounds:m.workArea,scale:m.scaleFactor,rotation:m.rotation,native:m.id}));
  const primary=this.screen.getPrimaryDisplay();rows.sort((a,b)=>a.bounds.x-b.bounds.x||a.bounds.y-b.bounds.y||a.name.localeCompare(b.name));
  const match=rows.find(m=>m.native===primary.id)||rows.find(m=>m.bounds.x===primary.bounds.x&&m.bounds.y===primary.bounds.y)||rows[0];
  return rows.map((m,i)=>({...m,ordinal:i+1,primary:m===match,placement:this.backend!=='wayland'}));
 }
 async own(window){
  const title=window.getTitle();
  if(this.backend==='hyprland'){const rows=JSON.parse(await call('/usr/bin/hyprctl',['-j','clients']));const found=rows.filter(c=>c.pid===process.pid&&c.title===title);if(found.length!==1||!/^0x[0-9a-f]+$/i.test(found[0].address))throw Error('No se pudo identificar inequívocamente la ventana ARGOS');return found[0]}
  if(this.backend==='sway'){const tree=JSON.parse(await call(this.sway,['-r','-t','get_tree'])),found=[];function walk(n,output){if(n.type==='output')output=n.name;if(n.pid===process.pid&&n.name===title)found.push({...n,output});for(const c of [...(n.nodes||[]),...(n.floating_nodes||[])])walk(c,output)}walk(tree);if(found.length!==1||!Number.isSafeInteger(found[0].id))throw Error('No se pudo identificar la superficie ARGOS');return found[0]}
 }
 async place(window,display){
  if(!display)throw Error('La pantalla ya no está disponible');
  if(this.backend==='wayland')throw Error('Este compositor Wayland requiere mover la superficie manualmente');
  let current;
  for(let i=0;i<15;i++){try{current=await this.own(window);break}catch(e){if(i===14)throw e;await pause(60)}}
  if(this.backend==='hyprland'){
   if(!Number.isSafeInteger(display.workspace)||display.workspace<1)throw Error('Pantalla sin workspace normal disponible');
   const cmd=`hl.dsp.window.move({window="address:${current.address}",workspace="${display.workspace}",follow=false})`;
   const result=await call('/usr/bin/hyprctl',['dispatch',cmd]);if(!result.trim().startsWith('ok'))throw Error('Hyprland no confirmó la asignación');
  }else if(this.backend==='sway'){
   if(!/^[-a-zA-Z0-9_]+$/.test(display.name))throw Error('Identidad de salida no admitida');
   const result=JSON.parse(await call(this.sway,['-r',`[con_id=${current.id}] move container to output ${display.name}`]));if(!result.every(r=>r.success))throw Error('Sway rechazó la asignación');
  }else{const b=display.bounds;window.setFullScreen(false);window.setBounds({x:b.x+12,y:b.y+12,width:Math.max(100,b.width-24),height:Math.max(100,b.height-24)})}
  for(let i=0;i<12;i++){await pause(50);if(this.backend==='x11'){if(this.screen.getDisplayMatching(window.getBounds()).id===display.native)return true}else{const next=await this.own(window);if(this.backend==='hyprland'?next.monitor===display.native:next.output===display.name)return true}}
  throw Error('Asignación solicitada pero no verificada; revisa la superficie');
 }
}
module.exports={Displays,key};
