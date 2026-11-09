"""Validate transient presentation requests; no task or project state authority."""
import re
OPERATIONS={'inspect','hide','show','present','distribute','primary','move','swap','only','return','close','fullscreen'}
def command(args):
    allowed={'action','operation','id','display','ref','other'}
    if not isinstance(args,dict) or set(args)-allowed or args.get('action')!='visual' or args.get('operation') not in OPERATIONS:raise ValueError('Invalid visual workspace request')
    for field in ('id','other'):
        if field in args and (not isinstance(args[field],str) or not re.fullmatch('[a-f0-9]{16}',args[field])):raise ValueError('Use an observed surface ID')
    if 'display' in args and (not isinstance(args['display'],str) or not re.fullmatch('[a-f0-9]{20}',args['display'])):raise ValueError('Use an observed display key')
    if 'ref' in args:
        r=args['ref']
        if not isinstance(r,dict) or set(r)!={'project','task_id','path'} or any(not isinstance(v,str) for v in r.values()) or not re.fullmatch('[A-Za-z0-9_-]{1,80}',r['project']) or not re.fullmatch('[A-Za-z0-9_-]{1,80}',r['task_id']) or not 0<len(r['path'])<=2048:raise ValueError('Use a concrete native task artifact')
    if args['operation']=='present' and 'ref' not in args:raise ValueError('Choose an actual project artifact')
    if args['operation'] in {'move','swap','only','return','close','fullscreen'} and 'id' not in args:raise ValueError('Choose an observed surface')
    if args['operation']=='move' and 'display' not in args:raise ValueError('Choose a display')
    if args['operation']=='swap' and 'other' not in args:raise ValueError('Choose the second surface')
    return {k:v for k,v in args.items() if k!='action'}
