import asyncio
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from argos.firefox import play, validate_request
from argos.models import ArgosError

class FirefoxTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.path=Path(self.temp.name)
        code='from pathlib import Path; from argos.firefox import native_main; native_main(Path('+repr(str(self.path))+'))'
        self.host=await asyncio.create_subprocess_exec(sys.executable,'-c',code,stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
        for _ in range(100):
            if (self.path/'firefox.sock').exists(): break
            await asyncio.sleep(.01)
        self.assertTrue((self.path/'firefox.sock').exists())
    async def asyncTearDown(self):
        self.host.stdin.close()
        try: await asyncio.wait_for(self.host.wait(),2)
        except TimeoutError:
            self.host.kill();await self.host.wait()
        self.temp.cleanup()
    async def message(self):
        async with asyncio.timeout(2):
            size=struct.unpack('=I',await self.host.stdout.readexactly(4))[0]
            return json.loads(await self.host.stdout.readexactly(size))
    async def reply(self,data):
        raw=json.dumps(data).encode();self.host.stdin.write(struct.pack('=I',len(raw))+raw);await self.host.stdin.drain()
    async def test_verified_result_crosses_native_pipe_and_private_socket(self):
        task=asyncio.create_task(play(None,{'query':'AC/DC Thunderstruck'},self.path))
        m=await self.message();self.assertEqual(m['query'],'AC/DC Thunderstruck')
        await self.reply({'id':m['id'],'status':'playing','title':'AC/DC - Thunderstruck','url':'https://www.youtube.com/watch?v=v2AC41dglnM'})
        result=await task
        self.assertEqual(result['verification'],'browser_video_advancing')
        self.assertEqual((self.path/'firefox.sock').stat().st_mode & 0o777,0o600)
    async def test_autoplay_block_is_not_success(self):
        task=asyncio.create_task(play(None,{'query':'Song'},self.path));m=await self.message()
        await self.reply({'id':m['id'],'status':'autoplay_blocked'})
        with self.assertRaises(ArgosError): await task
    async def test_unrelated_url_is_rejected(self):
        task=asyncio.create_task(play(None,{'query':'Song'},self.path));m=await self.message()
        await self.reply({'id':m['id'],'status':'playing','title':'Song','url':'https://example.com/'})
        with self.assertRaises(ArgosError): await task
    async def test_cancellation_is_forwarded_and_not_replayed(self):
        task=asyncio.create_task(play(None,{'query':'Song'},self.path));m=await self.message()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        cancel=await self.message()
        self.assertEqual(cancel,{'action':'cancel','id':m['id']})
    async def test_native_input_rejects_unbounded_frame(self):
        self.host.stdin.write(struct.pack('=I',100000));await self.host.stdin.drain()
        await asyncio.wait_for(self.host.wait(),2)
        self.assertFalse((self.path/'firefox.sock').exists())
    async def test_no_arbitrary_action_or_script(self):
        for r in [{'action':'script','query':'alert(1)'},{'action':'play','query':123},{'action':'play','query':'Song','code':'bad'}]:
            with self.assertRaises(ArgosError): validate_request(r)
