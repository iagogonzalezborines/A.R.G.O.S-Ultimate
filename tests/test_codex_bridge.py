import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from argos.codex import Codex, RESULT_SCHEMA
from argos.models import ArgosError
from argos.policy import ApprovalNeeded


FAKE = r'''#!/usr/bin/env python3
import json,sys
def emit(data):
    print(json.dumps(data),flush=True)
for line in sys.stdin:
    m=json.loads(line)
    method=m.get("method")
    if method=="initialize": result={}
    elif method=="account/read": result={"account":{"type":"chatgpt"}}
    elif method=="model/list": result={"data":[{"model":"test-model","supportedReasoningEfforts":[{"reasoningEffort":"low"}]}]}
    elif method in ("thread/start","thread/resume"): result={"thread":{"id":"thread-one"},"model":"test-model"}
    elif method=="turn/start":
        emit({"id":m["id"],"result":{"turn":{"id":"turn-one"}}})
        emit({"id":900,"method":"item/tool/call","params":{"threadId":"thread-one",
          "turnId":"turn-one","tool":"argos_capability",
          "arguments":{"capability":"files.read","arguments_json":'{"file":"demo.txt"}'}}})
        continue
    elif method=="turn/interrupt": result={}
    elif m.get("id")==900:
        if m["result"]["success"]:
            emit({"method":"item/completed","params":{"threadId":"thread-one","item":{
                "type":"agentMessage","phase":"final_answer",
                "text":json.dumps({"kind":"result","speech":"Leído.","detail":"Observed."})}}})
            emit({"method":"turn/completed","params":{"threadId":"thread-one","turn":{"status":"completed"}}})
        continue
    else: continue
    emit({"id":m["id"],"result":result})
'''


class BridgeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        fake = self.path / "codex"
        fake.write_text(FAKE)
        fake.chmod(0o700)
        self.binary = patch("argos.codex_probe.find_binary", return_value=str(fake))
        self.binary.start()
        self.codex = Codex(self.path)

    async def asyncTearDown(self):
        await self.codex.close()
        self.binary.stop()
        self.temp.cleanup()

    async def test_dynamic_tool_result_returns_on_persistent_thread(self):
        calls = []
        async def tool(name, args):
            calls.append((name, args))
            return {"evidence": "actual tool result"}
        thread = await self.codex.thread("engineering", tools=True)
        with patch.object(self.codex, "rpc", wraps=self.codex.rpc) as rpc:
            result = await self.codex.turn(thread, "read file", RESULT_SCHEMA, tool)
        turn_params = next(call.args[1] for call in rpc.call_args_list if call.args[0] == "turn/start")
        self.assertNotIn("effort", turn_params)
        self.assertEqual(calls, [("files.read", {"file": "demo.txt"})])
        self.assertEqual(result["speech"], "Leído.")
        self.assertEqual(await self.codex.thread("engineering", thread), thread)
        self.assertNotIn(thread, self.codex.tools)

    async def test_approval_suspends_turn_and_removes_tool_authority(self):
        async def tool(name, args):
            raise ApprovalNeeded({"capability": name, "arguments": args})
        thread = await self.codex.thread("engineering", tools=True)
        with self.assertRaises(ApprovalNeeded):
            await self.codex.turn(thread, "read file", RESULT_SCHEMA, tool)
        self.assertNotIn(thread, self.codex.tools)
        self.assertNotIn(thread, self.codex.queues)

    async def test_native_server_request_cannot_execute(self):
        messages = []
        async def send(message):
            messages.append(message)
        self.codex.send = send
        await self.codex._server_request({"id": 5, "method": "item/commandExecution/requestApproval",
                                         "params": {"threadId": "thread-one"}})
        self.assertIn("error", messages[0])

    async def test_cancel_turn_cancels_its_running_operation(self):
        entered, cancelled = asyncio.Event(), asyncio.Event()
        async def tool(name, args):
            entered.set()
            try:
                await asyncio.sleep(60)
            finally:
                cancelled.set()
        thread = await self.codex.thread("engineering", tools=True)
        turn = asyncio.create_task(self.codex.turn(thread, "read file", RESULT_SCHEMA, tool))
        await asyncio.wait_for(entered.wait(), 2)
        turn.cancel()
        await asyncio.gather(turn, return_exceptions=True)
        self.assertTrue(cancelled.is_set())
        self.assertNotIn(thread, self.codex.callback_threads.values())

    async def test_provider_close_reaps_child(self):
        await self.codex.start()
        child = self.codex.process
        await self.codex.close()
        self.assertIsNotNone(child.returncode)

    async def test_preparation_reuses_project_thread_without_an_inference_turn(self):
        context = {"session": "voice", "project": {"id": "project-one"}}
        with patch.object(self.codex, "rpc", wraps=self.codex.rpc) as rpc:
            await asyncio.gather(self.codex.prepare(context), self.codex.prepare(context))
            methods = [call.args[0] for call in rpc.call_args_list]
            self.assertEqual(methods.count("thread/start"), 1)
            self.assertNotIn("turn/start", methods)
            result = {"kind": "answer", "speech": "Hola.", "agent": "", "capability": "", "arguments_json": "{}"}
            with patch.object(self.codex, "turn", AsyncMock(return_value=result)) as turn:
                await self.codex.decide("hola", context)
            self.assertEqual(turn.call_args.args[0], "thread-one")
            self.assertEqual([call.args[0] for call in rpc.call_args_list].count("thread/start"), 1)

    async def test_general_uses_supported_low_effort_without_changing_model(self):
        result = {"kind": "answer", "speech": "Hola.", "agent": "", "capability": "", "arguments_json": "{}"}
        with patch.object(self.codex, "turn", AsyncMock(return_value=result)) as turn:
            await self.codex.decide("hola", {})
        self.assertEqual(turn.call_args.kwargs["effort"], "low")

    async def test_unknown_model_keeps_its_default_effort(self):
        await self.codex.start()
        self.codex.fast_models.clear()
        result = {"kind": "answer", "speech": "Hola.", "agent": "", "capability": "", "arguments_json": "{}"}
        with patch.object(self.codex, "turn", AsyncMock(return_value=result)) as turn:
            await self.codex.decide("hola", {})
        self.assertIsNone(turn.call_args.kwargs["effort"])
