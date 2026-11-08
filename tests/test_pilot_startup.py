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
from argos_startup_tests.startup import StartupTrace,release_ready


class StartupTests(unittest.IsolatedAsyncioTestCase):
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
