"""Opt-in experimental surface; does not replace the existing projects tool."""
from project_tool import S
NODE={'type':'object','additionalProperties':False,'required':['id','title','capability','parents'],
      'properties':{'id':S,'title':S,'capability':S,'parents':{'type':'array','items':S},
                    'payload':{'type':'object','properties':{'text':S,'format':S},'additionalProperties':False}}}
TOOL={'name':'adaptive','description':'Experimental bounded capability network. catalog reports actually available tools/models. '
      'submit creates a persistent native task and returns immediately. items with format=lines uses deterministic code; '
      'format=prose uses the reviewed small local model and leaves semantics in review. No routing model call. '
      'research.documentation fetches official Python sqlite3/pathlib documentation with timestamps and hashes, no project data sent. files.inventory reads only project root metadata; files.types needs one inventory parent. workflow persists a validated '
      'DAG of those capabilities. canvas exports JSON Canvas from actual task states. status reads evidence; tick explicitly '
      'admits queued work after restart/pressure. cancel requires current task revision. No installations, external accounts '
      'or unrestricted agents. Resolve the project and revision with projects first.',
      'inputSchema':{'type':'object','required':['operation'],'additionalProperties':False,'properties':{
          'operation':{'type':'string','enum':['catalog','submit','status','tick','cancel','workflow','canvas']},
          'project':S,'expected_revision':S,'capability':S,'title':S,'task_id':S,'task_revision':S,
          'payload':NODE['properties']['payload'],'parents':{'type':'array','items':S,'maxItems':8},
          'nodes':{'type':'array','items':NODE,'maxItems':8}}}}
