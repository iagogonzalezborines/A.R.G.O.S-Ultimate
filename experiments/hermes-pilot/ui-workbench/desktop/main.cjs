const {app,BrowserWindow,WebContentsView,ipcMain,session,screen,Menu}=require('electron');
const path=require('node:path');
const fs=require('node:fs'),http=require('node:http'),dns=require('node:dns').promises,net=require('node:net');
const ROOT=path.resolve(__dirname,'..'),ORIGIN=process.env.ARGOS_UI_QA==='1'&&process.env.ARGOS_UI_ORIGIN?process.env.ARGOS_UI_ORIGIN:'http://127.0.0.1:42720';
const allowedHosts=new Set(['science.nasa.gov','www.nasa.gov','en.wikipedia.org','es.wikipedia.org','www.swpc.noaa.gov']);
function allowedURL(value){try{const u=new URL(value),h=u.hostname;return u.protocol==='https:'&&h.includes('.')&&!/^[0-9.]+$/.test(h)&&!h.startsWith('[')&&!/(^|\.)(localhost|local|internal|test|invalid)$/.test(h)&&!u.username&&!u.password&&(!u.port||u.port==='443')}catch{return false}}
app.setPath('userData',path.join(ROOT,'state',process.env.ARGOS_UI_QA==='1'?'electron-qa':'electron'));
app.setPath('sessionData',path.join(ROOT,'state',process.env.ARGOS_UI_QA==='1'?'electron-session-qa':'electron-session'));
app.enableSandbox();
app.setName('ARGOS');app.setDesktopName('argos-workspace.desktop');
if(!app.requestSingleInstanceLock())app.quit();
app.on('second-instance',()=>{if(win&&!win.isDestroyed()){if(win.isMinimized())win.restore();win.show();win.focus()}});
// This host's Wayland/GPU compositor returned UnknownVizError on capture.
// Keep the isolated presentation pilot on the verified software rendering path.
app.commandLine.appendSwitch('disable-gpu');
app.commandLine.appendSwitch('ozone-platform',process.env.ARGOS_UI_PLATFORM==='x11'?'x11':process.env.WAYLAND_DISPLAY?'wayland':'x11');
if(process.env.ARGOS_UI_QA==='1')app.commandLine.appendSwitch('mute-audio');
let win,eventsRequest,reconnect,lastEvent=0;const views=new Map();
function token(){return fs.readFileSync(path.join(ROOT,'private/presentation.token'),'utf8').trim()}
function request(route,payload){return new Promise((resolve,reject)=>{const body=payload?JSON.stringify(payload):null;const req=http.request(ORIGIN+route,{method:body?'POST':'GET',headers:{Authorization:'Bearer '+token(),...(body?{'Content-Type':'application/json','Content-Length':Buffer.byteLength(body)}:{})}},response=>{let text='';response.on('data',c=>{text+=c;if(text.length>2400000)req.destroy()});response.on('end',()=>{try{const result=JSON.parse(text);if(response.statusCode>=400)throw Error(result.error||'Request rejected');resolve(result)}catch(e){reject(e)}})});req.on('error',reject);req.setTimeout(route==='/api/capability'&&payload?.tool==='files'&&['confirm','paste'].includes(payload.arguments?.action)?0:15000,()=>req.destroy(Error('Workspace host timeout')));if(body)req.write(body);req.end()})}
function subscribe(){if(!win||win.isDestroyed())return;let buffer='';eventsRequest=http.get(ORIGIN+'/events',{headers:{Authorization:'Bearer '+token(),...(lastEvent?{'Last-Event-ID':String(lastEvent)}:{})}},response=>{response.on('data',chunk=>{buffer+=chunk;let at;while((at=buffer.indexOf('\n\n'))>=0){const block=buffer.slice(0,at);buffer=buffer.slice(at+2);const line=block.split('\n').find(l=>l.startsWith('data: '));if(line)try{const event=JSON.parse(line.slice(6));lastEvent=event.sequence;if(win&&!win.isDestroyed())win.webContents.send('runtime-event',event)}catch{}}});response.on('end',()=>{reconnect=setTimeout(subscribe,1000)})});eventsRequest.on('error',()=>{reconnect=setTimeout(subscribe,1000)})}
function trusted(event){return win&&!win.isDestroyed()&&event.sender===win.webContents&&event.senderFrame===win.webContents.mainFrame&&event.senderFrame.url.startsWith(ORIGIN+'/')}
function emit(data){if(win&&!win.isDestroyed())win.webContents.send('browser-event',data)}
function secure(contents){contents.setWindowOpenHandler(({url})=>{if(allowedURL(url))emit({type:'source-open',url});return {action:'deny'}});contents.on('will-navigate',(event,url)=>{if(!allowedURL(url))event.preventDefault()});contents.on('will-redirect',(event,url)=>{if(!allowedURL(url))event.preventDefault()})}
async function snapshot(id,view){try{const image=await view.webContents.capturePage();if(!image.isEmpty())emit({id,snapshot:image.resize({width:1000}).toDataURL()})}catch{}}
app.whenReady().then(()=>{
 if(!app.hasSingleInstanceLock())return;
 Menu.setApplicationMenu(null);const area=screen.getPrimaryDisplay().workAreaSize;
 win=new BrowserWindow({width:Math.min(1540,area.width-30),height:Math.min(940,area.height-30),minWidth:850,minHeight:620,title:'ARGOS · Workspace',backgroundColor:'#01050a',frame:false,show:true,webPreferences:{preload:path.join(__dirname,'preload.cjs'),contextIsolation:true,nodeIntegration:false,sandbox:true,webviewTag:false,webSecurity:true,autoplayPolicy:'no-user-gesture-required',backgroundThrottling:true}});
 win.webContents.setWindowOpenHandler(({url})=>{if(allowedURL(url))emit({type:'source-open',url});return {action:'deny'}});
 win.webContents.on('will-navigate',(event,url)=>{if(!url.startsWith(ORIGIN+'/'))event.preventDefault()});
 win.webContents.on('did-finish-load',subscribe);
 ipcMain.handle('ui:diagnostic',(event,payload)=>{if(!trusted(event)||!payload||Object.keys(payload).some(k=>!['component','message'].includes(k))||typeof payload.message!=='string'||payload.message.length>800)throw Error('Invalid diagnostic');return request('/api/diagnostic',payload)});
 ipcMain.handle('ui:voice-state',event=>{if(!trusted(event))throw Error('Untrusted sender');return request('/voice-state')});
 ipcMain.handle('ui:workspace-state',(event,payload)=>{if(!trusted(event))throw Error('Untrusted sender');return request('/api/workspace',payload)});
 ipcMain.handle('ui:capability',(event,payload)=>{if(!trusted(event)||!payload||!['files','workspace','storage','media','development','apps'].includes(payload.tool))throw Error('Untrusted capability');return request('/api/capability',payload)});
 ipcMain.handle('ui:voice',(event,payload)=>{if(!trusted(event)||!payload||!['listen','interrupt','output'].includes(payload.op)||Object.keys(payload).some(k=>!['op','enabled'].includes(k)))throw Error('Unsupported voice control');return request('/api/voice',payload)});
 const remoteSession=session.fromPartition('argos-pilot-public-sources');
 remoteSession.setPermissionRequestHandler((wc,permission,callback)=>callback(false));remoteSession.setPermissionCheckHandler(()=>false);remoteSession.on('will-download',event=>event.preventDefault());
 const dnsCache=new Map();
 function privateIP(ip){if(net.isIP(ip)===4){const p=ip.split('.').map(Number);return p[0]===0||p[0]===10||p[0]===127||p[0]>=224||(p[0]===169&&p[1]===254)||(p[0]===172&&p[1]>=16&&p[1]<=31)||(p[0]===192&&(p[1]===168||(p[1]===0&&p[2]===0)))||(p[0]===100&&p[1]>=64&&p[1]<=127)||(p[0]===198&&[18,19].includes(p[1]))}return /^::|^f[cd]|^fe[89ab]|^ff|^2001:db8/i.test(ip)}
 remoteSession.webRequest.onBeforeRequest(async(details,callback)=>{try{const u=new URL(details.url),h=u.hostname;if(['data:','blob:'].includes(u.protocol))return callback({cancel:false});if(u.protocol!=='https:'||/(^|\.)(localhost|local|internal)$/.test(h))return callback({cancel:true});let cached=dnsCache.get(h);if(!cached||cached.until<Date.now()){const addresses=net.isIP(h)?[{address:h}]:await dns.lookup(h,{all:true});cached={allowed:addresses.length>0&&addresses.every(a=>!privateIP(a.address)),until:Date.now()+60000};if(dnsCache.size>128)dnsCache.clear();dnsCache.set(h,cached)}callback({cancel:!cached.allowed})}catch{callback({cancel:true})}});

 ipcMain.handle('ui:browser',async(event,payload)=>{
  if(!trusted(event)||!payload||typeof payload!=='object'||!/^[-a-zA-Z0-9]{1,64}$/.test(payload.id)||!['open','close','back','reload'].includes(payload.type))throw Error('Unsupported browser command');
  let view=views.get(payload.id);
  if(payload.type==='close'){if(view){win.contentView.removeChildView(view);view.webContents.close();views.delete(payload.id)}return {ok:true}}
  if(payload.type==='open'){
   if(!allowedURL(payload.url))throw Error('Unsupported source URL');
   if(!view){if(views.size>=4)throw Error('Close a browser panel before opening another');view=new WebContentsView({webPreferences:{session:remoteSession,autoplayPolicy:payload.kind==='video'?'no-user-gesture-required':'document-user-activation-required',nodeIntegration:false,contextIsolation:true,sandbox:true,webSecurity:true,webviewTag:false}});views.set(payload.id,view);win.contentView.addChildView(view);view.setVisible(false);secure(view.webContents);view.webContents.on('did-finish-load',()=>{emit({id:payload.id,ready:true,url:view.webContents.getURL()});snapshot(payload.id,view)});view.webContents.on('did-fail-load',(e,code)=>{if(code!==-3)emit({id:payload.id,error:true,error_code:code})});view.webContents.on('did-navigate-in-page',()=>emit({id:payload.id,url:view.webContents.getURL()}));}
   view.webContents.loadURL(payload.url).catch(()=>emit({id:payload.id,error:true}));return {ok:true}
  }
  if(!view)return {ok:false};if(payload.type==='back'&&view.webContents.navigationHistory.canGoBack())view.webContents.navigationHistory.goBack();if(payload.type==='reload')view.webContents.reload();return {ok:true}
 });
 ipcMain.on('ui:layout',(event,layouts)=>{if(!trusted(event)||!Array.isArray(layouts)||layouts.length>8)return;const valid=new Map(layouts.filter(x=>x&&typeof x.id==='string'&&['x','y','width','height'].every(k=>Number.isFinite(x[k]))).map(x=>[x.id,x]));const b=win.getContentBounds();for(const [id,view] of views){const l=valid.get(id),visible=!!l?.visible&&l.width>0&&l.height>0;if(!visible&&view.getVisible())snapshot(id,view);if(l)view.setBounds({x:Math.max(0,Math.min(b.width,Math.round(l.x))),y:Math.max(0,Math.min(b.height,Math.round(l.y))),width:Math.max(1,Math.min(b.width,Math.round(l.width))),height:Math.max(1,Math.min(b.height,Math.round(l.height)))});view.setVisible(visible)}});
 ipcMain.on('ui:fullscreen',event=>{if(trusted(event))win.setFullScreen(!win.isFullScreen())});ipcMain.on('ui:close',event=>{if(trusted(event))win.close()});
 win.on('closed',()=>{clearTimeout(reconnect);eventsRequest?.destroy();for(const view of views.values())if(!view.webContents.isDestroyed())view.webContents.close();views.clear();win=null});
 win.loadURL(ORIGIN+'/');
});
app.on('window-all-closed',()=>app.quit());
