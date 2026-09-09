"""Strict structured response envelopes; no fabricated JSON or partial repair."""
import json
import re


def parse_page_response(raw):
    text = str(raw or "").strip().lstrip("\ufeff").strip()
    if not text:
        raise ValueError("script_ppt_response_empty")
    match = re.fullmatch(r"(?P<fence>`{3}|~{3})(?:json)?\s*\n(?P<body>[\s\S]*?)\n(?P=fence)\s*", text, re.IGNORECASE)
    if match:
        text = match["body"].strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"script_ppt_response_invalid_json:line={exc.lineno}:column={exc.colno}") from exc
    if not isinstance(value, dict):
        raise ValueError("script_ppt_response_invalid_shape:expected_object")
    return value
