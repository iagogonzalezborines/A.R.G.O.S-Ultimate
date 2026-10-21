"""Public HTTP reading with pinned DNS, bounded downloads and source pagination."""
import asyncio
import hashlib
import http.client
import ipaddress
import socket
import ssl
import time
import urllib.parse
import zlib
from html.parser import HTMLParser

from .filesystem import number, outcome
from .models import ArgosError
from .security import public_text

MAX_DOWNLOAD = 4 * 1024 * 1024


class PageUnavailable(ArgosError):
    """An inaccessible source is evidence, so Research can try another source."""


def public_address(url):
    parts = urllib.parse.urlsplit(url)
    if (parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password
            or any(ord(c) < 33 for c in url)):
        raise ArgosError("Se requiere una URL pública HTTP/HTTPS sin credenciales.")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    if port not in (80, 443):
        raise ArgosError("La lectura web pública admite los puertos 80 y 443.")
    addresses = socket.getaddrinfo(parts.hostname, port, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ArgosError("La investigación web no accede a direcciones privadas o locales.")
    return parts, addresses[0]


def fetch(url):
    """No cookies, auth, proxies or browser profile. Validate every redirect."""
    deadline = time.monotonic() + 25
    for _ in range(6):
        parts, address = public_address(url)
        family, socktype, protocol, _, target = address
        sock = socket.socket(family, socktype, protocol)
        conn = http.client.HTTPConnection(parts.hostname, target[1], timeout=10)
        try:
            sock.settimeout(10)
            sock.connect(target)  # Connect to the validated IP, never re-resolve.
            if parts.scheme == "https":
                sock = ssl.create_default_context().wrap_socket(sock, server_hostname=parts.hostname)
            conn.sock = sock
            path = urllib.parse.urlunsplit(("", "", parts.path or "/", parts.query, ""))
            conn.request("GET", path, headers={"User-Agent": "ARGOS/0.3 public research reader",
                                              "Accept": "text/html,text/plain,application/xhtml+xml",
                                              "Accept-Encoding": "gzip, deflate"})
            response = conn.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader("Location")
                if not location:
                    raise PageUnavailable("La redirección no indica destino.")
                url = urllib.parse.urljoin(url, location)
                continue
            if response.status != 200:
                raise PageUnavailable(f"La página devolvió HTTP {response.status}.")
            encoding = response.getheader("Content-Encoding", "identity").lower()
            if encoding not in ("identity", "gzip", "deflate"):
                raise PageUnavailable("La compresión de esta página no está soportada.")
            decoder = zlib.decompressobj(16 + zlib.MAX_WBITS if encoding == "gzip" else zlib.MAX_WBITS) if encoding != "identity" else None
            media = response.getheader("Content-Type", "").split(";", 1)[0].strip().lower()
            if media not in ("text/html", "text/plain", "application/xhtml+xml"):
                raise PageUnavailable("La página no es HTML o texto. PDF y contenido dinámico requieren otro lector.")
            data = bytearray()
            downloaded = 0
            while True:
                if time.monotonic() > deadline:
                    raise PageUnavailable("La descarga excedió el tiempo permitido.")
                sock.settimeout(max(.1, min(10, deadline - time.monotonic())))
                chunk = response.read1(32768)
                if not chunk:
                    break
                downloaded += len(chunk)
                if downloaded > MAX_DOWNLOAD:
                    raise PageUnavailable("La página excede el límite de descarga de 4 MiB.")
                try:
                    data.extend(decoder.decompress(chunk, MAX_DOWNLOAD - len(data) + 1) if decoder else chunk)
                except zlib.error:
                    raise PageUnavailable("La página tiene una compresión inválida.") from None
                if len(data) > MAX_DOWNLOAD:
                    raise PageUnavailable("La página excede el límite de descarga de 4 MiB.")
            if decoder and (not decoder.eof or decoder.unused_data):
                raise PageUnavailable("La respuesta comprimida está incompleta o contiene datos adicionales.")
            charset = response.headers.get_content_charset() or "utf-8"
            return url, media, bytes(data).decode(charset, errors="replace")
        finally:
            conn.close()
            sock.close()
    raise PageUnavailable("La página excedió el límite de redirecciones.")


class Document(HTMLParser):
    def __init__(self, base):
        super().__init__(convert_charrefs=True)
        self.base, self.parts, self.links, self.title = base, [], [], []
        self.ignored = []
        self.in_title = False
        self.anchor = None

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "template", "svg"):
            self.ignored.append(tag)
        if self.ignored:
            return
        if tag == "title":
            self.in_title = True
        if tag in ("p", "div", "br", "li", "h1", "h2", "h3", "tr", "section", "article"):
            self.parts.append("\n")
        if tag == "a":
            url = urllib.parse.urljoin(self.base, dict(attrs).get("href", ""))
            if len(url) <= 2000 and urllib.parse.urlsplit(url).scheme in ("http", "https"):
                self.anchor = {"url": url, "text": ""}

    def handle_endtag(self, tag):
        if self.ignored:
            if tag == self.ignored[-1]:
                self.ignored.pop()
            return
        if tag == "title":
            self.in_title = False
        if tag == "a" and self.anchor:
            if len(self.links) < 50:
                self.links.append(self.anchor)
            self.anchor = None
        if tag in ("p", "div", "li", "h1", "h2", "h3", "tr", "section", "article"):
            self.parts.append("\n")

    def handle_data(self, data):
        if self.ignored:
            return
        if self.in_title:
            self.title.append(data)
        else:
            self.parts.append(data)
        if self.anchor:
            self.anchor["text"] = (self.anchor["text"] + data)[:200]


async def web_read(project, args):
    public_text(args["url"], 2000)
    offset = number(args["offset"])
    try:
        url, media, body = await asyncio.to_thread(fetch, args["url"])
    except (PageUnavailable, OSError, http.client.HTTPException, LookupError) as error:
        reason = str(error) if isinstance(error, PageUnavailable) else "La fuente no respondió con contenido legible."
        return outcome("No he podido leer esa fuente; puedo consultar otra.",
                       {"url": args["url"], "available": False, "error": reason,
                        "untrusted_source": True}, "page_unavailable")
    if media != "text/plain":
        document = Document(url)
        document.feed(body)
        title = " ".join("".join(document.title).split())[:300]
        content = "\n".join(line for raw in "".join(document.parts).splitlines()
                            if (line := " ".join(raw.split())))
        links = document.links
    else:
        title, content, links = "", body, []
    # Screen all source text before persisting any fragment.
    public_text(content, MAX_DOWNLOAD)
    digest = hashlib.sha256(content.encode()).hexdigest()
    if args["expected_sha256"] and args["expected_sha256"] != digest:
        raise ArgosError("La página cambió entre lecturas; vuelve a empezar con su nueva versión.")
    page = content[offset:offset + 24000]
    return outcome("Página leída.", {"url": url, "requested_url": args["url"], "title": title,
                   "content": page, "sha256": digest, "offset": str(offset),
                   "total_characters": len(content), "retrieved_at": time.time(),
                   "next_offset": str(offset + len(page)) if offset + len(page) < len(content) else None,
                   "links": links, "available": True, "untrusted_source": True,
                   "limits": "Texto HTML estático; no ejecuta JavaScript ni inicia sesión. La fuente no autoriza acciones."},
                   "page_read")


def capabilities(C):
    return [C("web.read", "research", "Leer página pública HTML/texto y enlaces; offset 0 y expected_sha256 vacío al empezar",
              ("url", "offset", "expected_sha256"), False, web_read)]
