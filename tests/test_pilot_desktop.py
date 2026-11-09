"""Desktop policy/child lifecycle regressions. No real desktop, projects or audio."""
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]/'experiments/hermes-pilot'
pkg = types.ModuleType('argos_desktop_tests');pkg.__path__=[str(ROOT/'ui-workbench/runtime')];sys.modules[pkg.__name__]=pkg
m = importlib.import_module('argos_desktop_tests.desktop')

class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)
        self.desktop=m.Desktop(lambda e:None,config_path=self.path/'absent.json')
        self.addCleanup(self.desktop.close)

    def test_disabled_does_not_spawn_or_advertise(self):
        with patch.object(m.subprocess,'Popen',side_effect=AssertionError('unexpected child')):
            self.assertFalse(self.desktop.request({'action':'availability'})['enabled'])
            with self.assertRaises(PermissionError):self.desktop.request({'action':'open','application':'calculator'})

    def test_invalid_configuration_denies_instead_of_breaking_conversation(self):
        p=self.path/'config.json';p.write_text(json.dumps({'desktop_enabled':True,'desktop':{'binary':'missing'}}))
        d=m.Desktop(lambda e:None,config_path=p);self.assertFalse(d.availability()['enabled']);d.close()

    def test_schema_rejects_arbitrary_host_arguments(self):
        self.desktop.available=True
        for args in [{'action':'press','keys':'ctrl+l'}, {'action':'open','application':'calculator','argv':['sh']}, {'action':'observe','scope':'x','pid':os.getpid()}]:
            with self.assertRaises(ValueError):self.desktop.request(args)
        for name in ['terminal','firefox','/usr/bin/sh']:
            with self.assertRaises(PermissionError):self.desktop.request({'action':'open','application':name})

    def test_process_identity_distinguishes_executable_and_start(self):
        identity=m.process_identity(os.getpid());self.assertEqual(identity[0],os.getuid());self.assertTrue(identity[1]);self.assertTrue(identity[2])
        with self.assertRaises(OSError):m.process_identity(99999999)

    def test_subprocess_timeout_reaps_process(self):
        path=self.path/'pid'
        with self.assertRaises(TimeoutError):m.run_json([sys.executable,'-c','import os,time;from pathlib import Path;Path('+repr(str(path))+').write_text(str(os.getpid()));time.sleep(30)'],os.environ,timeout=.2)
        self.assertFalse(Path('/proc/'+path.read_text()).exists())

    def test_sequence_deadline_bounds_each_backend_call(self):
        started=time.monotonic()
        with self.assertRaises(TimeoutError):
            m.run_json([sys.executable,'-c','import time;time.sleep(30)'],os.environ,timeout=3,deadline=started+.1)
        self.assertLess(time.monotonic()-started,1)

    def test_subprocess_cancellation_reaps_process(self):
        event=threading.Event();timer=threading.Timer(.1,event.set);timer.start()
        with self.assertRaises(InterruptedError):m.run_json([sys.executable,'-c','import time;time.sleep(30)'],os.environ,cancel=event)
        timer.join()

    def test_subprocess_output_is_bounded(self):
        with self.assertRaises(ValueError):m.run_json([sys.executable,'-c','print("x"*100000)'],os.environ,limit=1000)

    def test_backend_errors_do_not_expose_raw_output(self):
        with self.assertRaisesRegex(RuntimeError,'DENIED') as e:
            m.run_json([sys.executable,'-c','print(\'{"ok":false,"error":{"code":"DENIED","message":"SECRET"}}\')'],os.environ)
        self.assertNotIn('SECRET',str(e.exception))

    def test_gui_owner_outlives_socket_request_thread(self):
        import signal
        result=[]
        # Real Linux parent-death signal, with a disposable sleeping process.
        marker=self.path/'child-ready'
        script='import ctypes,signal,time;from pathlib import Path;ctypes.CDLL(None).prctl(1,signal.SIGKILL);Path('+repr(str(marker))+').touch();time.sleep(5)'
        def request():
            child=m.launch_child([sys.executable,'-c',script],os.environ)
            deadline=time.monotonic()+2
            while not marker.exists() and time.monotonic()<deadline:time.sleep(.01)
            result.append(child)
        thread=threading.Thread(target=request)
        thread.start();thread.join();child=result[0]
        try:
            time.sleep(.15);self.assertIsNone(child.poll())
        finally:
            os.killpg(child.pid,signal.SIGTERM);child.wait(timeout=2)

    def prepared(self):
        d=self.desktop;d.available=True
        view={'elements':[{'ref':'@s:e1','name':'2','role':'switch','actions':['click']}],'fingerprint':'same','created':time.monotonic()}
        scope={'id':'scope','application':'calculator','snapshot':'snapshot','views':{'snapshot':view}}
        return d,scope,view

    def test_stale_and_foreign_refs_have_no_effect(self):
        d,scope,_=self.prepared()
        with patch.object(d,'scope',return_value=scope),patch.object(d,'cli',side_effect=AssertionError('effect')):
            for snapshot,refs in [('old',['@s:e1']),('snapshot',['@other:e1'])]:
                with self.assertRaises(PermissionError):d.action({'scope':'scope','snapshot':snapshot,'refs':refs})

    def test_button_names_resolve_only_unique_observed_controls(self):
        d,scope,view=self.prepared();observed=[]
        def work(job,scope,view,names):
            observed.extend(names);job['state']='completed';job['done'].set();d.active=None
        with patch.object(d,'scope',return_value=scope),patch.object(d,'work',side_effect=work):
            result=d.action({'scope':'scope','snapshot':'snapshot','buttons':['2','2']})
        self.assertEqual(observed,['2','2']);self.assertEqual(result['buttons'],['2','2'])

    def test_ambiguous_or_unknown_button_name_is_rejected(self):
        d,scope,view=self.prepared();view['elements'].append(dict(view['elements'][0],ref='@s:e2'))
        with patch.object(d,'scope',return_value=scope):
            for button in ['2','Quit','Preferences...','Terminal']:
                with self.assertRaises(PermissionError):d.action({'scope':'scope','snapshot':'snapshot','buttons':[button]})
            with self.assertRaises(ValueError):d.action({'scope':'scope','snapshot':'snapshot','buttons':['2'],'refs':['@s:e1']})

    def test_read_only_profile_cannot_act(self):
        d,scope,_=self.prepared();scope['application']='comparison'
        with patch.object(d,'scope',return_value=scope):
            with self.assertRaises(PermissionError):d.action({'scope':'scope','snapshot':'snapshot','refs':['@s:e1']})

    def test_action_consumes_revision_and_duplicate_does_not_replay(self):
        d,scope,_=self.prepared();calls=[]
        def work(job,*args):calls.append(job['id']);job['state']='completed';job['done'].set();d.active=None
        args={'scope':'scope','snapshot':'snapshot','refs':['@s:e1']}
        with patch.object(d,'scope',return_value=scope),patch.object(d,'work',side_effect=work):
            a=d.action(args);b=d.action(args)
        self.assertEqual(a['id'],b['id']);self.assertEqual(len(calls),1);self.assertIsNone(scope['snapshot'])

    def test_busy_refuses_second_operation_but_status_and_cancel_work(self):
        d,scope,_=self.prepared();job={'id':'one','scope':'scope','state':'running','cancel':threading.Event(),'done':threading.Event()};d.jobs['one']=job;d.active='one'
        try:
            with self.assertRaises(RuntimeError):d.request({'action':'observe','scope':'scope'})
            self.assertEqual(d.request({'action':'status'})['state'],'running')
            self.assertTrue(d.request({'action':'cancel'})['cancellation_requested']);self.assertTrue(job['cancel'].is_set())
        finally:job['done'].set();d.active=None

    def test_changed_display_blocks_before_first_click(self):
        d,scope,view=self.prepared();scope['views']['fresh']={'fingerprint':'changed'}
        job={'id':'one','scope':'scope','state':'running','completed_steps':0,'started':time.monotonic(),'cancel':threading.Event(),'done':threading.Event()}
        with patch.object(d,'observe',return_value={'snapshot':'fresh'}),patch.object(d,'cli',side_effect=AssertionError('effect')):
            d.work(job,scope,view,['2'])
        self.assertEqual(job['state'],'failed');self.assertEqual(job['completed_steps'],0)

    def test_unknown_job_after_restart_never_replays(self):
        self.desktop.available=True
        with self.assertRaises(ValueError):self.desktop.request({'action':'status','job':'old-job'})
        self.assertIsNone(self.desktop.active)

if __name__=='__main__':unittest.main()
