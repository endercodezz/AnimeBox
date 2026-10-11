"""Provider error taxonomy. Each error carries the pipeline stage that failed."""

from __future__ import annotations

STAGES = ("search", "details", "episodes", "voiceovers", "stream")


class ProviderError(Exception):
    code = "provider_error"
    http_status = 502

    def __init__(self, message: str, *, source: str | None = None, stage: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.source = source
        self.stage = stage

    def to_detail(self) -> dict:
        return {"code": self.code, "message": self.message, "source": self.source, "stage": self.stage}


class ProviderTimeout(ProviderError):
    code = "provider_timeout"
    http_status = 504


class ProviderUnavailable(ProviderError):
    """Source disabled, unknown, or failed to load."""

    code = "provider_unavailable"
    http_status = 503


class NotFound(ProviderError, LookupError):
    code = "not_found"
    http_status = 404


class CacheExpired(NotFound):
    code = "search_expired"
    http_status = 410


class StreamUnavailable(ProviderError):
    code = "stream_unavailable"
    http_status = 502

    def __init__(self, message: str, *, attempts: list[dict] | None = None, **kwargs) -> None:
        super().__init__(message, **kwargs)
        self.attempts = attempts or []

    def to_detail(self) -> dict:
        detail = super().to_detail()
        detail["attempts"] = self.attempts
        return detail
