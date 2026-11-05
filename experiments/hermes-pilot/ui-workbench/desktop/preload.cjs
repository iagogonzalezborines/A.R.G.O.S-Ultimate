const {contextBridge,ipcRenderer}=require('electron');
contextBridge.exposeInMainWorld('argosDesktop',{
 diagnostic:payload=>ipcRenderer.invoke('ui:diagnostic',payload),
 browser:payload=>ipcRenderer.invoke('ui:browser',payload),
 layout:layouts=>ipcRenderer.send('ui:layout',layouts),
 fullscreen:()=>ipcRenderer.send('ui:fullscreen'),
 close:()=>ipcRenderer.send('ui:close'),
 voice:payload=>ipcRenderer.invoke('ui:voice',payload),
 voiceState:()=>ipcRenderer.invoke('ui:voice-state'),
 capability:payload=>ipcRenderer.invoke('ui:capability',payload),
 workspaceState:payload=>ipcRenderer.invoke('ui:workspace-state',payload),
 onRuntimeEvent:callback=>{const listener=(_event,data)=>callback(data);ipcRenderer.on('runtime-event',listener);return()=>ipcRenderer.removeListener('runtime-event',listener)},
 onBrowserEvent:callback=>{const listener=(_event,data)=>callback(data);ipcRenderer.on('browser-event',listener);return()=>ipcRenderer.removeListener('browser-event',listener)}
});
