"""Canonical hashing for exchanged course and PPT artifacts."""
import hashlib
import json

def digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
