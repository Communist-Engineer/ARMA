"""RFC 8785 JSON Canonicalization Scheme boundary."""

from __future__ import annotations

import rfc8785


def canonical_json_bytes(value: object) -> bytes:
    """Serialize a JSON-compatible value with RFC 8785 semantics."""

    return rfc8785.dumps(value)  # pyright: ignore[reportArgumentType]
