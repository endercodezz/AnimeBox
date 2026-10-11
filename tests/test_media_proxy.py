"""Media proxy: scoped sessions, SSRF protection, header isolation, playlist rewriting."""

from __future__ import annotations

import socket

import httpx
import pytest

from backend.player import proxy, sessions
from backend.player.sessions import UnsafeUpstream, media_sessions, validate_upstream
from backend.providers import http as provider_http

PUBLIC = {"cdn.example.com": "93.184.216.34", "other.example.net": "93.184.216.35", "rebind.example.com": "127.0.0.1"}


@pytest.fixture(autouse=True)
def fake_dns(monkeypatch):
    sessions._dns_cache.clear()

    async def resolve(host, _port):
        if host not in PUBLIC:
            raise socket.gaierror("unknown host")
        return [PUBLIC[host]]

    monkeypatch.setattr(sessions, "_resolve", resolve)
    yield
    sessions._dns_cache.clear()


@pytest.fixture
def upstream(monkeypatch):
    """Route media-client traffic to an in-memory handler and record requests."""
    seen: list[httpx.Request] = []
    responses: dict[str, httpx.Response] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return responses.get(str(request.url), httpx.Response(404))

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(provider_http.media_clients, "get", lambda _proxy: client)
    return seen, responses


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/secret",
        "http://localhost:8787/api/session",
        "http://[::1]/",
        "http://10.0.0.5/admin",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://0.0.0.0/",
        "file:///etc/passwd",
        "ftp://cdn.example.com/x",
        "http://user:pass@cdn.example.com/x",
        "http://rebind.example.com/",  # public name resolving to loopback
        "http://printer.local/",
    ],
)
async def test_validate_upstream_rejects_local_targets(url):
    with pytest.raises(UnsafeUpstream):
        await validate_upstream(url)


async def test_validate_upstream_allows_public_hosts():
    await validate_upstream("https://cdn.example.com/video.m3u8")
    await validate_upstream("https://93.184.216.34/video.mp4")


async def test_arbitrary_urls_cannot_be_proxied(client):
    legacy = await client.get("/api/proxy/stream", params={"url": "http://127.0.0.1:8787/api/session"})
    assert legacy.status_code in (404, 405)

    session = media_sessions.create({}, None, ttl=60)
    unknown = await client.get(f"/api/media/{session.id}/not-issued/x.ts")
    assert unknown.status_code == 404
    expired = await client.get("/api/media/does-not-exist/token/x.ts")
    assert expired.status_code == 410
    assert expired.json()["detail"]["code"] == "stream_expired"


async def test_playlist_is_rewritten_to_session_tokens(client, upstream):
    _seen, responses = upstream
    responses["https://cdn.example.com/show/master.m3u8"] = httpx.Response(
        200,
        headers={"content-type": "application/vnd.apple.mpegurl"},
        text='#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI="keys/k.bin"\n#EXTINF:5,\nseg-1.ts\n#EXTINF:5,\nhttps://other.example.net/seg-2.ts\n',
    )
    session = media_sessions.create({"User-Agent": "UA"}, None, ttl=60)
    response = await client.get(session.url_for("https://cdn.example.com/show/master.m3u8"))
    assert response.status_code == 200
    body = response.text
    assert "cdn.example.com" not in body and "other.example.net" not in body
    issued = set(session.entries.values())
    assert {
        "https://cdn.example.com/show/keys/k.bin",
        "https://cdn.example.com/show/seg-1.ts",
        "https://other.example.net/seg-2.ts",
    } <= issued
    assert f"/api/media/{session.id}/" in body and "seg-1.ts" in body


async def test_segments_stream_with_range_and_only_session_headers(client, upstream):
    seen, responses = upstream
    responses["https://cdn.example.com/seg.ts"] = httpx.Response(
        206, headers={"content-type": "video/mp2t", "content-range": "bytes 0-3/10"}, stream=httpx.ByteStream(b"abcd")
    )
    session = media_sessions.create({"User-Agent": "Provider-UA", "Referer": "https://player.example/"}, None, ttl=60)
    other = media_sessions.create({"Referer": "https://secret.example/", "Cookie": "sid=1"}, None, ttl=60)
    other.url_for("https://cdn.example.com/seg.ts")

    response = await client.get(
        session.url_for("https://cdn.example.com/seg.ts"),
        headers={"Range": "bytes=0-3", "Cookie": "browser=secret"},
    )
    assert response.status_code == 206
    assert response.content == b"abcd"
    sent = seen[-1].headers
    assert sent["range"] == "bytes=0-3"
    assert sent["referer"] == "https://player.example/"
    assert sent["user-agent"] == "Provider-UA"
    assert "cookie" not in sent  # neither the browser's nor another session's cookies


async def test_redirect_to_private_network_is_blocked(client, upstream):
    _seen, responses = upstream
    responses["https://cdn.example.com/redirect.mp4"] = httpx.Response(302, headers={"location": "http://127.0.0.1:8787/api/session"})
    session = media_sessions.create({}, None, ttl=60)
    response = await client.get(session.url_for("https://cdn.example.com/redirect.mp4"))
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "blocked_upstream"


async def test_expired_upstream_link_is_reported_for_re_resolution(client, upstream):
    _seen, responses = upstream
    responses["https://cdn.example.com/old.m3u8"] = httpx.Response(403)
    session = media_sessions.create({}, None, ttl=60)
    response = await client.get(session.url_for("https://cdn.example.com/old.m3u8"))
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "stream_expired"


def test_sessions_expire_and_are_capped(monkeypatch):
    store = sessions.MediaSessionStore()
    session = store.create({}, None, ttl=60)
    assert store.get(session.id) is session
    session.last_used -= 120
    assert store.get(session.id) is None
    monkeypatch.setattr(sessions, "MAX_SESSIONS", 3)
    created = [store.create({}, None, ttl=60) for _ in range(5)]
    assert len(store) == 3 and store.get(created[0].id) is None


def test_media_filename_keeps_extension_and_is_safe():
    assert sessions.media_filename("https://x/a/b/seg-01.ts?token=1") == "seg-01.ts"
    assert sessions.media_filename("https://x/?expires=1") == "media"
    assert "/" not in sessions.media_filename("https://x/..%2F..%2Fetc%2Fpasswd")


def test_rewrite_keeps_comments_and_blank_lines():
    session = media_sessions.create({}, None, ttl=60)
    out = proxy.rewrite_playlist("#EXTM3U\n\n#EXT-X-ENDLIST\n", "https://cdn.example.com/a.m3u8", session)
    assert out == "#EXTM3U\n\n#EXT-X-ENDLIST\n"
