"""Disposable native GTK3 event receiver; no accounts, files or network actions."""
import json
from pathlib import Path
import sys
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk, Gdk, GLib

root=Path(sys.argv[1]); root.mkdir(mode=0o700,parents=True,exist_ok=True)
win=Gtk.Window(title='ARGOS desktop isolation fixture '+root.name)
win.set_default_size(440,280);win.set_focus_on_map(False)
box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10);win.add(box)
menu=Gtk.MenuBar();top=Gtk.MenuItem(label='Options');popup=Gtk.Menu();item=Gtk.MenuItem(label='Mark draft');popup.append(item);top.set_submenu(popup);menu.append(top);box.pack_start(menu,False,False,0)
entry=Gtk.Entry();entry.get_accessible().set_name('Draft');entry.set_text('Initial draft');box.pack_start(entry,False,False,0)
button=Gtk.Button(label='Apply draft');box.pack_start(button,False,False,0)
label=Gtk.Label(label='No draft applied');box.pack_start(label,False,False,0)
events={'keys':0,'buttons':0,'motion':0,'focus_in':0,'applied':0,'marked':0,'text':'Initial draft'}
def save():
 events['text']=entry.get_text();(root/'events.json').write_text(json.dumps(events))
def applied(*args):
 events['applied']+=1;label.set_text(entry.get_text());save()
def mark(*args):events['marked']+=1;save()
def event(widget,event,key):events[key]+=1;save();return False
button.connect('clicked',applied);item.connect('activate',mark)
win.add_events(Gdk.EventMask.POINTER_MOTION_MASK|Gdk.EventMask.BUTTON_PRESS_MASK|Gdk.EventMask.KEY_PRESS_MASK|Gdk.EventMask.FOCUS_CHANGE_MASK)
for signal,key in [('key-press-event','keys'),('button-press-event','buttons'),('motion-notify-event','motion'),('focus-in-event','focus_in')]:win.connect(signal,event,key)
entry.connect('changed',lambda *_:save())
win.connect('destroy',Gtk.main_quit);win.show_all();save()
# A rendered widget image is not a compositor screenshot or capture capability.
def render():
 import cairo
 surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,win.get_allocated_width(),win.get_allocated_height())
 win.draw(cairo.Context(surface));surface.write_to_png(str(root/'widget-render.png'));return False
GLib.timeout_add(500,render)
Gtk.main()
