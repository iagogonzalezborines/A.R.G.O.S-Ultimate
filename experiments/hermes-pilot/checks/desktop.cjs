// Test-only bootstrap around the unmodified native Electron main entry.
const {app, BrowserWindow} = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
app.setAppPath(path.join(root,'source/apps/desktop'));
const out = path.join(root,'home/.cache/pilot-desktop');
fs.mkdirSync(out,{recursive:true});
let started = Date.now();
app.commandLine.appendSwitch('disable-gpu');
app.commandLine.appendSwitch('ozone-platform','wayland');
let finished = false;
let probing = false;
async function finish(data) {
  if (finished) return;
  finished = true;
  console.log('PILOT_DESKTOP_RESULT '+JSON.stringify({...data, seconds:(Date.now()-started)/1000}));
  // Test controller stops its own process group; never signal other desktop apps.
}
import('../source/apps/desktop/dist/electron-main.mjs').catch(e=>finish({error:String(e)}));
const timer = setInterval(async()=>{
  if (probing || finished) return;
  const windows = BrowserWindow.getAllWindows().filter(w=>!w.isDestroyed());
  const main = windows.find(w=>!w.webContents.getURL().includes('hud=1'));
  if (!main || main.webContents.isLoading()) return;
  try {
    const state = await main.webContents.executeJavaScript(`({title:document.title, body:document.body.innerText.slice(0,2000), sdk:globalThis.__ARGOS_PILOT_SDK__||null, bridge:typeof window.hermesDesktop})`);
    if ((!state.sdk || !state.sdk.rpc?.ok) && Date.now()-started<45000) return;
    probing = true;
    fs.writeFileSync(path.join(out,'sdk-state.json'),JSON.stringify(state,null,2));
    const hud = await main.webContents.executeJavaScript('window.hermesDesktop.hud.open({})');
    for (let wait=0;wait<12;wait++) {
      if (BrowserWindow.getAllWindows().some(w=>w.id!==main.id && w.isVisible())) break;
      await new Promise(r=>setTimeout(r,1000));
    }
    const snapshot = [];
    for (const w of BrowserWindow.getAllWindows()) {
      if (w.isDestroyed()) continue;
      snapshot.push({id:w.id,title:w.getTitle(),url:w.webContents.getURL(),bounds:w.getBounds(),visible:w.isVisible()});
      if (!w.isVisible()) continue;
      const image=await Promise.race([w.webContents.capturePage(),new Promise(r=>setTimeout(()=>r(null),3000))]);
      if (image) fs.writeFileSync(path.join(out,`window-${w.id}.png`),image.toPNG());
    }
    await finish({state,hud,windows:snapshot});
    clearInterval(timer);
  } catch(e) {
    if (Date.now()-started>60000) { await finish({error:String(e)});clearInterval(timer); }
  }
},1000);
setTimeout(()=>{finish({error:'Desktop smoke timeout'});clearInterval(timer)},90000).unref();
