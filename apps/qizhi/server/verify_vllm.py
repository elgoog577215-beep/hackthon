"""
Verify a local vLLM server (multimodal, e.g. Qwen3.6-35B-A3B).

Tests the OpenAI-compatible API end-to-end:
  1. /v1/models       — server is up
  2. text chat        — basic generation
  3. streaming        — incremental output
  4. multimodal       — image input (the path you'll actually use)
  5. JSON mode        — response_format={"type": "json_object"}
  6. thinking toggle  — Qwen3's enable_thinking=False via chat_template_kwargs
"""

import base64
import io
import json
import time
from openai import OpenAI

BASE_URL = "http://127.0.0.1:30964/v1"
API_KEY = "EMPTY"

client = OpenAI(base_url=BASE_URL, api_key=API_KEY)

# Collected stats — populated by each test, printed at the end.
STATS = []

# Recommended sampling per Qwen3.6 README.
# top_k and min_p aren't standard OpenAI params, so they ride in extra_body.
NON_THINKING_SAMPLING = dict(
    temperature=0.7,
    top_p=0.80,
    presence_penalty=1.5,
    extra_body={
        "top_k": 20,
        "min_p": 0.0,
        "repetition_penalty": 1.0,
        "chat_template_kwargs": {"enable_thinking": False},
    },
)

THINKING_SAMPLING = dict(
    temperature=1.0,
    top_p=0.95,
    presence_penalty=1.5,
    extra_body={
        "top_k": 20,
        "min_p": 0.0,
        "repetition_penalty": 1.0,
        "chat_template_kwargs": {"enable_thinking": True},
    },
)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def make_test_image() -> str:
    """Generate a small test image. Returns data URL."""
    try:
        from PIL import Image, ImageDraw
    except ImportError as e:
        raise SystemExit(f"PIL import failed: {e!r}. Try: python -m pip install pillow")

    img = Image.new("RGB", (240, 120), color=(30, 30, 60))
    draw = ImageDraw.Draw(img)
    draw.ellipse((20, 30, 80, 90), fill=(220, 50, 50))
    draw.ellipse((90, 30, 150, 90), fill=(50, 200, 80))
    draw.ellipse((160, 30, 220, 90), fill=(60, 100, 230))
    draw.text((75, 95), "VLLM TEST", fill=(255, 255, 255))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"


def section(n, title):
    print(f"\n{'=' * 70}\n{n}. {title}\n{'=' * 70}")


def fmt_stats(prompt_tokens, completion_tokens, total_time, ttft=None):
    """Compute and pretty-print performance numbers."""
    out_tps = completion_tokens / total_time if total_time > 0 else 0
    lines = [
        f"  prompt tokens     : {prompt_tokens}",
        f"  completion tokens : {completion_tokens}",
        f"  total time        : {total_time*1000:.1f} ms",
        f"  output throughput : {out_tps:.2f} tok/s",
    ]
    if ttft is not None:
        # Decode-only throughput excludes prefill — closer to "steady-state" speed.
        decode_time = total_time - ttft
        decode_tps = (
            (completion_tokens - 1) / decode_time
            if decode_time > 0 and completion_tokens > 1
            else 0
        )
        prefill_tps = prompt_tokens / ttft if ttft > 0 else 0
        lines.insert(3, f"  TTFT              : {ttft*1000:.1f} ms")
        lines.append(f"  prefill speed     : {prefill_tps:.1f} tok/s (prompt / TTFT)")
        lines.append(f"  decode speed      : {decode_tps:.2f} tok/s (excludes prefill)")
    print("\n".join(lines))


def record(name, prompt_tokens, completion_tokens, total_time, ttft=None):
    STATS.append(
        {
            "name": name,
            "prompt": prompt_tokens,
            "completion": completion_tokens,
            "total_s": total_time,
            "ttft_s": ttft,
            "out_tps": completion_tokens / total_time if total_time > 0 else 0,
        }
    )


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------


def check_models():
    section(1, "GET /v1/models")
    t0 = time.perf_counter()
    models = client.models.list()
    dt = time.perf_counter() - t0
    for m in models.data:
        print(f"  - {m.id}")
    print(f"  [latency: {dt*1000:.1f} ms]")
    return models.data[0].id


def check_text_chat(model_id):
    section(2, "Text chat — short answer")
    t0 = time.perf_counter()
    resp = client.chat.completions.create(
        model=model_id,
        messages=[
            {"role": "system", "content": "You are a helpful assistant. Be concise."},
            {
                "role": "user",
                "content": "What is 17 * 23? Answer with just the number.",
            },
        ],
        max_tokens=128,
        **NON_THINKING_SAMPLING,
    )
    dt = time.perf_counter() - t0
    print(f"[content] {resp.choices[0].message.content}\n")
    fmt_stats(resp.usage.prompt_tokens, resp.usage.completion_tokens, dt)
    record("text_short", resp.usage.prompt_tokens, resp.usage.completion_tokens, dt)


def check_text_long(model_id):
    section(3, "Text chat — long answer (for decode throughput)")
    t0 = time.perf_counter()
    resp = client.chat.completions.create(
        model=model_id,
        messages=[
            {
                "role": "user",
                "content": "Write a 300-word essay about the history of the printing press.",
            },
        ],
        max_tokens=512,
        **NON_THINKING_SAMPLING,
    )
    dt = time.perf_counter() - t0
    print(f"[first 200 chars] {resp.choices[0].message.content[:200]}...\n")
    fmt_stats(resp.usage.prompt_tokens, resp.usage.completion_tokens, dt)
    record("text_long", resp.usage.prompt_tokens, resp.usage.completion_tokens, dt)


def check_streaming(model_id):
    section(4, "Streaming (measures TTFT and decode speed)")
    t0 = time.perf_counter()
    ttft = None
    completion_tokens = 0
    prompt_tokens = 0
    content_buf = ""

    stream = client.chat.completions.create(
        model=model_id,
        messages=[
            {"role": "user", "content": "List 10 interesting facts about octopuses."}
        ],
        max_tokens=512,
        stream=True,
        stream_options={"include_usage": True},
        **NON_THINKING_SAMPLING,
    )

    for chunk in stream:
        # Final usage chunk (no choices)
        if chunk.usage is not None:
            prompt_tokens = chunk.usage.prompt_tokens
            completion_tokens = chunk.usage.completion_tokens
            continue
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta.content:
            if ttft is None:
                ttft = time.perf_counter() - t0
            content_buf += delta.content

    dt = time.perf_counter() - t0
    print(f"[first 200 chars] {content_buf[:200]}...\n")
    fmt_stats(prompt_tokens, completion_tokens, dt, ttft=ttft)
    record("streaming", prompt_tokens, completion_tokens, dt, ttft=ttft)


def check_multimodal(model_id):
    section(5, "Multimodal — image + text")
    image_url = make_test_image()
    print("Image: 240x120 PNG, three colored circles + 'VLLM TEST' label\n")

    t0 = time.perf_counter()
    resp = client.chat.completions.create(
        model=model_id,
        messages=[
            {"role": "system", "content": "You are a helpful assistant. Be concise."},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text", "text": "What colors and text do you see?"},
                ],
            },
        ],
        max_tokens=256,
        **NON_THINKING_SAMPLING,
    )
    dt = time.perf_counter() - t0
    print(f"[content] {resp.choices[0].message.content}\n")
    fmt_stats(resp.usage.prompt_tokens, resp.usage.completion_tokens, dt)
    record("multimodal", resp.usage.prompt_tokens, resp.usage.completion_tokens, dt)


def check_json_mode(model_id):
    section(6, "JSON mode + image (DashScope port)")
    image_url = make_test_image()

    t0 = time.perf_counter()
    resp = client.chat.completions.create(
        model=model_id,
        messages=[
            {
                "role": "system",
                "content": "你是图像分析助手，只返回JSON，不要返回其他内容。",
            },
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {
                        "type": "text",
                        "text": 'Return JSON: {"circles": [{"color": "..."}], "text": "..."}',
                    },
                ],
            },
        ],
        max_tokens=256,
        response_format={"type": "json_object"},
        **NON_THINKING_SAMPLING,
    )
    dt = time.perf_counter() - t0
    raw = resp.choices[0].message.content
    print(f"[raw] {raw}")
    try:
        parsed = json.loads(raw)
        print(f"[parsed OK] keys = {list(parsed.keys())}\n")
    except json.JSONDecodeError as e:
        print(f"[parse FAILED] {e}\n")
    fmt_stats(resp.usage.prompt_tokens, resp.usage.completion_tokens, dt)
    record("json_mode", resp.usage.prompt_tokens, resp.usage.completion_tokens, dt)


def check_thinking_mode(model_id):
    section(7, "enable_thinking=True (reasoning trace)")
    t0 = time.perf_counter()
    resp = client.chat.completions.create(
        model=model_id,
        messages=[
            {
                "role": "user",
                "content": "If a train leaves at 3pm at 60mph and another at 4pm at 80mph from the same place going the same direction, when do they meet?",
            }
        ],
        max_tokens=32768,  # Qwen3.6 README recommends 32k for general thinking tasks
        **THINKING_SAMPLING,
    )
    dt = time.perf_counter() - t0
    choice = resp.choices[0]
    msg = choice.message
    reasoning = getattr(msg, "reasoning_content", None) or ""
    content = msg.content or ""

    print(f"[finish_reason] {choice.finish_reason}")
    print(
        f"[reasoning_content] ({len(reasoning)} chars) "
        f"{reasoning[:200]}{'...' if len(reasoning) > 200 else ''}"
    )
    print(
        f"[content] ({len(content)} chars) "
        f"{content[:300]}{'...' if len(content) > 300 else ''}\n"
    )

    if choice.finish_reason == "length":
        print("  ⚠️  Hit max_tokens — answer was truncated.\n")
    if not reasoning and not content:
        print(
            "  ⚠️  Both reasoning_content and content are empty. Check --reasoning-parser qwen3 was applied.\n"
        )

    fmt_stats(resp.usage.prompt_tokens, resp.usage.completion_tokens, dt)
    record("thinking", resp.usage.prompt_tokens, resp.usage.completion_tokens, dt)


def print_summary():
    section("∑", "Performance summary")
    header = f"{'test':<14} {'prompt':>7} {'output':>7} {'time(s)':>8} {'TTFT(ms)':>9} {'tok/s':>8}"
    print(header)
    print("-" * len(header))
    for s in STATS:
        ttft_str = f"{s['ttft_s']*1000:.0f}" if s["ttft_s"] is not None else "-"
        print(
            f"{s['name']:<14} {s['prompt']:>7} {s['completion']:>7} "
            f"{s['total_s']:>8.2f} {ttft_str:>9} {s['out_tps']:>8.2f}"
        )


# --------------------------------------------------------------------------
# Run
# --------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        model_id = check_models()
        check_text_chat(model_id)
        check_text_long(model_id)
        check_streaming(model_id)
        check_multimodal(model_id)
        check_json_mode(model_id)
        check_thinking_mode(model_id)
        print_summary()
        print("\n✅ All checks passed.")
    except Exception as e:
        print(f"\n❌ Failed: {type(e).__name__}: {e}")
        raise
