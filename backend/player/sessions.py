"""Scoped media sessions for the playback/download proxy.

A session is created only by the backend after it resolved a stream. It holds
the upstream request headers and a table ``token -> upstream URL``. Clients can
fetch only tokens the server itself issued (the resolved URL and URLs found in
playlists it rewrote), so the proxy cannot be pointed at arbitrary hosts.
Every upstream hop is additionally checked against loopback/private networks.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import re
import secrets
import socket
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from urllib.parse import unquote, urlsplit

logger = logging.getLogger("animebox.media")

MAX_SESSIONS = 300
MAX_ENTRIES_PER_SESSION = 200_000
_DNS_TTL = 300.0


class UnsafeUpstream(ValueError):
    pass


@dataclass
class MediaSession:
    id: str
    headers: dict[str, str]
    proxy: str | None
    ttl: float
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    entries: dict[str, str] = field(default_factory=dict)
    _reverse: dict[str, str] = field(default_factory=dict, repr=False)

    def token_for(self, url: str) -> str:
        token = self._reverse.get(url)
        if token is None:
            if len(self.entries) >= MAX_ENTRIES_PER_SESSION:
                raise UnsafeUpstream("media session entry limit reached")
            token = secrets.token_urlsafe(9)
            self.entries[token] = url
            self._reverse[url] = token
        return token

    def url_for(self, url: str) -> str:
        return f"/api/media/{self.id}/{self.token_for(url)}/{media_filename(url)}"

    @property
    def expires_at(self) -> float:
        return self.last_used + self.ttl

    def expired(self, now: float | None = None) -> bool:
        return (now or time.time()) > self.expires_at


def media_filename(url: str) -> str:
    """Last path segment (keeps the extension ffmpeg's HLS demuxer checks)."""
    name = unquote(urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]) or "media"
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)[-80:].strip("._") or "media"
    return name


class MediaSessionStore:
    def __init__(self) -> None:
        self._sessions: OrderedDict[str, MediaSession] = OrderedDict()

    def create(self, headers: dict[str, str], proxy: str | None, ttl: float) -> MediaSession:
        self.purge()
        session = MediaSession(id=secrets.token_urlsafe(16), headers=dict(headers), proxy=proxy, ttl=ttl)
        self._sessions[session.id] = session
        while len(self._sessions) > MAX_SESSIONS:
            self._sessions.popitem(last=False)
        return session

    def get(self, session_id: str) -> MediaSession | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if session.expired():
            self._sessions.pop(session_id, None)
            return None
        session.last_used = time.time()
        self._sessions.move_to_end(session_id)
        return session

    def drop(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def purge(self) -> int:
        now = time.time()
        expired = [sid for sid, s in self._sessions.items() if s.expired(now)]
        for sid in expired:
            self._sessions.pop(sid, None)
        return len(expired)

    def __len__(self) -> int:
        return len(self._sessions)


media_sessions = MediaSessionStore()

_dns_cache: dict[str, tuple[float, bool]] = {}


async def _resolve(host: str, port: int) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [info[4][0] for info in infos]


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


async def validate_upstream(url: str, *, proxy: str | None = None) -> None:
    """Reject non-HTTP URLs and URLs pointing at loopback, private, link-local or reserved addresses."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise UnsafeUpstream(f"unsupported scheme {parts.scheme!r}")
    host = (parts.hostname or "").strip().lower()
    if not host:
        raise UnsafeUpstream("missing host")
    if parts.username or parts.password:
        raise UnsafeUpstream("credentials in URL are not allowed")
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise UnsafeUpstream("local host names are not allowed")
    try:
        ipaddress.ip_address(host)
        literal = True
    except ValueError:
        literal = False
    if literal:
        if not _is_public(host):
            raise UnsafeUpstream("private or local address")
        return

    cached = _dns_cache.get(host)
    if cached and time.monotonic() - cached[0] < _DNS_TTL:
        if not cached[1]:
            raise UnsafeUpstream("host resolves to a private or local address")
        return
    try:
        addresses = await _resolve(host, parts.port or 443)
    except OSError:
        if proxy:
            return  # only the configured proxy can resolve this name
        raise UnsafeUpstream(f"cannot resolve {host}") from None
    public = bool(addresses) and all(_is_public(address) for address in addresses)
    _dns_cache[host] = (time.monotonic(), public)
    if not public:
        raise UnsafeUpstream("host resolves to a private or local address")
