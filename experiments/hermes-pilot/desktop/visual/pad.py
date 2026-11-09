"""Disposable visual scratchpad. Canvas controls intentionally have no AT-SPI UI.

No account, network, shell or host-file integration. State stays in /work.
"""
import json
from pathlib import Path
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gdk

state={'text':'','applied':'','scroll':0,'dropped':False,'dragging':False,'keys':0,'clicks':0,'moves':0}
win=Gtk.Window(title='ARGOS Visual Pad');win.set_default_size(1000,700)
canvas=Gtk.DrawingArea();canvas.set_can_focus(True);win.add(canvas)
canvas.add_events(Gdk.EventMask.BUTTON_PRESS_MASK|Gdk.EventMask.BUTTON_RELEASE_MASK|Gdk.EventMask.POINTER_MOTION_MASK|Gdk.EventMask.SCROLL_MASK|Gdk.EventMask.SMOOTH_SCROLL_MASK|Gdk.EventMask.KEY_PRESS_MASK)
selected=False;editing=False;tile=[80,340]
def save():Path('/work/result.json').write_text(json.dumps(state,ensure_ascii=False));canvas.queue_draw()
def draw(widget,c):
 w=widget.get_allocated_width();h=widget.get_allocated_height()
 def rect(x,y,ww,hh,col):c.set_source_rgb(*col);c.rectangle(x,y,ww,hh);c.fill()
 def text(x,y,value,size=18):c.set_source_rgb(.83,.93,1);c.set_font_size(size);c.move_to(x,y);c.show_text(value)
 rect(0,0,w,h,(.025,.055,.09));text(30,38,'ARGOS · VISUAL PAD',25)
 text(40,82,'Draft');rect(40,95,w*.43,55,(.08,.16,.24));text(50,130,state['text'][-35:] or 'Click here and type',19)
 rect(40,175,190,50,(.05,.31,.49));text(65,208,'Apply draft')
 text(40,265,'Applied: '+state['applied'][-35:]);text(40,305,'Drag the blue card into the green area')
 rect(w*.58,h*.53,w*.35,h*.34,(.04,.27,.19));text(w*.60,h*.57,'DROP HERE')
 rect(tile[0],tile[1],150,75,(.05,.38,.64));text(tile[0]+20,tile[1]+45,'MODEL.STL')
 x=w*.58;c.save();c.rectangle(x,65,w*.36,235);c.clip();rect(x,65,w*.36,235,(.06,.12,.18))
 for i in range(7):text(x+12,93+i*31,'Item '+str(state['scroll']+i+1))
 c.restore();text(x,330,'Scroll list · offset '+str(state['scroll']))
 text(40,h-30,'Dropped: '+str(state['dropped'])+' · isolated disposable workspace',16)
 return False

def down(_,event):
 global editing,selected
 canvas.grab_focus();state['clicks']+=1;x,y=event.x,event.y
 editing=40<=x<=40+canvas.get_allocated_width()*.43 and 95<=y<=150
 if 40<=x<=230 and 175<=y<=225:state['applied']=state['text']
 if tile[0]<=x<=tile[0]+150 and tile[1]<=y<=tile[1]+75:state['dragging']=True
 save();return True

def motion(_,event):
 state['moves']+=1
 if state['dragging']:tile[:]=[event.x-75,event.y-35]
 save();return True

def up(_,event):
 if state['dragging']:
  state['dropped']=event.x>=canvas.get_allocated_width()*.58 and event.y>=canvas.get_allocated_height()*.53
 state['dragging']=False;save();return True

def scroll(_,event):
 delta=1 if event.direction==Gdk.ScrollDirection.DOWN else -1
 if event.direction==Gdk.ScrollDirection.SMOOTH:
  ok,dx,dy=event.get_scroll_deltas();delta=1 if dy>0 else -1
 state['scroll']=max(0,min(50,state['scroll']+delta));save();return True

def key(_,event):
 global selected
 state['keys']+=1
 if not editing:save();return False
 if event.state&Gdk.ModifierType.CONTROL_MASK:
  if event.keyval in (Gdk.KEY_a,Gdk.KEY_A):selected=True
  elif event.keyval==Gdk.KEY_Return:state['applied']=state['text']
 elif event.keyval==Gdk.KEY_BackSpace:state['text']='' if selected else state['text'][:-1];selected=False
 else:
  value=Gdk.keyval_to_unicode(event.keyval)
  if value>=32 and len(state['text'])<2048:
   state['text']=('' if selected else state['text'])+chr(value);selected=False
 save();return True

canvas.connect('draw',draw);canvas.connect('button-press-event',down);canvas.connect('button-release-event',up);canvas.connect('motion-notify-event',motion);canvas.connect('scroll-event',scroll);canvas.connect('key-press-event',key)
win.connect('destroy',Gtk.main_quit);win.show_all();save();Gtk.main()
