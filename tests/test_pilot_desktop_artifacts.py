"""Controller scope regression tests; real native/filesystem cases live in qa_desktop."""
import json
from pathlib import Path
from unittest.mock import patch
import unittest
import test_pilot_desktop as fixture

class ApplicationProfilesTests(unittest.TestCase):
    setUp=fixture.DesktopTests.setUp

    def setup_profile(self):
        p=self.desktop.profiles;p.path=self.path/'enabled.json';p.catalogue=self.path/'profiles.json'
        p.catalogue.write_text(json.dumps({'sample':{'name':'Sample','executable':'/usr/bin/true','argv':['/usr/bin/true'],'resources':[],'app_id':'sample','private_bus':False,'memory_mib':1536,'network':False,'filesystem':'private','operations':['capture'],'seed':{}}}))
        return p

    def test_discovery_does_not_enable_or_execute(self):
        p=self.setup_profile()
        with patch.object(self.desktop.visual,'launch',side_effect=AssertionError('launch')):
            self.assertFalse(p.discover()['applications'][0]['enabled'])
            with self.assertRaises(PermissionError):p.selected('sample')
            with self.assertRaises(PermissionError):p.selected('/usr/bin/sh')
        self.assertFalse(p.path.exists())

    def test_enablement_requires_human_and_checks_profile_revision(self):
        p=self.setup_profile();self.desktop.available=True;self.desktop.visual.ready=True
        result=self.desktop.request({'action':'enable_application','application':'sample'})
        with self.assertRaises(PermissionError):self.desktop.request({'action':'confirm','proposal_id':result['proposal_id'],'approve':True})
        data=json.loads(p.catalogue.read_text());data['sample']['argv'].append('changed');p.catalogue.write_text(json.dumps(data))
        with patch.object(self.desktop.visual,'launch',side_effect=AssertionError('launch')):
            with self.assertRaises(PermissionError):self.desktop.request({'action':'confirm','proposal_id':result['proposal_id'],'approve':True},user=True)

    def test_changed_profile_invalidates_enabled_revision(self):
        p=self.setup_profile();definition=p.definition('sample');p.path.write_text(json.dumps({'sample':{'revision':definition['revision']}}));self.assertEqual(p.selected('sample'),definition)
        data=json.loads(p.catalogue.read_text());data['sample']['network']=True;p.catalogue.write_text(json.dumps(data))
        with self.assertRaises(ValueError):p.selected('sample')

    def test_failed_launch_never_enables(self):
        p=self.setup_profile()
        with patch.object(self.desktop.visual,'launch',side_effect=RuntimeError('unavailable')):
            with self.assertRaises(RuntimeError):p.enable(p.definition('sample'))
        self.assertFalse(p.path.exists())

    def test_no_arbitrary_scope_fields_or_model_export_confirmation(self):
        d=self.desktop;d.available=True;d.visual.ready=True
        for action in ('project_open','export','enable_application'):
            with self.assertRaises(ValueError):d.request({'action':action,'command':'sh'})
        proposal=d.access.proposal({'kind':'desktop_export','path':'test','content':'review'})
        with patch.object(d.artifacts,'export',side_effect=AssertionError('export')):
            with self.assertRaises(PermissionError):d.request({'action':'confirm','proposal_id':proposal['proposal_id'],'approve':True})

    def test_reopen_checks_native_workspace_identity_before_launch(self):
        d=self.desktop;bridge=d.artifacts
        bound={'project':'p','task_id':'t','expected_revision':'r','task_revision':'tr'}
        ctx={'project':{'id':'p','revision':'r'},'task':{'id':'t','revision':'tr'},'sessions':[{'session_id':'s','profile_revision':'rev'}]}
        proposal={'bound':bound,'profile':{'id':'sample','revision':'rev'},'imports':[],'retained':True,'session_id':'s'}
        with patch.object(bridge,'context',return_value=ctx),patch.object(d.profiles,'selected',return_value=proposal['profile']),patch.object(bridge,'native',side_effect=PermissionError('workspace replaced')),patch.object(d.visual,'launch',side_effect=AssertionError('launch')):
            with self.assertRaises(PermissionError):bridge.launch(proposal)
