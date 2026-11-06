"""Validated DAG and JSON Canvas projection. Native task records remain authoritative."""
from adaptive.capabilities import REGISTRY,validate_payload
from projects.policy import text


def validate(nodes):
    if not isinstance(nodes,list) or not 1<=len(nodes)<=8:raise ValueError('Use one to eight nodes')
    mapped={}
    for node in nodes:
        if not isinstance(node,dict) or set(node)-{'id','title','capability','parents','payload'}:raise ValueError('Invalid node fields')
        ident=text(node.get('id'),40)
        if ident in mapped or node.get('capability') not in REGISTRY:raise ValueError('Duplicate node or unregistered capability')
        text(node.get('title'),160)
        if not isinstance(node.get('parents'),list) or len(node['parents'])>8 or any(not isinstance(p,str) for p in node['parents']) or len(set(node['parents']))!=len(node['parents']):raise ValueError('Invalid dependencies')
        mapped[ident]={**node,'payload':validate_payload(node['capability'],node.get('payload',{}))}
    for node in mapped.values():
        if node['capability']=='files.types' and (len(node['parents'])!=1 or mapped.get(node['parents'][0],{}).get('capability')!='files.inventory'):
            raise ValueError('Types requires exactly one inventory dependency')
    ordered=[];done=set()
    while len(done)<len(mapped):
        ready=[n for key,n in mapped.items() if key not in done and set(n['parents'])<=done]
        if not ready:raise ValueError('Cycle or missing dependency')
        for node in ready:ordered.append(node);done.add(node['id'])
    return ordered


def canvas(tasks):
    ids={t['id'] for t in tasks}
    return {'nodes':[{'id':t['id'],'type':'text','x':(i%3)*340,'y':(i//3)*200,'width':310,'height':160,
                      'color':'5','text':t['title']+'\n'+t['capability']+'\nNative status: '+t['status']}
                     for i,t in enumerate(tasks)],
            'edges':[{'id':p+'-'+t['id'],'fromNode':p,'toNode':t['id'],'fromSide':'right','toSide':'left'}
                     for t in tasks for p in t['parents'] if p in ids]}
