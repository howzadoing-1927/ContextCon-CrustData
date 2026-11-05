"""SSRF-safe single-page fetch of a public seller website (doc 03 SourceInput rules).

Every hop: http(s) only, ports 80/443, no URL credentials, hostname resolved here and EVERY resolved address
must be globally routable; the socket then connects to that vetted address (not a second DNS lookup), so
DNS rebinding cannot swap in a private address. Max two redirects, 10 s total, 1 MB after decompression,
HTML/plain text only. Returned text is untrusted evidence, never instructions.
"""

import http.client
import ipaddress
import socket
import ssl
import time
import zlib
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

MAX_BYTES = 1_000_000
MAX_REDIRECTS = 2
TOTAL_SECONDS = 10.0
ALLOWED_PORTS = {"http": 80, "https": 443}
REDIRECT_STATUSES = {301, 302, 303, 307, 308}
USER_AGENT = "OutcomeAI-SourceFetch/1.0 (+single-page seller profile fetch)"


class FetchBlocked(Exception):
    """The URL or a redirect target is not allowed. Callers should offer pasted text instead."""


class FetchFailed(Exception):
    """Network/provider failure for an allowed URL."""


@dataclass(frozen=True)
class FetchedPage:
    requested_url: str
    final_url: str
    status: int
    content_type: str
    text: str
    truncated: bool


def _vet_url(url: str) -> tuple[str, str, int, str]:
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in ALLOWED_PORTS:
        raise FetchBlocked("only http and https URLs are allowed")
    if parts.username or parts.password or "@" in parts.netloc:
        raise FetchBlocked("credentials in URL are not allowed")
    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        raise FetchBlocked("URL has no host")
    try:
        port = parts.port or ALLOWED_PORTS[scheme]
    except ValueError as exc:
        raise FetchBlocked("invalid port") from exc
    if port != ALLOWED_PORTS[scheme]:
        raise FetchBlocked("only default ports 80/443 are allowed")
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise FetchBlocked("local hostnames are not allowed")
    path = parts.path or "/"
    if parts.query:
        path = f"{path}?{parts.query}"
    return scheme, host, port, path


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not (ip.is_multicast or ip.is_reserved or ip.is_loopback or ip.is_link_local)


def resolve_public(host: str, port: int) -> str:
    """Resolve and require every address to be public; return the one to connect to."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise FetchFailed("host did not resolve") from exc
    addresses = sorted({info[4][0] for info in infos})
    if not addresses:
        raise FetchFailed("host did not resolve")
    blocked = [a for a in addresses if not _is_public(a)]
    if blocked:
        raise FetchBlocked("host resolves to a private, loopback, link-local or reserved address")
    ipv4 = [a for a in addresses if ":" not in a]
    return (ipv4 or addresses)[0]


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host: str, address: str, port: int, timeout: float) -> None:
        super().__init__(host, port, timeout=timeout)
        self._address = address

    def connect(self) -> None:
        self.sock = socket.create_connection((self._address, self.port), self.timeout)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, address: str, port: int, timeout: float) -> None:
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self._address = address

    def connect(self) -> None:
        sock = socket.create_connection((self._address, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


@dataclass(frozen=True)
class _Response:
    status: int
    headers: dict[str, str]
    body: bytes
    truncated: bool


def _request_once(url: str, deadline: float) -> _Response:
    scheme, host, port, path = _vet_url(url)
    address = resolve_public(host, port)
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise FetchFailed("fetch timed out")
    cls = _PinnedHTTPSConnection if scheme == "https" else _PinnedHTTPConnection
    conn = cls(host, address, port, timeout=min(remaining, TOTAL_SECONDS))
    try:
        conn.request(
            "GET",
            path,
            headers={"Host": host, "User-Agent": USER_AGENT, "Accept": "text/html,text/plain", "Accept-Encoding": "gzip, identity"},
        )
        resp = conn.getresponse()
        headers = {k.lower(): v for k, v in resp.getheaders()}
        raw = bytearray()
        while len(raw) <= MAX_BYTES:
            if time.monotonic() > deadline:
                raise FetchFailed("fetch timed out")
            chunk = resp.read(65536)
            if not chunk:
                break
            raw.extend(chunk)
        return _Response(resp.status, headers, bytes(raw), truncated=len(raw) > MAX_BYTES)
    except (OSError, http.client.HTTPException) as exc:
        raise FetchFailed(f"connection failed: {type(exc).__name__}") from exc
    finally:
        conn.close()


def _decode_body(response: _Response) -> tuple[str, bool]:
    body, truncated = response.body[: MAX_BYTES + 1], response.truncated
    if response.headers.get("content-encoding", "").lower() == "gzip":
        inflater = zlib.decompressobj(16 + zlib.MAX_WBITS)
        body = inflater.decompress(body, MAX_BYTES + 1)
        truncated = truncated or bool(inflater.unconsumed_tail)
    elif response.headers.get("content-encoding", "identity").lower() not in ("", "identity"):
        raise FetchBlocked("unsupported content encoding")
    if len(body) > MAX_BYTES:
        body, truncated = body[:MAX_BYTES], True
    charset = "utf-8"
    for part in response.headers.get("content-type", "").split(";")[1:]:
        key, _, value = part.strip().partition("=")
        if key.lower() == "charset" and value:
            charset = value.strip("\"'")
    try:
        return body.decode(charset, errors="replace"), truncated
    except LookupError:
        return body.decode("utf-8", errors="replace"), truncated


class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript", "template", "svg", "iframe", "object"}
    BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "tr", "header", "footer"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in self.SKIP:
            self._skip_depth += 1
        elif tag == "title":
            self._in_title = True
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag == "title":
            self._in_title = False
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self.title += data
            return
        self.parts.append(data)


def html_to_text(html: str) -> tuple[str, str]:
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    lines = (" ".join(line.split()) for line in "".join(parser.parts).splitlines())
    return " ".join(parser.title.split()), "\n".join(line for line in lines if line)


def fetch_page(url: str, *, request=_request_once) -> FetchedPage:
    deadline = time.monotonic() + TOTAL_SECONDS
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        response = request(current, deadline)
        if response.status in REDIRECT_STATUSES:
            location = response.headers.get("location")
            if not location:
                raise FetchFailed("redirect without location")
            current = urljoin(current, location)
            continue
        if response.status != 200:
            raise FetchFailed(f"unexpected HTTP status {response.status}")
        content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
        if content_type not in ("text/html", "text/plain", "application/xhtml+xml"):
            raise FetchBlocked(f"unsupported content type {content_type or 'missing'}")
        raw_text, truncated = _decode_body(response)
        title, text = html_to_text(raw_text) if content_type != "text/plain" else ("", raw_text)
        if title:
            text = f"{title}\n{text}"
        if not text.strip():
            raise FetchBlocked("page has no readable text; paste the seller facts instead")
        return FetchedPage(url, current, response.status, content_type, text, truncated)
    raise FetchBlocked("too many redirects")
