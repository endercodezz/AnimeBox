"""Reverse proxy for browser playback — inspired by ani-cli-ru reverse_proxy patterns."""

from __future__ import annotations

import logging
import re
from urllib.parse import quote, urljoin

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse

logger = logging.getLogger("animebox.player")

router = APIRouter(prefix="/api/proxy", tags=["proxy"])

_HEADER_STORE: dict[str, dict[str, str]] = {}


def store_headers(headers: dict[str, str]) -> str:
    import uuid

    hid = uuid.uuid4().hex
    _HEADER_STORE[hid] = headers
    return hid


def _proxy_url(url: str, hid: str | None) -> str:
    proxied = f"/api/proxy/stream?url={quote(url, safe='')}"
    if hid:
        proxied += f"&hid={hid}"
    return proxied


def _rewrite_m3u8(body: str, base_url: str, hid: str | None) -> str:
    """Rewrite HLS media URLs and URI attributes through local proxy.

    Adapted from ani-cli-ru's GPL-3.0 reverse proxy implementation.
    See THIRD_PARTY.md.
    """
    uri_pattern = re.compile(r'(URI=["\'])([^"\']+)(["\'])')
    lines: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            lines.append(line)
            continue
        if not stripped.startswith("#"):
            lines.append(_proxy_url(urljoin(base_url, stripped), hid))
            continue
        if "URI=" in line:
            line = uri_pattern.sub(
                lambda match: (
                    f"{match.group(1)}"
                    f"{_proxy_url(urljoin(base_url, match.group(2)), hid)}"
                    f"{match.group(3)}"
                ),
                line,
            )
        lines.append(line)
    return "\n".join(lines) + "\n"


@router.get("/stream")
async def proxy_stream(
    request: Request,
    url: str = Query(...),
    hid: str | None = Query(None),
):
    headers = dict(_HEADER_STORE.get(hid or "", {}))
    # Forward Range for seeking
    if range_header := request.headers.get("range"):
        headers["Range"] = range_header

    client = httpx.AsyncClient(follow_redirects=True, timeout=60)
    try:
        req = client.build_request("GET", url, headers=headers)
        upstream = await client.send(req, stream=True)
    except Exception as exc:
        await client.aclose()
        raise HTTPException(502, f"Upstream error: {exc}") from exc

    if upstream.status_code >= 400:
        body = await upstream.aread()
        await upstream.aclose()
        await client.aclose()
        raise HTTPException(upstream.status_code, body.decode("utf-8", errors="ignore")[:500])

    content_type = upstream.headers.get("content-type", "application/octet-stream")
    is_playlist = "mpegurl" in content_type or url.endswith(".m3u8")

    if is_playlist:
        raw = await upstream.aread()
        await upstream.aclose()
        await client.aclose()
        text = raw.decode("utf-8", errors="ignore")
        rewritten = _rewrite_m3u8(text, url, hid)
        return Response(content=rewritten, media_type="application/vnd.apple.mpegurl")

    async def iter_bytes():
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    out_headers = {}
    for key in ("content-length", "content-range", "accept-ranges"):
        if key in upstream.headers:
            out_headers[key] = upstream.headers[key]

    return StreamingResponse(
        iter_bytes(),
        status_code=upstream.status_code,
        media_type=content_type,
        headers=out_headers,
    )
