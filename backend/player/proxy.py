"""Media proxy for browser playback and ffmpeg downloads.

The HLS rewriting approach (route playlist entries and ``URI=`` attributes back
through a local endpoint) is inspired by ani-cli-ru's reverse proxy
(GPL-3.0, https://github.com/vypivshiy/ani-cli-ru). This implementation is
AnimeBox's own: entries are mapped to session-scoped tokens instead of raw URLs.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urljoin, urlsplit

import httpx
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from backend.player.sessions import MediaSession, UnsafeUpstream, media_sessions, validate_upstream
from backend.providers.http import media_clients

logger = logging.getLogger("animebox.player")

router = APIRouter(prefix="/api/media", tags=["media"])

MAX_PLAYLIST_BYTES = 8 * 1024 * 1024
MAX_REDIRECTS = 5
_PASS_HEADERS = ("content-type", "content-length", "content-encoding", "content-range", "accept-ranges", "last-modified", "etag")
_URI_ATTR = re.compile(r'(URI=)(["\'])([^"\']+)(\2)')


def rewrite_playlist(body: str, base_url: str, session: MediaSession) -> str:
    lines: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            lines.append(line)
        elif not stripped.startswith("#"):
            lines.append(session.url_for(urljoin(base_url, stripped)))
        elif "URI=" in line:
            lines.append(
                _URI_ATTR.sub(
                    lambda m: f"{m.group(1)}{m.group(2)}{session.url_for(urljoin(base_url, m.group(3)))}{m.group(4)}",
                    line,
                )
            )
        else:
            lines.append(line)
    return "\n".join(lines) + "\n"


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"detail": {"code": code, "message": message}}, status_code=status)


def _looks_like_playlist(url: str, content_type: str, length: int | None) -> bool:
    content_type = content_type.lower()
    if "mpegurl" in content_type:
        return True
    if urlsplit(url).path.lower().endswith(".m3u8"):
        return True
    return (content_type.startswith("text/") or "octet-stream" in content_type) and length is not None and length < 1024 * 1024


async def _open_upstream(session: MediaSession, url: str, range_header: str | None) -> tuple[httpx.Response, str]:
    client = media_clients.get(session.proxy)
    headers = dict(session.headers)
    if range_header:
        headers["Range"] = range_header
    for _ in range(MAX_REDIRECTS + 1):
        await validate_upstream(url, proxy=session.proxy)
        response = await client.send(client.build_request("GET", url, headers=headers), stream=True)
        if response.status_code in (301, 302, 303, 307, 308) and response.headers.get("location"):
            await response.aclose()
            url = urljoin(url, response.headers["location"])
            continue
        return response, url
    raise UnsafeUpstream("too many redirects")


@router.get("/{session_id}/{token}/{name}")
async def media(session_id: str, token: str, name: str, request: Request):  # noqa: ARG001 - name is cosmetic
    session = media_sessions.get(session_id)
    if session is None:
        return _error(410, "stream_expired", "Media session expired; resolve the stream again")
    url = session.entries.get(token)
    if url is None:
        return _error(404, "unknown_media", "Unknown media entry")

    try:
        upstream, final_url = await _open_upstream(session, url, request.headers.get("range"))
    except UnsafeUpstream as exc:
        logger.warning("Blocked media request to %s: %s", urlsplit(url).netloc, exc)
        return _error(403, "blocked_upstream", f"Blocked upstream: {exc}")
    except httpx.TimeoutException:
        return _error(504, "upstream_timeout", "Media host did not respond in time")
    except httpx.HTTPError as exc:
        return _error(502, "upstream_error", f"Media host unreachable: {type(exc).__name__}")

    if upstream.status_code >= 400:
        await upstream.aclose()
        code = "stream_expired" if upstream.status_code in (401, 403, 404, 410) else "upstream_error"
        return _error(502, code, f"Media host answered HTTP {upstream.status_code}")

    content_type = upstream.headers.get("content-type", "application/octet-stream")
    length_header = upstream.headers.get("content-length")
    length = int(length_header) if length_header and length_header.isdigit() else None

    if upstream.status_code == 200 and _looks_like_playlist(final_url, content_type, length):
        try:
            raw = bytearray()
            async for chunk in upstream.aiter_bytes():
                raw.extend(chunk)
                if len(raw) > MAX_PLAYLIST_BYTES:
                    return _error(502, "upstream_error", "Playlist too large")
        except httpx.HTTPError as exc:
            return _error(502, "upstream_error", f"Playlist download failed: {type(exc).__name__}")
        finally:
            await upstream.aclose()
        if bytes(raw[:16]).lstrip(b"\xef\xbb\xbf").startswith(b"#EXTM3U"):
            text = raw.decode("utf-8", errors="replace")
            return Response(
                content=rewrite_playlist(text, final_url, session),
                media_type="application/vnd.apple.mpegurl",
                headers={"Cache-Control": "no-store"},
            )
        return Response(content=bytes(raw), media_type=content_type)

    async def body():
        try:
            async for chunk in upstream.aiter_raw(256 * 1024):
                yield chunk
        except httpx.HTTPError as exc:
            logger.info("Media stream interrupted: %s", type(exc).__name__)
        finally:
            await upstream.aclose()

    headers = {key: upstream.headers[key] for key in _PASS_HEADERS if key in upstream.headers}
    headers.pop("content-type", None)
    return StreamingResponse(body(), status_code=upstream.status_code, media_type=content_type, headers=headers)
