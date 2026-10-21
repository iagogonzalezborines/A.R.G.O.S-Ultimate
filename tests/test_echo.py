import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from argos.echo import EchoCancellation
from argos.models import ArgosError


class EchoTests(unittest.IsolatedAsyncioTestCase):
    def child(self):
        child = SimpleNamespace(returncode=None, wait=AsyncMock(return_value=0))
        child.terminate = Mock(side_effect=lambda: setattr(child, "returncode", 0))
        return child

    async def test_private_nodes_route_selected_mic_and_default_output_without_changing_defaults(self):
        echo, child = EchoCancellation(), self.child()
        device = 'chosen microphone "quoted" #1'
        async def command(argv, **kwargs):
            if argv == ["pactl", "get-default-sink"]:
                return 0, "speakers\n", ""
            self.assertEqual(argv, ["pw-dump"])
            return 0, json.dumps([{"info": {"props": {"node.name": name}}}
                                  for name in (echo.source, echo.sink, device, "speakers")]), ""
        with patch("argos.echo.shutil.which", return_value="installed"), \
             patch("argos.echo.process", side_effect=command), \
             patch("asyncio.create_subprocess_exec", AsyncMock(return_value=child)) as spawn:
            self.assertTrue(await echo.start(device))
            self.assertTrue(echo.active)
            argv = spawn.call_args.args
            self.assertEqual(argv[:4], ("pw-cli", "--monitor", "load-module", "libpipewire-module-echo-cancel"))
            config = json.loads(argv[4])
            self.assertNotIn("#", argv[4])  # pw-cli treats even quoted # as a comment.
            self.assertEqual(config["capture.props"]["target.object"], device)
            self.assertTrue(config["capture.props"]["node.dont-fallback"])
            self.assertEqual(config["playback.props"]["target.object"], "speakers")
            self.assertEqual(config["sink.props"]["priority.session"], 0)
            await echo.stop()
            child.terminate.assert_called_once()
            self.assertFalse(echo.active)
            self.assertIsNone(echo.process)

    async def test_defaults_are_resolved_before_virtual_devices_are_published(self):
        echo, child = EchoCancellation(), self.child()
        async def command(argv, **kwargs):
            if argv == ["pactl", "get-default-source"]:
                return 0, "mic\n", ""
            if argv == ["pactl", "get-default-sink"]:
                return 0, "speakers\n", ""
            return 0, json.dumps([{"info": {"props": {"node.name": name}}}
                                  for name in (echo.source, echo.sink, "mic", "speakers")]), ""
        with patch("argos.echo.shutil.which", return_value="installed"), \
             patch("argos.echo.process", side_effect=command) as commands, \
             patch("asyncio.create_subprocess_exec", AsyncMock(return_value=child)):
            self.assertTrue(await echo.start())
            self.assertEqual(commands.call_args_list[0].args[0], ["pactl", "get-default-source"])
            await echo.stop()

    async def test_missing_tools_do_not_claim_aec_or_open_audio(self):
        echo = EchoCancellation()
        with patch("argos.echo.shutil.which", return_value=None), \
             patch("asyncio.create_subprocess_exec", AsyncMock()) as spawn:
            self.assertFalse(await echo.start())
            spawn.assert_not_called()
        self.assertFalse(echo.active)
        self.assertIn("interrupción", echo.last_error)

    async def test_failed_start_reaps_child_and_never_enables_barge_in(self):
        echo, child = EchoCancellation(), self.child()
        with patch("argos.echo.shutil.which", return_value="installed"), \
             patch("argos.echo.process", AsyncMock(side_effect=[(0, "speakers", ""), TimeoutError()])), \
             patch("asyncio.create_subprocess_exec", AsyncMock(return_value=child)):
            self.assertFalse(await echo.start("mic"))
        child.terminate.assert_called_once()
        self.assertFalse(echo.active)
        self.assertIsNone(echo.process)

    async def test_cancelled_setup_removes_virtual_devices(self):
        echo, child, entered = EchoCancellation(), self.child(), asyncio.Event()
        async def command(argv, **kwargs):
            if argv[0] == "pactl":
                return 0, "speakers", ""
            entered.set()
            await asyncio.Event().wait()
        with patch("argos.echo.shutil.which", return_value="installed"), \
             patch("argos.echo.process", side_effect=command), \
             patch("asyncio.create_subprocess_exec", AsyncMock(return_value=child)):
            task = asyncio.create_task(echo.start("mic"))
            await entered.wait()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        child.terminate.assert_called_once()
        self.assertFalse(echo.active)
        self.assertIsNone(echo.process)

    async def test_loss_of_aec_is_an_error_not_raw_microphone_fallback(self):
        echo = EchoCancellation()
        echo.active = True
        echo.process = self.child()
        with self.assertRaises(ArgosError):
            await echo.watch()
        self.assertFalse(echo.active)
        await echo.stop()
