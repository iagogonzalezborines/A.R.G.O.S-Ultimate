import { host, useValue } from '@hermes/plugin-sdk';
import { jsx, jsxs } from 'react/jsx-runtime';

function PilotPane() {
  const gateway = useValue(host.state.gateway);
  return jsxs('div', {style:{padding:20,color:'#78dcca'},children:[
    jsx('div',{style:{fontSize:48},children:'◉'}),
    jsx('strong',{children:'ARGOS · isolated pilot'}),
    jsx('p',{children:`Native Hermes gateway: ${gateway}`}),
    jsx('p',{children:'No operational ARGOS connection. No user projects.'})
  ]});
}

export default {
  id:'argos-pilot', name:'ARGOS pilot',
  register(ctx) {
    globalThis.__ARGOS_PILOT_SDK__ = {registered:true,gateway:'not-probed'};
    ctx.register({id:'pane',area:'panes',title:'ARGOS pilot',data:{placement:'right',width:'300px'},render:()=>jsx(PilotPane,{})});
    ctx.register({id:'status',area:'statusBar.right',render:()=>jsx('span',{children:'ARGOS pilot'})});
    // Read the same native session list as the host, without creating another owner.
    const probe=()=>{
      const gateway=host.state.gateway.get();
      globalThis.__ARGOS_PILOT_SDK__.gateway=gateway;
      if (gateway!=='open') return;
      host.request('session.list',{}).then(value=>{
        globalThis.__ARGOS_PILOT_SDK__.rpc={ok:true,sessions:value};
      }).catch(error=>{
        globalThis.__ARGOS_PILOT_SDK__.rpc={ok:false,error:String(error)};
        if (attempts++ < 3) retry=setTimeout(probe,3000);
      });
    };
    let attempts=0;
    let retry;
    const stop=host.state.gateway.subscribe(probe);
    return ()=>{stop();clearTimeout(retry)};
  }
};
