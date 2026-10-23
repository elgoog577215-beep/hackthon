"""Deterministic transport normalization for mathematical display titles."""
import re
from math_json_transport import escape_math_transport


_TITLE = re.compile(
    r'("title"\s*:\s*")((?:[^"\\]|\\.|"(?!\s*(?:,\s*"[^"]+"\s*:|})))*)"(?=\s*(?:,\s*"[^"]+"\s*:|}))'
)


def normalize_title_math_transport(payload: str) -> str:
    """Escape odd TeX slash runs in explicit math, leaving JSON structure alone.

    Already JSON-escaped runs are unchanged. JSON Unicode escapes retain their
    meaning. No recovery applies to identity fields, references, ordinary prose,
    missing delimiters or duplicate fields; the normal parser validates those.
    """
    titles = list(_TITLE.finditer(payload))
    if len(titles) != 1:
        return payload
    title = titles[0]

    normalized = escape_math_transport(title[2])
    return payload[:title.start(2)] + normalized + payload[title.end(2):]
