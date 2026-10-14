import json

import httpx
import pytest
from openai import AsyncOpenAI

from qwen_wire import QwenCompatibleAsyncHttpxClient, encode_qwen_chat_body


@pytest.mark.parametrize('text', [
    'Directory.CreateDirectory(Path.GetDirectoryName(savePath));',
    '红黑树、跳表、B+树\n```cpp\nnode->left = child;\n```\n\\[h=\\log n\\] 🧪 "quote"',
    '完整教学内容' * 12000,
], ids=['code', 'unicode', 'long'])
def test_wire_encoding_preserves_all_message_text_and_generation_options(text):
    payload = {'model': 'qwen3.8-27b', 'messages': [
        {'role': 'system', 'content': '原教学目标不删减'},
        {'role': 'user', 'content': text},
    ], 'max_tokens': 32000, 'stream': True, 'extra_body': {'enable_thinking': False}, 'temperature': .2}
    wire = encode_qwen_chat_body(payload)
    assert wire.isascii()
    assert json.loads(wire) == payload
    assert text.encode('utf-8') not in wire


def test_existing_structured_content_parts_also_round_trip():
    payload = {'model': 'qwen3.8-27b', 'messages': [{'role': 'user', 'content': [
        {'type': 'text', 'text': '中文\n'}, {'type': 'text', 'text': '<tag>\\"'}]}]}
    assert json.loads(encode_qwen_chat_body(payload)) == payload


@pytest.mark.asyncio
async def test_sdk_uses_safe_json_bytes_with_correct_length_and_unchanged_authorization():
    captured = []
    async def handler(request):
        captured.append(request)
        return httpx.Response(200, headers={'Content-Type': 'text/event-stream'}, content=(
            b'data: {"id":"one","object":"chat.completion.chunk","model":"qwen3.8-27b",'
            b'"choices":[{"index":0,"delta":{"content":"OK"},"finish_reason":"stop"}]}\n\n'
            b'data: [DONE]\n\n'))
    client = AsyncOpenAI(api_key='test-key', base_url='http://provider.test/v1',
        http_client=QwenCompatibleAsyncHttpxClient(transport=httpx.MockTransport(handler)))
    messages = [{'role': 'user', 'content': 'Directory.CreateDirectory(Path.GetDirectoryName(savePath));中文🧪'}]
    try:
        stream = await client.chat.completions.create(model='qwen3.8-27b', messages=messages, max_tokens=32000, stream=True)
        assert ''.join([chunk.choices[0].delta.content or '' async for chunk in stream]) == 'OK'
        request = captured[0]
        assert json.loads(request.content)['messages'] == messages
        assert b'Directory.CreateDirectory' not in request.content
        assert int(request.headers['content-length']) == len(request.content)
        assert request.headers['authorization'] == 'Bearer test-key'
        assert request.headers['content-type'] == 'application/json'
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_other_models_and_explicit_raw_bodies_are_not_rewritten():
    async with QwenCompatibleAsyncHttpxClient() as client:
        request = client.build_request('POST', 'http://provider.test/v1/chat/completions',
            json={'model': 'other-model', 'messages': [{'role': 'user', 'content': 'literal.text()'}]})
        assert b'literal.text()' in request.content
        raw = b'raw request body'
        request = client.build_request('POST', 'http://provider.test/v1/chat/completions',
            content=raw, json={'model': 'qwen3.8-27b', 'messages': []})
        assert request.content == raw
