"""Provider layer. ``ids`` is import-light; the registry pulls in anicli-api."""

from backend.providers.ids import canonical_id, decode_external_id, encode_external_id, safe_canonical_id


def get_registry():
    from backend.providers.registry import get_registry as _get

    return _get()


__all__ = ["canonical_id", "decode_external_id", "encode_external_id", "get_registry", "safe_canonical_id"]
