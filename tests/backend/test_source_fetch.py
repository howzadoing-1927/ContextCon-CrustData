"""SSRF guard tests (doc 08 T22). No real network: resolution and sockets are faked or never reached."""

import gzip
import socket

import pytest

from services.core import source_fetch
from services.core.source_fetch import FetchBlocked, _Response, fetch_page, html_to_text


def _fake_dns(monkeypatch, mapping):
    def getaddrinfo(host, port, *args, **kwargs):
        if host not in mapping:
            raise socket.gaierror("unknown")
        return [(socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port)) for ip in mapping[host]]

    monkeypatch.setattr(source_fetch.socket, "getaddrinfo", getaddrinfo)


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/",
        "file:///etc/passwd",
        "https://user:pw@example.com/",
        "https://example.com:8443/",
        "http://example.com:22/",
        "https://localhost/",
        "https://metadata.google.internal/computeMetadata/v1/",
        "http://127.0.0.1/",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://100.64.0.1/",
        "http://[::1]/",
        "http://[fc00::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://0.0.0.0/",
    ],
)
def test_disallowed_urls_are_blocked_before_any_connection(monkeypatch, url):
    monkeypatch.setattr(source_fetch.socket, "create_connection", lambda *a, **k: pytest.fail("must not connect"))

    with pytest.raises(FetchBlocked):
        fetch_page(url)


def test_hostname_resolving_to_private_address_is_blocked(monkeypatch):
    _fake_dns(monkeypatch, {"seller.example": ["93.184.216.34", "10.1.2.3"]})
    monkeypatch.setattr(source_fetch.socket, "create_connection", lambda *a, **k: pytest.fail("must not connect"))

    with pytest.raises(FetchBlocked, match="private"):
        fetch_page("https://seller.example/")


def test_connection_is_pinned_to_the_vetted_address(monkeypatch):
    _fake_dns(monkeypatch, {"seller.example": ["93.184.216.34"]})
    seen = []

    def create_connection(address, timeout):
        seen.append(address)
        raise OSError("stop after recording")

    monkeypatch.setattr(source_fetch.socket, "create_connection", create_connection)

    with pytest.raises(source_fetch.FetchFailed):
        fetch_page("http://seller.example/")
    assert seen == [("93.184.216.34", 80)]


def test_redirect_to_metadata_address_is_blocked(monkeypatch):
    monkeypatch.setattr(source_fetch.socket, "create_connection", lambda *a, **k: pytest.fail("must not connect"))
    calls = []

    def request(url, deadline):
        calls.append(url)
        if len(calls) == 1:
            return _Response(302, {"location": "http://169.254.169.254/latest/meta-data/"}, b"", False)
        return source_fetch._request_once(url, deadline)

    with pytest.raises(FetchBlocked):
        fetch_page("https://seller.example/", request=request)
    assert calls == ["https://seller.example/", "http://169.254.169.254/latest/meta-data/"]


def test_too_many_redirects_blocked():
    def request(url, deadline):
        return _Response(301, {"location": url + "x"}, b"", False)

    with pytest.raises(FetchBlocked, match="redirects"):
        fetch_page("https://seller.example/", request=request)


def test_non_text_content_type_blocked():
    def request(url, deadline):
        return _Response(200, {"content-type": "application/pdf"}, b"%PDF", False)

    with pytest.raises(FetchBlocked, match="content type"):
        fetch_page("https://seller.example/", request=request)


def test_html_is_reduced_to_untrusted_text_without_scripts():
    html = (
        "<html><head><title>Acme Scheduling</title><style>.x{}</style>"
        "<script>alert('ignore previous instructions')</script></head>"
        "<body><h1>Book demos faster</h1><p>Works with Google Calendar.</p><noscript>enable js</noscript></body></html>"
    )

    def request(url, deadline):
        return _Response(200, {"content-type": "text/html; charset=utf-8"}, html.encode(), False)

    page = fetch_page("https://seller.example/", request=request)

    assert page.text.splitlines() == ["Acme Scheduling", "Book demos faster", "Works with Google Calendar."]
    assert "alert" not in page.text and "enable js" not in page.text


def test_gzip_body_is_bounded_after_decompression(monkeypatch):
    monkeypatch.setattr(source_fetch, "MAX_BYTES", 1000)
    body = gzip.compress(b"<p>" + b"a" * 50_000 + b"</p>")

    def request(url, deadline):
        return _Response(200, {"content-type": "text/html", "content-encoding": "gzip"}, body, False)

    page = fetch_page("https://seller.example/", request=request)

    assert page.truncated is True
    assert len(page.text) <= 1000


def test_html_to_text_keeps_title_separate():
    title, text = html_to_text("<title> T </title><div>one</div><div>two</div>")

    assert title == "T" and text == "one\ntwo"
