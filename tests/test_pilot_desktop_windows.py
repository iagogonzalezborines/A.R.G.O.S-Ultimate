"""Authorization, stale state and non-interference boundary tests (no desktop I/O)."""
import unittest
import test_pilot_desktop as fixture
m = fixture.m
import threading
import time
from unittest.mock import patch


class WindowAccessTests(unittest.TestCase):
    setUp = fixture.DesktopTests.setUp
    def generic(self):
        d=self.desktop;d.available=True
        view={'elements':[{'ref':'/control','name':'Draft','role':'text','actions':['replace_text','click']}],
              'fingerprint':'first','created':time.monotonic(),'geometry':{'address':'0x1'},'layout':[{'scale':1}]}
        scope={'id':'scope','application':'accessible-window','app':'editor','snapshot':'snapshot','views':{'snapshot':view},'released':False}
        return d,scope,view

    def test_model_cannot_confirm_even_with_valid_proposal_id(self):
        with self.assertRaises(PermissionError):self.desktop.access.confirm('any',True,False)

    def test_unknown_reference_and_credential_text_never_propose_effect(self):
        d,s,v=self.generic()
        with patch.object(d,'scope',return_value=s):
            for args in [{'ref':'/foreign','operation':'click'}, {'ref':'/control','operation':'replace_text','text':'api_key=hidden'}]:
                with self.assertRaises((PermissionError,ValueError)):
                    d.access.prepare({'scope':'scope','snapshot':'snapshot',**args})
        self.assertEqual(d.access.pending,{})

    def test_proposal_does_not_mutate_and_repeated_request_deduplicates(self):
        d,s,v=self.generic();args={'scope':'scope','snapshot':'snapshot','ref':'/control','operation':'replace_text','text':'Draft'}
        with patch.object(d,'scope',return_value=s),patch.object(d,'semantic',side_effect=AssertionError('effect')):
            first=d.access.prepare(args);second=d.access.prepare(args)
        self.assertEqual(first['proposal_id'],second['proposal_id']);self.assertIsNone(d.active)

    def test_denial_and_stop_invalidate_pending_approvals(self):
        d,s,v=self.generic()
        with patch.object(d,'scope',return_value=s):p=d.access.prepare({'scope':'scope','snapshot':'snapshot','ref':'/control','operation':'click'})
        d.request({'action':'stop'})
        self.assertEqual(d.access.confirm(p['proposal_id'],True,True)['status'],'cancelled')
        self.assertIsNone(d.active)

    def test_expired_review_is_rejected(self):
        d,s,v=self.generic()
        with patch.object(d,'scope',return_value=s):p=d.access.prepare({'scope':'scope','snapshot':'snapshot','ref':'/control','operation':'click'})
        d.access.pending[p['proposal_id']]['created']-=121
        with self.assertRaises(PermissionError):d.access.confirm(p['proposal_id'],True,True)

    def test_changed_snapshot_consumes_approval_without_effect_replay(self):
        d,s,v=self.generic()
        with patch.object(d,'scope',return_value=s),patch.object(d,'semantic',side_effect=AssertionError('effect')):
            p=d.access.prepare({'scope':'scope','snapshot':'snapshot','ref':'/control','operation':'click'});s['snapshot']='new'
            with self.assertRaises(PermissionError):d.access.confirm(p['proposal_id'],True,True)
            self.assertEqual(d.access.confirm(p['proposal_id'],True,True)['status'],'consumed')

    def test_release_user_window_does_not_kill_it(self):
        d,s,v=self.generic();s.update(child=None,home=self.path/'scope')
        s['home'].mkdir()
        with patch.object(m.os,'killpg',side_effect=AssertionError('killed user process')):d.release(s)
        self.assertTrue(s['released']);self.assertFalse(s['home'].exists())

    def job(self):
        return {'id':'test','scope':'scope','state':'running','started':time.monotonic(),'completed_steps':0,
                'cancel':threading.Event(),'done':threading.Event()}

    def test_changed_geometry_or_scale_refuses_before_delivery(self):
        d,s,v=self.generic();job=self.job()
        with patch.object(d,'scope',return_value=s),patch.object(d.access,'validate_window',return_value={'address':'0x1'}),patch.object(d.access.hypr,'layout',return_value=[{'scale':2}]),patch.object(d,'semantic',side_effect=AssertionError('effect')):
            d.access.work(job,s,{'view':v,'payload':{'operation':'click'}})
        self.assertEqual(job['state'],'failed');self.assertEqual(job['completed_steps'],0)

    def test_focus_change_stops_without_attempting_restoration(self):
        d,s,v=self.generic();job=self.job()
        with patch.object(d,'scope',return_value=s),patch.object(d.access,'validate_window',return_value=v['geometry']),patch.object(d.access.hypr,'layout',return_value=v['layout']),patch.object(d.access.hypr,'seat',side_effect=[{'focus':'other','cursor':{'x':1,'y':2}},{'focus':'target','cursor':{'x':1,'y':2}}]),patch.object(d,'semantic',return_value={'delivered':True}),patch.object(d,'observe',return_value={}):
            d.access.work(job,s,{'view':v,'payload':{'operation':'click'}})
        self.assertEqual(job['state'],'failed');self.assertEqual(job['completed_steps'],1)
        self.assertFalse(job['input_observation']['focus_unchanged'])

    def test_cancellation_preserves_uncertainty_and_invalidates_refs(self):
        d,s,v=self.generic();job=self.job()
        with patch.object(d,'scope',return_value=s),patch.object(d.access,'validate_window',return_value=v['geometry']),patch.object(d.access.hypr,'layout',return_value=v['layout']),patch.object(d.access.hypr,'seat',return_value={}),patch.object(d,'semantic',side_effect=InterruptedError()):
            d.access.work(job,s,{'view':v,'payload':{'operation':'click'}})
        self.assertEqual(job['state'],'cancelled');self.assertIsNone(s['snapshot']);self.assertIsNone(d.active)

    def test_physical_modes_are_not_advertised_or_accepted(self):
        d,s,v=self.generic();availability=d.availability()
        for key in ('physical_input','screenshots','shortcuts','drag'):self.assertFalse(availability[key])
        for action in ('drag','press','foreground','screenshot','mouse-move'):
            with self.assertRaises(ValueError):d.request({'action':action})


    def test_closed_process_has_desktop_error_not_filesystem_error(self):
        d,s,v=self.generic();s.update(child=None,pid=99999999,identity=(1,'missing','0'),used=time.monotonic())
        d.scopes['scope']=s;s['home']=self.path/'scope';s['home'].mkdir()
        with self.assertRaisesRegex(PermissionError,'Application closed'):d.scope('scope')
        self.assertIsNone(s['snapshot'])

    def test_approval_reports_started_not_completed_effect(self):
        d,s,v=self.generic()
        def fake_work(job,*args):job['done'].set();d.active=None
        with patch.object(d,'scope',return_value=s),patch.object(d.access,'work',side_effect=fake_work):
            p=d.access.prepare({'scope':'scope','snapshot':'snapshot','ref':'/control','operation':'click'})
            result=d.access.confirm(p['proposal_id'],True,True)
        self.assertEqual(result['status'],'started')
        self.assertEqual(result['completed_steps'],0)

    def test_controller_approval_surface_cannot_be_automated(self):
        with self.assertRaisesRegex(PermissionError,'approval surfaces'):
            self.desktop.access.deny_control_plane(99999999,{'class':'ARGOS'})

    def test_model_launch_needs_explicit_consent_and_deduplicates(self):
        d=self.desktop;d.available=True
        with patch.object(d,'launch',side_effect=AssertionError('unapproved foreground launch')):
            a=d.request({'action':'open','application':'calculator'})
            b=d.request({'action':'open','application':'calculator'})
        self.assertEqual(a['status'],'needs_approval');self.assertEqual(a['proposal_id'],b['proposal_id'])

    def test_user_launch_consent_is_single_use(self):
        d=self.desktop;d.available=True
        with patch.object(d,'launch',return_value={'window_verified':True}) as launch:
            p=d.request({'action':'open','application':'calculator'})
            result=d.request({'action':'confirm','proposal_id':p['proposal_id'],'approve':True},user=True)
            d.request({'action':'confirm','proposal_id':p['proposal_id'],'approve':True},user=True)
        self.assertTrue(result['window_verified']);self.assertEqual(launch.call_count,1)
