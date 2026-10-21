import asyncio
import gzip
import socket
import tempfile
import unittest
import uuid
from email.message import Message
from pathlib import Path
from unittest.mock import patch

from argos.core import Core
from argos.models import ArgosError
from argos.store import Store
from argos.web_reader import PageUnavailable, fetch, public_address, web_read


class WebReaderTests(unittest.IsolatedAsyncioTestCase):
    async def test_extract_links_remove_scripts_and_read_all_pages(self):
        text = "Primera fuente. " * 4000
        html = f'<html><title> Fuente A </title><script>hidden()</script><style>hidden</style><p>{text}</p><a href="/next">Siguiente</a></html>'
        with patch("argos.web_reader.fetch", return_value=("https://example.org/page", "text/html", html)):
            result = await web_read(None, {"url": "https://example.org/page", "offset": "0", "expected_sha256": ""})
            first = result["evidence"]
            self.assertNotIn("hidden", first["content"])
            self.assertEqual(first["title"], "Fuente A")
            self.assertEqual(first["links"], [{"url": "https://example.org/next", "text": "Siguiente"}])
            content = first["content"]
            while result["evidence"]["next_offset"]:
                result = await web_read(None, {"url": "https://example.org/page", "offset": result["evidence"]["next_offset"],
                                              "expected_sha256": first["sha256"]})
                content += result["evidence"]["content"]
            self.assertEqual(content, text.strip() + "\nSiguiente")

    async def test_changed_page_and_secret_source_are_rejected(self):
        with patch("argos.web_reader.fetch", return_value=("https://example.org", "text/plain", "changed")):
            with self.assertRaises(ArgosError):
                await web_read(None, {"url": "https://example.org", "offset": "0", "expected_sha256": "old"})
        with patch("argos.web_reader.fetch", return_value=("https://example.org", "text/plain", "password=secret-value")):
            with self.assertRaises(ArgosError):
                await web_read(None, {"url": "https://example.org", "offset": "0", "expected_sha256": ""})

    async def test_unavailable_source_returns_evidence_to_allow_another_attempt(self):
        with patch("argos.web_reader.fetch", side_effect=PageUnavailable("La página devolvió HTTP 403.")):
            result = await web_read(None, {"url": "https://example.org", "offset": "0", "expected_sha256": ""})
        self.assertEqual(result["verification"], "page_unavailable")
        self.assertFalse(result["evidence"]["available"])
        self.assertNotIn("content", result["evidence"])

    def test_public_reader_rejects_local_private_and_credentials(self):
        for address in ("127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "192.168.1.1", "::ffff:127.0.0.1"):
            with patch("socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 80))]):
                with self.assertRaises(ArgosError):
                    public_address("http://example.org/")
        for url in ("file:///etc/passwd", "http://user:pass@example.org", "http://example.org:8080", "http://example.org/\n"):
            with self.assertRaises(ArgosError):
                public_address(url)

    def test_pinned_address_and_redirect_revalidation(self):
        addresses = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))]
        connections = []
        class Sock:
            def __init__(self, *args):
                pass
            def settimeout(self, value):
                pass
            def connect(self, target):
                connections.append(target)
            def close(self):
                pass
        class Response:
            status = 302
            def getheader(self, name, default=None):
                return "http://127.0.0.1/private" if name == "Location" else default
        class Connection:
            def __init__(self, *args, **kwargs):
                pass
            def request(self, *args, **kwargs):
                pass
            def getresponse(self):
                return Response()
            def close(self):
                pass
        def resolve(host, *args, **kwargs):
            return addresses if host == "public.example" else [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))]
        with patch("socket.getaddrinfo", side_effect=resolve), patch("socket.socket", Sock), \
             patch("http.client.HTTPConnection", Connection):
            with self.assertRaises(ArgosError):
                fetch("http://public.example")
        self.assertEqual(connections, [("93.184.216.34", 80)])

    def test_http_reader_limits_type_size_and_redirects(self):
        class Sock:
            def __init__(self, *args):
                pass
            def settimeout(self, value):
                pass
            def connect(self, target):
                pass
            def close(self):
                pass
        class Response:
            status = 200
            media = "text/plain"
            encoding = "identity"
            headers = Message()
            body = b"text"
            def getheader(self, name, default=None):
                return {"Content-Type": self.media, "Content-Encoding": self.encoding,
                        "Location": "http://public.example/again"}.get(name, default)
            def read1(self, count):
                result, self.body = self.body[:count], self.body[count:]
                return result
        response = Response()
        class Connection:
            def __init__(self, *args, **kwargs):
                pass
            def request(self, *args, **kwargs):
                pass
            def getresponse(self):
                return response
            def close(self):
                pass
        addresses = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))]
        with patch("socket.getaddrinfo", return_value=addresses), patch("socket.socket", Sock), \
             patch("http.client.HTTPConnection", Connection):
            self.assertEqual(fetch("http://public.example")[2], "text")
            response.encoding, response.body = "gzip", gzip.compress("Texto comprimido á".encode())
            self.assertEqual(fetch("http://public.example")[2], "Texto comprimido á")
            response.body = gzip.compress(b"x" * (4 * 1024 * 1024 + 1))
            with self.assertRaises(ArgosError):
                fetch("http://public.example")
            response.encoding = "identity"
            response.media = "application/pdf"
            with self.assertRaises(ArgosError):
                fetch("http://public.example")
            response.media, response.body = "text/html", b"a" * (4 * 1024 * 1024 + 1)
            with self.assertRaises(ArgosError):
                fetch("http://public.example")
            response.status = 302
            with self.assertRaises(ArgosError):
                fetch("http://public.example")

    async def test_specialist_searches_reads_multiple_sources_and_retains_evidence(self):
        observed = []
        class Provider:
            name = "fake-codex"
            async def work(self, task, context, execute, save_thread, progress):
                save_thread("research-thread")
                await execute("web.search", {"query": "official topic sources"})
                for url in ("https://one.example/page", "https://two.example/page"):
                    result = await execute("web.read", {"url": url, "offset": "0", "expected_sha256": ""})
                    observed.append(result["evidence"]["content"])
                return {"kind": "result", "speech": "Dos fuentes contrastadas.",
                        "detail": "Fuente uno https://one.example/page y fuente dos https://two.example/page"}
        async def search(project, args):
            return {"speech": "Encontradas.", "evidence": {"results": []}, "verification": "search_results_received"}
        from dataclasses import replace
        from argos.capabilities import CAPABILITIES
        with tempfile.TemporaryDirectory() as temporary:
            store = Store(Path(temporary))
            core = Core(store, Provider())
            await core.start()
            try:
                with patch.dict(CAPABILITIES, {"web.search": replace(CAPABILITIES["web.search"], execute=search)}), \
                     patch("argos.web_reader.fetch", side_effect=lambda url: (url, "text/plain", "Evidence from " + url)):
                    result = await core.request({"method": "say", "text": "investiga este tema", "request_id": uuid.uuid4().hex})
                    await asyncio.wait_for(core.queue.join(), 5)
                task = store.task(result["task_id"])
                self.assertEqual(task["status"], "COMPLETED")
                self.assertEqual(task["result"]["operations"], 3)
                self.assertEqual(len(observed), 2)
                events = [e for e in store.events(task["id"]) if e["kind"] == "CAPABILITY_RESULT"]
                self.assertEqual(len(events), 3)
            finally:
                await core.close()
                store.close()
