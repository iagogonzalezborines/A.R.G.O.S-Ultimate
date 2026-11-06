"""Read-only Linux block-device and mounted-filesystem observations."""
import json
import os
from pathlib import Path
import subprocess
import threading
import time

from .machine import USER_HOME

class Storage:
 def __init__(self):self.lock=threading.Lock();self.cached=None;self.observed=0
 def inspect(self,*,refresh=True):
  with self.lock:
   if not refresh and self.cached and time.monotonic()-self.observed<2:return self.cached
   result=subprocess.run(['/usr/bin/lsblk','--json','--bytes','--output','NAME,TYPE,SIZE,FSTYPE,LABEL,MOUNTPOINTS,FSAVAIL,FSUSE%,RO,RM'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=5,check=True)
   tree=json.loads(result.stdout)
   def volume(node):
    mounts=[p for p in node.get('mountpoints',[]) if p and p.startswith('/')]
    value={'device':'/dev/'+node['name'],'name':node['name'],'type':node['type'],'size_bytes':node.get('size'),'filesystem':node.get('fstype'),'label':node.get('label'),'mountpoints':mounts,'mounted':bool(mounts),'read_only':node.get('ro',False),'removable':node.get('rm',False),'available_bytes':None}
    for path in mounts:
     try:s=os.statvfs(path)
     except OSError:continue
     value['available_bytes']=s.f_bavail*s.f_frsize;value['filesystem_size_bytes']=s.f_blocks*s.f_frsize;break
    if node.get('children'):value['children']=[volume(n) for n in node['children']]
    return value
   physical=[];virtual=[]
   for node in tree.get('blockdevices',[]):
    (virtual if node['name'].startswith(('zram','ram','loop')) else physical).append(volume(node))
   self.cached={'disks':physical,'virtual_devices':virtual,'observed_at':time.time(),'mode':'read-only','unmounted_note':'Unmounted partitions have unknown free space and cannot be browsed until mounted.'};self.observed=time.monotonic();return self.cached
 def volumes(self):
  result=[]
  def walk(nodes):
   for n in nodes:result.append(n);walk(n.get('children',[]))
  walk(self.inspect(refresh=False)['disks']);return result
 def roots(self):
  roots={}
  for volume in self.volumes():
   for mount in volume['mountpoints']:
    path=Path(mount)
    if any(path.is_relative_to(base) and path!=Path(base) for base in ['/run/media/'+USER_HOME.name,'/media','/mnt']) and path.is_dir() and os.access(path,os.R_OK|os.X_OK):roots['Disco '+volume['name']]=path;break
  return roots
 def browse(self,device):
  selected=next((n for n in self.volumes() if n['device']==device or n['name']==device),None)
  if selected is None:raise ValueError('Unknown device. Inspect storage first.')
  if not selected['mounted']:raise ValueError('This partition is not mounted. It is visible in storage information, but its files are unavailable until mounted.')
  for path in self.roots().values():
   if str(path) in selected['mountpoints']:return str(path)
  if '/' in selected['mountpoints'] or '/home' in selected['mountpoints']:return str(USER_HOME)
  raise PermissionError('This is a system partition, not an enabled file-browsing location.')
