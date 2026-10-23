"""Deterministic transport normalization for mathematical display titles."""
import re


_TITLE = re.compile(
    r'("title"\s*:\s*")((?:[^"\\]|\\.|"(?!\s*(?:,\s*"[^"]+"\s*:|})))*)"(?=\s*(?:,\s*"[^"]+"\s*:|}))'
)
_MATH = re.compile(r'\$\$[\s\S]*?\$\$|\$[^$\r\n]*?\$|\\+\([\s\S]*?\\+\)|\\+\[[\s\S]*?\\+\]')
_SLASHES = re.compile(r'\\+(?=[A-Za-z()[\]])')


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

    def math_region(match):
        text = match[0]
        def slash_run(run):
            value = run[0]
            if len(value) % 2 == 0:
                return value
            if re.match(r'u[0-9a-fA-F]{4}', text[run.end():]):
                return value
            return value + '\\'
        return _SLASHES.sub(slash_run, text)

    normalized = _MATH.sub(math_region, title[2])
    return payload[:title.start(2)] + normalized + payload[title.end(2):]
