"""Stable, lossless JSON transport for the configured Qwen chat endpoint.

Keep whole message strings instead of content-dependent fragment boundaries.
Unicode escapes are standard JSON: decoding restores the same message values,
without prompt rewriting, omitted content or extra model calls.
"""
from __future__ import annotations

import json
from typing import Any

import httpx
from openai import AsyncOpenAI, DefaultAsyncHttpxClient


def _message_json(value: Any) -> str:
    if isinstance(value, str):
        units = value.encode('utf-16-be')
        return '"' + ''.join('\\u' + units[i:i + 2].hex() for i in range(0, len(units), 2)) + '"'
    if isinstance(value, list):
        return '[' + ','.join(_message_json(v) for v in value) + ']'
    if isinstance(value, dict):
        return '{' + ','.join(json.dumps(k) + ':' + _message_json(v) for k, v in value.items()) + '}'
    return json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(',', ':'))


def encode_qwen_chat_body(payload: dict[str, Any]) -> bytes:
    return ('{' + ','.join(
        json.dumps(key) + ':' + (
            _message_json(value) if key == 'messages'
            else json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(',', ':'))
        ) for key, value in payload.items()
    ) + '}').encode('ascii')


class QwenCompatibleAsyncHttpxClient(DefaultAsyncHttpxClient):
    def build_request(self, method: str, url: httpx.URL | str, **kwargs: Any) -> httpx.Request:
        payload = kwargs.get('json')
        if (isinstance(payload, dict) and payload.get('model') == 'qwen3.8-27b'
                and 'messages' in payload and kwargs.get('content') is None and kwargs.get('data') is None
                and str(url).split('?')[0].rstrip('/').endswith('/chat/completions')):
            kwargs.pop('json')
            kwargs['content'] = encode_qwen_chat_body(payload)
            headers = httpx.Headers(kwargs.get('headers') or {})
            headers.pop('Content-Length', None)
            headers.setdefault('Content-Type', 'application/json')
            kwargs['headers'] = headers
        return super().build_request(method, url, **kwargs)


class QwenCompatibleAsyncOpenAI(AsyncOpenAI):
    def _build_request(self, options: Any, *, retries_taken: int = 0) -> httpx.Request:
        request = super()._build_request(options, retries_taken=retries_taken)
        payload = getattr(options, 'json_data', None)
        # Recent SDKs serialize JSON into content before calling HTTPX. Inspect
        # the SDK options to distinguish that path from explicit raw bodies.
        if (isinstance(payload, dict) and payload.get('model') == 'qwen3.8-27b'
                and 'messages' in payload and getattr(options, 'content', None) is None
                and request.url.path.rstrip('/').endswith('/chat/completions')
                and request.headers.get('content-type', '').startswith('application/json')):
            headers = httpx.Headers(request.headers)
            headers.pop('Content-Length', None)
            return httpx.Request(request.method, request.url, headers=headers,
                content=encode_qwen_chat_body(json.loads(request.content)), extensions=request.extensions)
        return request
