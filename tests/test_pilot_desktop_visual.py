"""Isolated desktop policy tests; no display/input/audio or user files."""
import importlib
import json
import os
import threading
import time
import unittest
from unittest.mock import patch
import test_pilot_desktop as fixture

v=importlib.import_module('argos_desktop_tests.desktop_visual')
m=fixture.m

class VisualTests(unittest.TestCase):
    setUp=fixture.DesktopTests.setUp

    def test_profile_requires_trusted_single_use_review(self):
        d=self.desktop;d.available=True;d.visual.ready=True
        args={'action':'visual_open','application':'pad'}
        p=d.request(args)
        self.assertEqual(d.request(args)['proposal_id'],p['proposal_id'])
        self.assertEqual(d.scopes,{})
        with self.assertRaises(PermissionError):d.request({'action':'confirm','proposal_id':p['proposal_id'],'approve':True})
        with patch.object(d.visual,'launch',return_value={'ok':True}) as launch:
            d.request({'action':'confirm','proposal_id':p['proposal_id'],'approve':True},user=True)
            d.request({'action':'confirm','proposal_id':p['proposal_id'],'approve':True},user=True)
            self.assertEqual(launch.call_count,1)

    def test_private_environment_does_not_inherit_host_authority(self):
        visual=self.desktop.visual;visual.root=self.path/'tools'
        scope={'home':self.path/'scope','outputs':1}
        with patch.dict(os.environ,{'DISPLAY':':1','WAYLAND_DISPLAY':'host','DBUS_SESSION_BUS_ADDRESS':'host','SECRET_TOKEN':'do-not-use'}):
            env=visual.environment(scope);cmd=visual.sandbox(scope,['/usr/bin/true'])
        self.assertEqual(env['WAYLAND_DISPLAY'],'wayland-1')
        self.assertNotIn('DISPLAY',env);self.assertNotIn('DBUS_SESSION_BUS_ADDRESS',env);self.assertNotIn('SECRET_TOKEN',env)
        self.assertIn('--unshare-all',cmd);self.assertNotIn(str(os.environ.get('XDG_RUNTIME_DIR','/run/user')),cmd)
        self.assertNotIn('/dev/input',cmd);self.assertNotIn('/dev/dri',cmd);self.assertNotIn(str(__import__('pathlib').Path.home()),cmd)

    def test_no_unsupported_profile_or_compositor_arguments(self):
        d=self.desktop;d.available=True;d.visual.ready=True
        for args in ({'application':'terminal'},{'application':'/usr/bin/sh'},{'application':'pad','outputs':30},{'application':'pad','scale':True}):
            with self.assertRaises(ValueError):d.request({'action':'visual_open',**args})
        with self.assertRaises(ValueError):d.request({'action':'visual_open','application':'pad','display':'host'})

    def test_action_contract_bounds_and_balances_input(self):
        view={'geometry':{'rect':{'width':1000,'height':700}}}
        invalid=[[{'type':'click','x':0,'y':5}],[{'type':'click','x':True,'y':5}],
                 [{'type':'move','x':1001,'y':4}],[{'type':'down','x':3,'y':3}],
                 [{'type':'up'}],[{'type':'keys','keys':['ctrl']}],[{'type':'keys','keys':['super','e']}],
                 [{'type':'text','text':'password=secret'}],[{'type':'text','text':'a\x00'}],
                 [{'type':'drag','x':1,'y':1,'to_x':10,'to_y':10,'duration_ms':10000}],
                 [{'type':'scroll','x':3,'y':3,'steps':True,'direction':'down'}],
                 [{'type':'click','x':3,'y':3,'command':'exec sh'}]]
        for actions in invalid:
            with self.subTest(actions=actions),self.assertRaises((ValueError,PermissionError)):
                v.Visual.validate_actions(actions,view)
        v.Visual.validate_actions([{'type':'down','x':5,'y':5},{'type':'move','x':6,'y':6},{'type':'up'}],view)

    def test_visual_input_cannot_target_semantic_scope(self):
        d=self.desktop;d.available=True
        with patch.object(d,'scope',return_value={'application':'accessible-window'}):
            with self.assertRaises(PermissionError):d.request({'action':'visual_act','scope':'host','snapshot':'x','actions':[]})

    def test_stale_snapshot_rejected_before_thread_or_effect(self):
        d=self.desktop;d.available=True
        scope={'application':'isolated-visual','snapshot':'now','views':{'old':{'created':time.monotonic()}}}
        with patch.object(d,'scope',return_value=scope):
            with self.assertRaises(PermissionError):d.request({'action':'visual_act','scope':'private','snapshot':'old','actions':[]})
        self.assertEqual(d.jobs,{})

    def test_cancelled_or_expired_child_never_starts(self):
        event=threading.Event();event.set()
        with patch.object(m.subprocess,'Popen',side_effect=AssertionError('spawn')):
            with self.assertRaises(InterruptedError):m.run_json(['unused'],{},cancel=event,raw=True)
            with self.assertRaises(TimeoutError):m.run_json(['unused'],{},deadline=time.monotonic()-1,raw=True)

    def test_raw_output_checks_status_and_budget(self):
        with self.assertRaises(RuntimeError):m.run_json(['/usr/bin/python3','-c','print("private");exit(1)'],{},raw=True)
        with self.assertRaises(ValueError):m.run_json(['/usr/bin/python3','-c','print("x"*20000)'],{},raw=True,limit=100)

    def test_interrupted_keys_destroy_private_seat(self):
        d=self.desktop;visual=d.visual;visual.root=self.path/'tools'
        scope={'id':'s','home':self.path,'outputs':1,'released':False,'snapshot':None}
        view={'geometry':{},'image':__import__('hashlib').sha256(b'pixels').hexdigest()}
        job={'id':'test','state':'running','started':time.monotonic(),'cancel':threading.Event(),'done':threading.Event(),'completed_steps':0}
        def release(s):s['released']=True
        with patch.object(visual,'capture',return_value=({},b'pixels')),patch.object(visual,'geometry',return_value={}),patch.object(v,'run_json',side_effect=InterruptedError()),patch.object(d,'release',side_effect=release) as close:
            visual.work(job,scope,view,[{'type':'keys','keys':['ctrl','a']}])
        self.assertEqual(job['state'],'cancelled');self.assertTrue(job['held_input_released']);close.assert_called_once()

    def test_changed_or_escaping_installation_is_rejected(self):
        import hashlib
        visual=self.desktop.visual;root=self.path/'tools';root.mkdir()
        names=['pointer-seat','key-combo','usr/bin/sway','usr/bin/grim','usr/bin/wtype']
        for name in names:
            path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'fixture')
        manifest={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in names}
        (root/'.argos-files.json').write_text(json.dumps(manifest))
        visual.root=root;visual.settings={'manifest_sha256':hashlib.sha256((root/'.argos-files.json').read_bytes()).hexdigest()}
        visual.validate_installation()
        (root/'key-combo').write_bytes(b'changed')
        with self.assertRaises(ValueError):visual.validate_installation()
        (root/'key-combo').unlink();outside=self.path/'outside';outside.write_bytes(b'fixture');(root/'key-combo').symlink_to(outside)
        with self.assertRaises(ValueError):visual.validate_installation()
