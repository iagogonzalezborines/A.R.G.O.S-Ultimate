"""Task-bound Codex App Server, with ARGOS as its only effectful tool bridge."""
import asyncio
import contextlib
import json
import os
import shutil

from .agents import contract
from .models import ArgosError
from .providers import validate_decision
from .security import safe_data


DECISION_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "kind": {"type": "string", "enum": ["answer", "clarify", "delegate", "capability", "panel", "reply", "develop", "task_status"]},
        "speech": {"type": "string"}, "agent": {"type": "string"},
        "capability": {"type": "string"}, "arguments_json": {"type": "string"},
    },
    "required": ["kind", "speech", "agent", "capability", "arguments_json"],
}
RESULT_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {"kind": {"type": "string", "enum": ["result", "question"]},
                   "speech": {"type": "string"}, "detail": {"type": "string"}},
    "required": ["kind", "speech", "detail"],
}
TOOL = {
    "type": "function", "name": "argos_capability",
    "description": "Request one registered ARGOS capability. Core enforces scope, approval and execution.",
    "inputSchema": {
        "type": "object", "additionalProperties": False,
        "properties": {"capability": {"type": "string"}, "arguments_json": {"type": "string"}},
        "required": ["capability", "arguments_json"],
    },
}


class Codex:
    name = "codex-chatgpt"
    conversation_allowed = False

    def __init__(self, directory):
        self.directory = directory / "codex-root"
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.process, self.reader = None, None
        self.pending, self.queues, self.tools = {}, {}, {}
        self.callbacks = set()
        self.callback_threads = {}
        self.sequence = 0
        self.start_lock = asyncio.Lock()
        self.chat_locks, self.chat_threads = {}, {}
        self.fast_models, self.fast_threads = set(), set()
        self.connected = False

    async def start(self):
        async with self.start_lock:
            if self.process and self.process.returncode is None:
                return
            from .codex_probe import find_binary
            binary = find_binary()
            if not binary:
                raise ArgosError("No se encuentra Codex.")
            disabled = ("shell_tool", "unified_exec", "multi_agent", "apps", "plugins",
                        "browser_use", "browser_use_external", "computer_use", "image_generation",
                        "view_image", "skill_search", "hooks", "code_mode",
                        "memories", "shell_snapshot")
            argv = [binary, "app-server", "--listen", "stdio://"]
            for feature in disabled:
                argv += ["--disable", feature]
            # Current models dispatch dynamic tools through the code-mode host.
            # Disabling this host leaves chat working but breaks every bridge
            # call. It orchestrates registered tools; native shell/browser/etc.
            # remain disabled and Core still authorizes every ARGOS effect.
            argv += ["--enable", "code_mode_host", "--enable", "skip_host_skill_discovery",
                     "-c", "project_doc_max_bytes=0", "-c", "mcp_servers={}",
                     "-c", 'web_search="disabled"', "-c", "analytics.enabled=false"]
            env = {k: v for k, v in os.environ.items() if k not in ("OPENAI_API_KEY", "CODEX_API_KEY")}
            self.process = await asyncio.create_subprocess_exec(
                *argv, cwd=self.directory, env=env, stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                limit=2 * 1024 * 1024)
            self.reader = asyncio.create_task(self._read())
            try:
                await self.rpc("initialize", {"clientInfo": {"name": "argos_core", "title": "ARGOS",
                                                            "version": "0.2.0"},
                                               "capabilities": {"experimentalApi": True}})
                await self.send({"method": "initialized", "params": {}})
                account = (await self.rpc("account/read", {"refreshToken": False})).get("account") or {}
                if account.get("type") != "chatgpt":
                    raise ArgosError("Codex necesita iniciar sesión con ChatGPT; no se usará una API de pago.")
                models = await self.rpc("model/list", {})
                self.fast_models = {model["model"] for model in models.get("data", [])
                                    if any(option.get("reasoningEffort") == "low"
                                           for option in model.get("supportedReasoningEfforts", []))}
                self.connected = True
            except BaseException:
                await self.close()
                raise

    async def send(self, message):
        if not self.process or self.process.returncode is not None:
            raise ArgosError("La conexión Codex se cerró.")
        self.process.stdin.write(json.dumps(message).encode() + b"\n")
        await self.process.stdin.drain()

    async def rpc(self, method, params):
        self.sequence += 1
        identifier = self.sequence
        future = asyncio.get_running_loop().create_future()
        self.pending[identifier] = future
        try:
            await self.send({"id": identifier, "method": method, "params": params})
            return await asyncio.wait_for(future, 30)
        finally:
            self.pending.pop(identifier, None)

    async def _read(self):
        try:
            while line := await self.process.stdout.readline():
                message = json.loads(line)
                if "method" in message and "id" in message:
                    callback = asyncio.create_task(self._server_request(message))
                    self.callbacks.add(callback)
                    self.callback_threads[callback] = message.get("params", {}).get("threadId")
                    def completed(job):
                        self.callbacks.discard(job)
                        self.callback_threads.pop(job, None)
                        if not job.cancelled():
                            job.exception()
                    callback.add_done_callback(completed)
                elif "id" in message:
                    future = self.pending.get(message["id"])
                    if future and not future.done():
                        if "error" in message:
                            future.set_exception(ArgosError("Codex rechazó la solicitud del protocolo."))
                        else:
                            future.set_result(message.get("result", {}))
                else:
                    params = message.get("params", {})
                    thread_id = params.get("threadId")
                    queue = self.queues.get(thread_id)
                    if queue:
                        await queue.put(message)
        except (OSError, ValueError, asyncio.LimitOverrunError):
            pass
        finally:
            for future in list(self.pending.values()):
                if not future.done():
                    future.set_exception(ArgosError("Se perdió la conexión con Codex."))
            for queue in self.queues.values():
                queue.put_nowait({"method": "argos/disconnected"})

    async def _server_request(self, message):
        params = message.get("params", {})
        thread = params.get("threadId")
        handler = self.tools.get(thread)
        if message["method"] == "item/tool/call" and params.get("tool") == "argos_capability" and handler:
            try:
                args = params["arguments"]
                if isinstance(args, str):
                    args = json.loads(args)
                operation_args = json.loads(args["arguments_json"])
                result = await handler(args["capability"], operation_args)
                safe_data(result)
                response = {"contentItems": [{"type": "inputText", "text": json.dumps(result, ensure_ascii=False)}],
                            "success": True}
                await self.send({"id": message["id"], "result": response})
                return
            except asyncio.CancelledError:
                raise
            except Exception as error:
                # Approval suspension and scope errors stop the turn, not retry blindly.
                self.tools.pop(thread, None)
                queue = self.queues.get(thread)
                if queue:
                    queue.put_nowait({"method": "argos/toolError", "exception": error})
                with contextlib.suppress(Exception):
                    await self.send({"id": message["id"], "result": {
                        "contentItems": [{"type": "inputText", "text": "ARGOS suspended this operation. Stop and wait."}],
                        "success": False}})
                return
        # Never let native tools or unexpected server requests grant authority.
        await self.send({"id": message["id"], "error": {
            "code": -32601, "message": "This operation is not exposed by ARGOS."}})

    async def thread(self, agent, thread_id=None, tools=False, ephemeral=False):
        if agent == "general":
            raise ArgosError("Codex está reservado a tareas complejas escaladas, no a conversación General.")
        await self.start()
        params = {"cwd": str(self.directory), "sandbox": "read-only",
                  "approvalPolicy": "never", "developerInstructions": contract(agent),
                  "baseInstructions": "You are a specialist inside ARGOS. Use only the supplied ARGOS contract and tools.",
                  "config": {"project_doc_max_bytes": 0, "web_search": "disabled"},
                  "personality": "none"}
        if thread_id:
            params.update(threadId=thread_id, excludeTurns=True)
            result = await self.rpc("thread/resume", params)
        else:
            params.update(ephemeral=ephemeral, environments=[], dynamicTools=[TOOL] if tools else [])
            result = await self.rpc("thread/start", params)
        if agent == "general" and result.get("model") in self.fast_models:
            self.fast_threads.add(result["thread"]["id"])
        return result["thread"]["id"]

    async def turn(self, thread_id, text, schema, tool_handler=None, progress=None, effort=None):
        queue = asyncio.Queue(maxsize=4096)
        self.queues[thread_id] = queue
        if tool_handler:
            self.tools[thread_id] = tool_handler
        turn_id = None
        messages = []
        try:
            result = await self.rpc("turn/start", {
                "threadId": thread_id, "input": [{"type": "text", "text": text}],
                "outputSchema": schema, "approvalPolicy": "never",
                "sandboxPolicy": {"type": "readOnly", "networkAccess": False},
                "environments": [], "summary": "none",
                **({"effort": effort} if effort else {}),
            })
            turn_id = result["turn"]["id"]
            async with asyncio.timeout(300):
                while True:
                    event = await queue.get()
                    method, params = event.get("method"), event.get("params", {})
                    if method == "argos/toolError":
                        raise event["exception"]
                    if method == "argos/disconnected":
                        raise ArgosError("Codex se desconectó. La tarea requiere revisión.")
                    if method == "item/started":
                        item = params.get("item", {})
                        if item.get("type") in ("commandExecution", "fileChange", "mcpToolCall", "webSearch"):
                            raise ArgosError("Codex intentó utilizar una herramienta fuera del bridge ARGOS.")
                    if method == "item/completed":
                        item = params.get("item", {})
                        if item.get("type") == "agentMessage":
                            text_value = item.get("text", "")
                            if item.get("phase") == "commentary":
                                if progress:
                                    progress(text_value)
                            else:
                                messages.append(text_value)
                    if method == "turn/completed":
                        if params.get("turn", {}).get("status") != "completed":
                            raise ArgosError("El turno de Codex no terminó correctamente.")
                        if not messages:
                            raise ArgosError("Codex no devolvió un resultado estructurado.")
                        try:
                            data = json.loads(messages[-1])
                        except ValueError:
                            raise ArgosError("Codex devolvió un formato inesperado.") from None
                        safe_data(data)
                        return data
        except BaseException:
            if turn_id:
                with contextlib.suppress(Exception):
                    await self.rpc("turn/interrupt", {"threadId": thread_id, "turnId": turn_id})
            raise
        finally:
            self.queues.pop(thread_id, None)
            self.tools.pop(thread_id, None)
            callbacks = [job for job, owner in self.callback_threads.items() if owner == thread_id]
            for job in callbacks:
                job.cancel()
            await asyncio.gather(*callbacks, return_exceptions=True)

    async def prepare(self, context):
        """Connect and create the exact conversation thread; no inference turn."""
        key = (context.get("session", "default"), (context.get("project") or {}).get("id"), "general")
        async with self.chat_locks.setdefault(key, asyncio.Lock()):
            if key not in self.chat_threads:
                self.chat_threads[key] = await self.thread("general", ephemeral=True)

    def conversation_thread(self, context):
        key = (context.get("session", "default"), (context.get("project") or {}).get("id"), "general")
        return self.chat_threads.get(key)

    async def decide(self, text, context, agent="general"):
        key = (context.get("session", "default"), (context.get("project") or {}).get("id"), agent)
        lock = self.chat_locks.setdefault(key, asyncio.Lock())
        async with lock:
            thread_id = self.chat_threads.get(key)
            if thread_id is None:
                thread_id = await self.thread(agent, ephemeral=True)
                self.chat_threads[key] = thread_id
            payload = json.dumps({"request": text, "context": context,
                                  "output_note": "Encode action arguments (capability or panel) as a JSON string in arguments_json."},
                                 ensure_ascii=False)
            data = await self.turn(thread_id, payload, DECISION_SCHEMA,
                                   effort="low" if thread_id in self.fast_threads else None)
            try:
                data["arguments"] = json.loads(data.pop("arguments_json"))
            except (ValueError, KeyError, TypeError):
                raise ArgosError("Codex devolvió argumentos inválidos.") from None
            return validate_decision(data, agent)

    async def work(self, task, context, execute, save_thread, progress):
        thread_id = await self.thread(task["agent"], task.get("thread_id"), tools=True)
        if thread_id != task.get("thread_id"):
            save_thread(thread_id)
        payload = json.dumps({
            "objective": task["objective"], "context": context,
            "instruction": "Perform the requested work with argos_capability. Each call needs capability and arguments_json. "
                           "Use measured tool results. Ask a question only if essential. "
                           "If an operation is suspended, stop. Never claim tests passed without their evidence.",
        }, ensure_ascii=False)
        result = await self.turn(thread_id, payload, RESULT_SCHEMA, execute, progress)
        if (not isinstance(result, dict) or set(result) != {"kind", "speech", "detail"}
                or result["kind"] not in ("result", "question")
                or any(not isinstance(result[key], str) or len(result[key]) > 16000
                       for key in ("speech", "detail"))):
            raise ArgosError("Codex devolvió un resultado inválido.")
        return result

    async def close(self):
        self.connected = False
        for callback in list(self.callbacks):
            callback.cancel()
        await asyncio.gather(*self.callbacks, return_exceptions=True)
        if self.process and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), 3)
            except TimeoutError:
                self.process.kill()
                await self.process.wait()
        if self.reader:
            self.reader.cancel()
            await asyncio.gather(self.reader, return_exceptions=True)
        self.process = self.reader = None
        self.chat_threads.clear()
        self.fast_threads.clear()
        self.fast_models.clear()
