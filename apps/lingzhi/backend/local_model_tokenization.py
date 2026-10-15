"""Count the configured local model's chat input without generating or shortening it."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from urllib.parse import urlparse

import httpx


def prompt_digest(prompt: str, system_prompt: str) -> str:
    return hashlib.sha256((system_prompt + '\0' + prompt).encode('utf-8')).hexdigest()


@dataclass(frozen=True)
class MeasuredChatInput:
    tokens: int
    digest: str


async def measure_local_chat_input(api_base: str, api_key: str, prompt: str, system_prompt: str) -> MeasuredChatInput | None:
    # Only the already configured loopback llama.cpp service supports these routes.
    # Remote providers keep the existing conservative estimate and receive no extra requests.
    parsed = urlparse(api_base)
    if os.getenv('AI_LOCAL_PROVIDER') != 'http' or parsed.hostname not in {'127.0.0.1', 'localhost', '::1'}:
        return None
    root = api_base.rstrip('/').removesuffix('/v1')
    messages = [{'role': 'system', 'content': system_prompt}, {'role': 'user', 'content': prompt}]
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
            headers = {'Authorization': f'Bearer {api_key}'} if api_key else {}
            template = await client.post(root + '/apply-template', headers=headers,
                json={'messages': messages, 'add_generation_prompt': True, 'enable_thinking': False})
            template.raise_for_status()
            text = template.json().get('prompt')
            if not isinstance(text, str) or not text:
                return None
            result = await client.post(root + '/tokenize', headers=headers,
                json={'content': text, 'add_special': False})
            result.raise_for_status()
            tokens = result.json().get('tokens')
            if not isinstance(tokens, list) or not tokens or any(type(token) is not int or token < 0 for token in tokens):
                return None
            return MeasuredChatInput(len(tokens), prompt_digest(prompt, system_prompt))
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        return None
