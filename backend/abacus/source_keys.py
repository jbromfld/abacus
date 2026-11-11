"""Stable exact CSV source identity, shared by writes and import validation."""

import hashlib
import json


def csv_fields_key(source):
    original = source.get("original") if isinstance(source, dict) else None
    if (
        not isinstance(original, dict)
        or not original
        or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in original.items()
        )
    ):
        return None
    return json.dumps(
        original, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )


def fingerprint(key):
    return hashlib.sha256(key.encode("utf-8")).hexdigest()
