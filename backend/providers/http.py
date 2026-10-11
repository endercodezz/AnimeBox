"""HTTP clients for providers and media.

- One long-lived client pair per source: cookies and connection pools stay
  scoped to that source and never leak into another provider.
- Connection failures are retried once. HTTP 403/429 and anti-bot pages are
  *final* answers: AnimeBox respects source access restrictions and does not
  retry or work around them (anicli-api's default transport retries 10 times).
- The configured network proxy applies to every request that may produce or
  consume a signed media URL (resolution, playback proxy, downloads). OKCDN
  links embed the requesting IP (``srcIp``); mixing proxied resolution with
  direct playback was the cause of intermittent 403s in 1.x.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from anicli_api._http import HEADERS as ANICLI_HEADERS
from anicli_api._http import BaseHTTPAsync, BaseHTTPSync

logger = logging.getLogger("animebox.http")

# Identity used for extraction. Media requests reuse the exact same User-Agent so a
# CDN that ties signed links to the requesting client sees one consistent client.
EXTRACTION_HEADERS: dict[str, str] = dict(ANICLI_HEADERS)
DEFAULT_USER_AGENT = EXTRACTION_HEADERS["User-Agent"]
DEFAULT_TIMEOUT = httpx.Timeout(15.0, connect=8.0)
MEDIA_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class _RetryOnceAsyncTransport(httpx.AsyncHTTPTransport):
    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        try:
            return await super().handle_async_request(request)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.RemoteProtocolError) as exc:
            logger.debug("Retrying %s %s after %s", request.method, request.url.host, type(exc).__name__)
            await asyncio.sleep(0.4)
            return await super().handle_async_request(request)


class _RetryOnceSyncTransport(httpx.HTTPTransport):
    def handle_request(self, request: httpx.Request) -> httpx.Response:
        try:
            return super().handle_request(request)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.RemoteProtocolError):
            return super().handle_request(request)


def async_transport(proxy: str | None, http2: bool = True) -> httpx.AsyncHTTPTransport:
    return _RetryOnceAsyncTransport(proxy=proxy or None, http2=http2)


def sync_transport(proxy: str | None, http2: bool = True) -> httpx.HTTPTransport:
    return _RetryOnceSyncTransport(proxy=proxy or None, http2=http2)


def make_async_client(proxy: str | None, *, headers: dict[str, str] | None = None, **kwargs: Any) -> BaseHTTPAsync:
    http2 = kwargs.pop("http2", True)
    return BaseHTTPAsync(
        transport=async_transport(proxy, http2=http2),
        headers=dict(headers if headers is not None else EXTRACTION_HEADERS),
        timeout=kwargs.pop("timeout", DEFAULT_TIMEOUT),
        http2=http2,
        **kwargs,
    )


def make_sync_client(proxy: str | None, *, headers: dict[str, str] | None = None, **kwargs: Any) -> BaseHTTPSync:
    http2 = kwargs.pop("http2", True)
    return BaseHTTPSync(
        transport=sync_transport(proxy, http2=http2),
        headers=dict(headers if headers is not None else EXTRACTION_HEADERS),
        timeout=kwargs.pop("timeout", DEFAULT_TIMEOUT),
        http2=http2,
        **kwargs,
    )


class SourceClients:
    """Lazily created client pair for one source."""

    def __init__(self, proxy: str | None) -> None:
        self.proxy = proxy
        self._sync: BaseHTTPSync | None = None
        self._async: BaseHTTPAsync | None = None

    @property
    def sync(self) -> BaseHTTPSync:
        if self._sync is None:
            self._sync = make_sync_client(self.proxy)
        return self._sync

    @property
    def async_(self) -> BaseHTTPAsync:
        if self._async is None or self._async.is_closed:
            self._async = make_async_client(self.proxy)
        return self._async

    async def aclose(self) -> None:
        if self._async is not None:
            await self._async.aclose()
        if self._sync is not None:
            self._sync.close()
        self._async = self._sync = None


class MediaClientPool:
    """Shared, pooled client for media proxying/downloads (one per network config)."""

    def __init__(self) -> None:
        self._clients: dict[str | None, httpx.AsyncClient] = {}

    def get(self, proxy: str | None) -> httpx.AsyncClient:
        client = self._clients.get(proxy)
        if client is None or client.is_closed:
            client = httpx.AsyncClient(
                transport=async_transport(proxy, http2=False),
                timeout=MEDIA_TIMEOUT,
                follow_redirects=False,  # redirects are validated hop by hop
                headers={"User-Agent": DEFAULT_USER_AGENT},
                limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
            )
            self._clients[proxy] = client
        return client

    async def aclose(self) -> None:
        clients, self._clients = list(self._clients.values()), {}
        for client in clients:
            await client.aclose()


media_clients = MediaClientPool()


def redact_proxy(proxy: str | None) -> str | None:
    """Hide credentials in proxy URLs before logging or returning them in diagnostics."""
    if not proxy:
        return proxy
    try:
        url = httpx.URL(proxy)
    except Exception:  # noqa: BLE001
        return "<invalid proxy url>"
    if url.userinfo:
        return str(url.copy_with(username="***", password="***"))
    return proxy
