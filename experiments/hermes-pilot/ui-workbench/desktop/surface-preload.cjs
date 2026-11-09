const {contextBridge,ipcRenderer}=require('electron');
contextBridge.exposeInMainWorld('argosSurface',{state:()=>ipcRenderer.invoke('surface:state'),artifact:()=>ipcRenderer.invoke('surface:artifact'),action:a=>ipcRenderer.invoke('surface:action',a),onChange:fn=>ipcRenderer.on('surface:changed',(_e,v)=>fn(v))});
