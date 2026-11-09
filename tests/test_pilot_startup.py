"""Real child failure diagnostics and independent audio readiness, without audio/model use."""
import asyncio
import importlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]/'experiments/hermes-pilot'
sys.path.insert(0,str(ROOT))
package=types.ModuleType('argos_startup_tests');package.__path__=[str(ROOT/'ui-workbench/runtime')]
sys.modules[package.__name__]=package
runtime=importlib.import_module('argos_startup_tests.conversation')
from argos_startup_tests.startup import StartupTrace,release_ready,stderr_summary


class StartupTests(unittest.IsolatedAsyncioTestCase):
    def test_faulthandler_frames_are_kept_without_source_or_error_content(self):
        diagnostic='Timeout (0:00:15)!\nThread 0x123 (most recent call first):\n  File "/private/loader.py", line 42 in load\n  File "/private/entry.py", line 9 in <module>\nSECRET=DO_NOT_STORE\n'
        summary=stderr_summary(diagnostic)
        self.assertEqual(summary['frames'],[{'file':'loader.py','line':42,'function':'load'},{'file':'entry.py','line':9,'function':'<module>'}])
        self.assertNotIn('DO_NOT_STORE',json.dumps(summary));self.assertNotIn('/private',json.dumps(summary))

    async def test_import_timeout_retries_once_only_after_previous_child_is_reaped(self):
        with tempfile.TemporaryDirectory() as directory:
            marker=Path(directory)/'attempt'
            script="import json,sys,time;from pathlib import Path;p=Path(sys.argv[1]);print(json.dumps({'event':'startup.stage','stage':'import_agent'}),flush=True);first=not p.exists();p.write_text('attempt');time.sleep(10) if first else None;print(json.dumps({'ready':True}),flush=True);sys.stdin.read()"
            worker=runtime.Worker([sys.executable,'-c',script,str(marker)],name='codex',startup_timeout=.3)
            with self.assertRaises(runtime.WorkerStartupError) as raised:await worker.start()
            self.assertTrue(raised.exception.retryable);first=worker.process
            self.assertIsNotNone(first.returncode)
            ready=await worker.start();self.assertTrue(ready['ready']);self.assertNotEqual(first.pid,worker.process.pid)
            await worker.close()

    async def test_audio_loading_starts_after_codex_ready_and_import_recovery_is_bounded(self):
        for failures in [0,1,2]:
            events=[];workers=[];calls=[];model_ready=False
            class FakeWorker:
                def __init__(self,*args,name='worker',**kw):self.name=name;self.closed=False;workers.append(self)
                async def start(self,stage):
                    nonlocal model_ready
                    calls.append(self.name)
                    if self.name=='codex':
                        if calls.count('codex')<=failures:raise runtime.WorkerStartupError('codex','synthetic import timeout',{'last_stage':'import_agent'},retryable=True)
                        await stage(self.name,'ready');model_ready=True
                    else:self_outer.assertTrue(model_ready)
                    return {'ready':True,'codex_ready':True,'startup_seconds':.01}
                async def close(self):self.closed=True
            self_outer=self
            with tempfile.TemporaryDirectory() as directory,patch.object(runtime,'ROOT',Path(directory)),patch.object(runtime,'Worker',FakeWorker):
                host=runtime.Conversation(events.append,no_capture=True,session_id='ordered-start-test')
                try:
                    await host.prepare()
                    self.assertEqual(calls.count('codex'),min(failures+1,2))
                    if failures<2:
                        self.assertTrue(host.status['ready']);self.assertEqual(calls[-2:],['recognition','speech'])
                    else:
                        self.assertEqual(calls,['codex','codex']);self.assertFalse(host.status['ready']);self.assertTrue(all(w.closed for w in workers))
                    self.assertEqual(host.status['startup_retries'],int(failures>0))
                    self.assertFalse(any(e.get('type')=='voice.answer' for e in events))
                finally:
                    for task in host.tasks:task.cancel()
                    await asyncio.gather(*host.tasks,return_exceptions=True);host.loop.close()

    async def test_manual_startup_retry_is_single_and_never_replays_text(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(runtime,'ROOT',Path(directory)):
            host=runtime.Conversation(lambda e:None,no_capture=True,session_id='manual-retry-test');calls=[]
            async def prepare():calls.append('prepare');await asyncio.sleep(10)
            host.prepare=prepare
            try:
                self.assertEqual((await host.command('retry'))['error'],'startup_retry_unavailable')
                host.status.update(ready=False,phase='error',startup_error_component='codex')
                self.assertTrue((await host.command('retry'))['ok'])
                self.assertEqual((await host.command('retry'))['error'],'startup_in_progress')
                await asyncio.sleep(0);self.assertEqual(calls,['prepare'])
                host.prepare_task.cancel();await asyncio.gather(host.prepare_task,return_exceptions=True)
                host.status['ready']=True
                self.assertEqual((await host.command('retry'))['error'],'startup_retry_unavailable')
                host.closed=True
                with self.assertRaises(ValueError):await host.command('retry')
            finally:host.loop.close()

    async def test_cancelled_audio_startup_leaves_no_old_conversation_consumer(self):
        audio_started=asyncio.Event();workers=[]
        class FakeWorker:
            def __init__(self,*args,name='worker',**kw):self.name=name;self.closed=False;workers.append(self)
            async def start(self,stage):
                if self.name=='codex':return {'ready':True,'codex_ready':True,'startup_seconds':.01}
                audio_started.set();await asyncio.sleep(10)
            async def close(self):self.closed=True
        with tempfile.TemporaryDirectory() as directory,patch.object(runtime,'ROOT',Path(directory)),patch.object(runtime,'Worker',FakeWorker):
            host=runtime.Conversation(lambda e:None,no_capture=True,session_id='cancel-ready-model-test')
            task=asyncio.create_task(host.prepare())
            try:
                await audio_started.wait();self.assertEqual(len(host.tasks),1)
                consumer=host.tasks[0];task.cancel();await asyncio.gather(task,return_exceptions=True)
                self.assertTrue(consumer.done());self.assertEqual(host.tasks,[]);self.assertTrue(all(w.closed for w in workers))
            finally:
                task.cancel();await asyncio.gather(task,return_exceptions=True);host.loop.close()

    async def test_new_addressed_turn_clears_stale_error_but_standby_audio_does_not(self):
        events=[]
        class Model:
            async def call(self,value,on_event):
                return {'ok':True,'speech':'Ready.','seconds':.01}
        with tempfile.TemporaryDirectory() as directory,patch.object(runtime,'ROOT',Path(directory)):
            (Path(directory)/'reports').mkdir()
            host=runtime.Conversation(events.append,no_capture=True,session_id='stale-error-test')
            host.model=Model();host.status.update(ready=True,output_muted=True,error='Previous request failed')
            try:
                await host.accept('background speech',direct=False)
                self.assertEqual(host.status['error'],'Previous request failed')
                self.assertEqual(events,[])
                await host.accept('Hello',direct=True)
                self.assertTrue(any(e.get('phase')=='thinking' and e.get('error') is None for e in events))
                self.assertTrue(any(e.get('type')=='voice.answer' and e.get('text')=='Ready.' for e in events))
                self.assertIsNone(host.status['error'])
            finally:host.loop.close()

    async def test_bare_wake_recovers_from_prior_error(self):
        host=runtime.Conversation(lambda e:None,no_capture=True,session_id='wake-error-test')
        host.status['error']='Previous request failed'
        try:
            await host.accept('Argos')
            self.assertTrue(host.status['dialogue_open'])
            self.assertEqual(host.status['phase'],'listening')
            self.assertIsNone(host.status['error'])
        finally:host.loop.close()

    def test_voice_update_is_not_accepted_when_only_text_has_started(self):
        state={'agent_connected':True,'renderer_connected':True,'voice_ready':False}
        self.assertFalse(release_ready(state))
        self.assertTrue(release_ready(state,text_only=True))
        self.assertTrue(release_ready({**state,'voice_ready':True}))
        self.assertFalse(release_ready({**state,'voice_ready':True,'renderer_connected':False}))

    async def test_real_timeout_keeps_stage_and_error_type_without_stderr_content(self):
        script="import json,sys,time;print(json.dumps({'event':'startup.stage','stage':'authentication'}),flush=True);print('RuntimeError: token=DO_NOT_STORE private conversation',file=sys.stderr,flush=True);time.sleep(10)"
        worker=runtime.Worker([sys.executable,'-c',script],name='codex',startup_timeout=.2)
        with self.assertRaises(runtime.WorkerStartupError) as raised:await worker.start()
        error=raised.exception
        self.assertEqual(error.diagnostics['last_stage'],'authentication')
        self.assertFalse(error.retryable)
        self.assertIn('RuntimeError',error.diagnostics['exception_types'])
        self.assertIsNotNone(worker.process.returncode)
        with tempfile.TemporaryDirectory() as directory:
            trace=StartupTrace(Path(directory)/'latest.json')
            trace.record('codex','failed',error=error,diagnostics=error.diagnostics)
            text=trace.path.read_text()
            self.assertNotIn('DO_NOT_STORE',text);self.assertNotIn('private conversation',text)
            self.assertIn('authentication',text)

    async def test_audio_failure_does_not_destroy_ready_text_conversation(self):
        events=[];workers=[]
        class FakeWorker:
            def __init__(self,*args,name='worker',**kw):self.name=name;self.closed=False;workers.append(self)
            async def start(self,stage):
                await stage(self.name,'starting')
                if self.name=='speech':raise runtime.WorkerStartupError('speech','synthetic unavailable device')
                await stage(self.name,'ready')
                return {'ready':True,'codex_ready':True,'startup_seconds':.01,'device':'synthetic'}
            async def close(self):self.closed=True
            def interrupt(self):pass
        with tempfile.TemporaryDirectory() as directory,patch.object(runtime,'ROOT',Path(directory)),patch.object(runtime,'Worker',FakeWorker):
            host=runtime.Conversation(events.append,no_capture=True,session_id='audio-failure-test')
            try:
                await host.prepare()
                self.assertTrue(host.status['ready']);self.assertTrue(host.status['codex_ready'])
                self.assertFalse(host.status['speech_ready']);self.assertFalse(host.status['voice_ready'])
                self.assertEqual(host.status['startup_failures'],['speech'])
                self.assertTrue(any(e.get('ready') for e in events))
            finally:
                for task in host.tasks:task.cancel()
                await asyncio.gather(*host.tasks,return_exceptions=True);host.loop.close()

    async def test_codex_failure_reaps_siblings_and_never_reports_conversation_ready(self):
        workers=[]
        class FakeWorker:
            def __init__(self,*args,name='worker',**kw):self.name=name;self.closed=False;workers.append(self)
            async def start(self,stage):
                if self.name=='codex':raise runtime.WorkerStartupError('codex','synthetic handshake failure')
                await asyncio.sleep(10)
            async def close(self):self.closed=True
        with tempfile.TemporaryDirectory() as directory,patch.object(runtime,'ROOT',Path(directory)),patch.object(runtime,'Worker',FakeWorker):
            host=runtime.Conversation(lambda e:None,no_capture=True,session_id='codex-failure-test')
            try:
                await host.prepare()
                self.assertFalse(host.status['ready']);self.assertFalse(host.status['codex_ready'])
                self.assertTrue(all(w.closed for w in workers))
            finally:host.loop.close()
