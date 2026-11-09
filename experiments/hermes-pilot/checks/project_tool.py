"""One opt-in tool; project state and execution live in native Hermes."""
S = {'type':'string'}
A = lambda size=20: {'type':'array','maxItems':size,'items':S}
BRIEF = {'type':'object','additionalProperties':False,'required':['objective','requirements','decisions','verification','aliases'],
         'properties':{'objective':S,'requirements':A(),'decisions':A(),'verification':A(),'aliases':{**A(),'description':'All explicit alternate names/nicknames supplied by the user; use [] only when none were given.'}}}
TOOL = {'name':'projects', 'description':
    'catalog lists specialized Engineering capabilities and actual availability. For technical diagrams, architecture, parametric CAD or Blender use catalog then task_create with capability set to the available ID. No extra agent or routing call. '
    'Native persistent Projects and Kanban, independent of this conversation. list/resolve retrieve real registered '
    'projects and aliases. Focused Project Map observations include project/task_id as context to resolve, never authorization; activity answers what Engineering is currently working on across projects without loading their histories. resolve returns the selected brief and revision. For a new idea propose its concrete '
    'name/slug, folder and brief; user grants that folder and local Engineering scope once in the existing review panel. '
    'No agent approval tool. update replaces only the brief, preserving unchanged requirements/decisions, and requires '
    'the latest expected_revision. task_create needs project, expected_revision, title, goal and verification; optional '
    'kind=desktop creates a persistent task for isolated application work and artifact delivery; use desktop.project_open, never Engineering dispatch for it. kind=decision creates a pending user decision; it is never dispatched to Engineering. open_map opens the real interactive project panel. map reads its current native evidence. parents are native prerequisite task IDs. Identical task requests are deduplicated. task_update revises an unstarted task; dependency links/unlinks one prerequisite, both require current project/task revisions. tasks/task read native '
    'status, runs, comments and bounded artifacts. dispatch needs project, task_id, expected_revision and task_revision; '
    'it starts scoped native Codex work and returns promptly. An interrupted attempt requires inspecting effects before '
    'a trusted, bounded retry grant followed by dispatch; repeated dispatch during a run never starts a second worker. Native review is not verified '
    'completion. No arbitrary shell, project deletion, approval, global scan or unrelated history.',
    'inputSchema':{'type':'object','additionalProperties':False,'required':['action'],'properties':{
        'action':{'type':'string','enum':['catalog','list','activity','resolve','propose','update','task_create','task_update','dependency','tasks','task','dispatch','open_map','map']},
        'project':{**S,'description':'Native ID, exact name or alias returned by list/resolve.'},'name':S,'slug':S,
        'path':{**S,'description':'Optional absolute folder. OMIT to use the configured default projects root and slug; never pass a relative slug here.'},
        'register':{'type':'boolean','description':'Default false for a NEW folder. True only when the user explicitly asks to register an EXISTING folder.'},'brief':BRIEF,
        'capability':{**S,'description':'Available catalog ID, only for native Engineering tasks.'},'kind':{'type':'string','enum':['engineering','decision','desktop']},'expected_revision':S,'task_revision':S,'title':S,'goal':S,'verification':A(12),'parents':A(12),'task_id':S,'parent_id':S,'operation':{'type':'string','enum':['link','unlink']}}}}
