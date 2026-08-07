#!/usr/bin/env python3
"""Probe a self-hosted, OpenAI-compatible Qwen endpoint before pointing 灵知 at it.

Why this exists: the production deployment moves model calls from a hosted API to
启智's own Qwen service (vLLM-class, OpenAI-compatible, no real concurrency). Three
things differ from the hosted providers and each has already bitten us or is
likely to:

1. ``max_tokens`` truncation. ``backend/ai_base.py:157-164`` records the original
   bug: no ``max_tokens`` was passed, calls fell back to the provider default
   (~4096), and long structured JSON got cut mid-string — surfacing as a
   content-quality bug rather than a truncation bug. A self-hosted endpoint has
   its own ceiling, so we measure it rather than assume it.
2. ``enable_thinking``. ``ai_base._thinking_extra_body`` sends a **flat**
   ``{"enable_thinking": bool}``. vLLM normally expects it nested under
   ``chat_template_kwargs``. If the endpoint rejects unknown top-level fields,
   every call fails; if it silently ignores them, thinking never actually turns
   on. Both forms are probed here so the deployment knows which to configure.
3. Auth. A self-hosted endpoint usually needs no key, but ``ai_base`` disables
   the client entirely when ``AI_API_KEY`` is empty (see ``ai_base.py:187-198``),
   so a placeholder is mandatory. This script verifies the endpoint tolerates one.

No network access is required to review the script: ``--dry-run`` prints the plan
and exits 0.

Usage:
    scripts/qwen_endpoint_smoke.py --base-url http://10.0.0.5:8000/v1 \
        --model Qwen/Qwen3-32B --api-key EMPTY
    scripts/qwen_endpoint_smoke.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
for module_root in (ROOT, BACKEND):
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))

# The long-JSON probe asks for enough nested structure to exceed a ~4096-token
# default ceiling, which is what the original truncation bug ran into.
LONG_JSON_INSTRUCTION = (
    "输出一个 JSON 对象，键为 chapters，值为 12 个章节对象的数组。"
    "每个章节对象包含：title（字符串）、summary（不少于 60 字的字符串）、"
    "capability_points（5 条字符串）、mistake_points（5 条字符串）。"
    "只输出 JSON，不要解释，不要代码围栏。"
)

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"
SKIP = "SKIP"


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def blocking(self) -> bool:
        return self.status == FAIL


@dataclass
class SmokeConfig:
    base_url: str
    model: str
    api_key: str
    max_tokens: int
    timeout: float
    verbose: bool


def _fmt(value: Any, limit: int = 160) -> str:
    text = str(value).replace("\n", " ")
    return text if len(text) <= limit else f"{text[:limit]}…"


async def check_models(client: Any, config: SmokeConfig) -> CheckResult:
    """GET /v1/models — the cheapest proof of reachability and auth posture."""
    try:
        listing = await client.models.list()
    except Exception as exc:  # noqa: BLE001 - report any transport/auth failure
        return CheckResult(
            "GET /v1/models",
            FAIL,
            f"{type(exc).__name__}: {_fmt(exc)}",
        )

    ids = [getattr(item, "id", "") for item in getattr(listing, "data", [])]
    if not ids:
        return CheckResult(
            "GET /v1/models", WARN, "端点可达但未返回任何模型 ID"
        )
    if config.model not in ids:
        return CheckResult(
            "GET /v1/models",
            FAIL,
            f"端点未提供 --model {config.model}；可用：{', '.join(ids[:5])}",
            {"available": ids},
        )
    return CheckResult(
        "GET /v1/models",
        PASS,
        f"端点可达，{config.model} 在列（共 {len(ids)} 个模型）",
        {"available": ids},
    )


async def check_short_completion(client: Any, config: SmokeConfig) -> CheckResult:
    """One tiny call: proves chat/completions works end to end."""
    started = time.monotonic()
    try:
        response = await client.chat.completions.create(
            model=config.model,
            messages=[{"role": "user", "content": "只回复两个字：就绪"}],
            max_tokens=32,
            temperature=0,
        )
    except Exception as exc:  # noqa: BLE001
        return CheckResult(
            "短补全", FAIL, f"{type(exc).__name__}: {_fmt(exc)}"
        )

    elapsed = time.monotonic() - started
    choice = response.choices[0] if response.choices else None
    content = (getattr(choice.message, "content", "") or "") if choice else ""
    if not content.strip():
        return CheckResult(
            "短补全",
            FAIL,
            "返回了空内容；ai_base 会把这种情况当作 empty_response 失败",
        )
    return CheckResult(
        "短补全",
        PASS,
        f"{elapsed:.1f}s 内返回：{_fmt(content, 40)}",
        {"latency_seconds": round(elapsed, 2)},
    )


async def check_long_json(client: Any, config: SmokeConfig) -> CheckResult:
    """The truncation probe recorded in ai_base.py:157-164.

    A cut-off response is reported by ``finish_reason == "length"`` — the exact
    signal ``ai_base`` uses to raise ``AIResponseTruncated``. We ask for more
    structure than a default ceiling allows, so this either proves the configured
    ``max_tokens`` is honoured or shows where the real ceiling sits.
    """
    started = time.monotonic()
    try:
        response = await client.chat.completions.create(
            model=config.model,
            messages=[{"role": "user", "content": LONG_JSON_INSTRUCTION}],
            max_tokens=config.max_tokens,
            temperature=0,
        )
    except Exception as exc:  # noqa: BLE001
        return CheckResult(
            "长 JSON / 截断", FAIL, f"{type(exc).__name__}: {_fmt(exc)}"
        )

    elapsed = time.monotonic() - started
    choice = response.choices[0] if response.choices else None
    content = (getattr(choice.message, "content", "") or "") if choice else ""
    finish_reason = getattr(choice, "finish_reason", None) if choice else None
    usage = getattr(response, "usage", None)
    completion_tokens = getattr(usage, "completion_tokens", None)
    data = {
        "finish_reason": finish_reason,
        "chars": len(content),
        "completion_tokens": completion_tokens,
        "requested_max_tokens": config.max_tokens,
        "latency_seconds": round(elapsed, 2),
    }

    if finish_reason == "length":
        return CheckResult(
            "长 JSON / 截断",
            FAIL,
            (
                f"输出被 max_tokens={config.max_tokens} 截断"
                f"（completion_tokens={completion_tokens}, chars={len(content)}）。"
                "这正是 ai_base.py:157-164 记录的坑：截断的 JSON 会在下游解析失败，"
                "看起来像内容质量问题。请提高端点的输出上限或调低 AI_MAX_TOKENS 对应的分段规模。"
            ),
            data,
        )

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        return CheckResult(
            "长 JSON / 截断",
            FAIL,
            (
                f"finish_reason={finish_reason} 未报截断，但 JSON 仍解析失败：{exc}。"
                "可能是模型加了代码围栏或前言，需要在 prompt 层继续约束。"
            ),
            data,
        )

    chapters = parsed.get("chapters") if isinstance(parsed, dict) else None
    count = len(chapters) if isinstance(chapters, list) else 0
    data["chapters"] = count
    if count < 12:
        return CheckResult(
            "长 JSON / 截断",
            WARN,
            (
                f"JSON 完整可解析，但只给了 {count}/12 个章节"
                f"（completion_tokens={completion_tokens}）。结构未被截断，"
                "但模型倾向缩短长结构，出题与教案批次需要留额外余量。"
            ),
            data,
        )
    return CheckResult(
        "长 JSON / 截断",
        PASS,
        (
            f"{elapsed:.1f}s 内返回完整 JSON，{count} 章、chars={len(content)}、"
            f"completion_tokens={completion_tokens}，未触发截断"
        ),
        data,
    )


async def _try_thinking_form(
    client: Any, config: SmokeConfig, extra_body: dict[str, Any]
) -> tuple[bool, str, str]:
    """Send one request with the given extra_body. Returns (ok, detail, content)."""
    try:
        response = await client.chat.completions.create(
            model=config.model,
            messages=[{"role": "user", "content": "1+1 等于几？只回答数字。"}],
            max_tokens=256,
            temperature=0,
            extra_body=extra_body,
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {_fmt(exc, 120)}", ""
    choice = response.choices[0] if response.choices else None
    message = getattr(choice, "message", None) if choice else None
    content = (getattr(message, "content", "") or "") if message else ""
    # Some builds expose thinking separately rather than inline.
    reasoning = getattr(message, "reasoning_content", None) if message else None
    detail = "已接受"
    if reasoning:
        detail += "，且返回了 reasoning_content"
    return True, detail, content


async def check_enable_thinking(client: Any, config: SmokeConfig) -> CheckResult:
    """Probe both spellings of enable_thinking.

    ``ai_base._thinking_extra_body`` sends the flat form. vLLM usually wants it
    under ``chat_template_kwargs``. Whichever the endpoint accepts determines
    whether ``ai_base`` needs an adapter for this deployment.
    """
    flat_ok, flat_detail, _ = await _try_thinking_form(
        client, config, {"enable_thinking": True}
    )
    nested_ok, nested_detail, _ = await _try_thinking_form(
        client, config, {"chat_template_kwargs": {"enable_thinking": True}}
    )
    data = {"flat_accepted": flat_ok, "nested_accepted": nested_ok}

    if flat_ok:
        # This is what ai_base already sends, so nothing has to change.
        suffix = "" if nested_ok else "（嵌套写法被拒，但无需使用）"
        return CheckResult(
            "enable_thinking extra_body",
            PASS,
            f"端点接受 ai_base 现用的扁平写法 {{'enable_thinking': true}}{suffix}",
            data,
        )
    if nested_ok:
        return CheckResult(
            "enable_thinking extra_body",
            FAIL,
            (
                "端点拒绝 ai_base 现用的扁平写法，只接受 vLLM 的嵌套写法 "
                "chat_template_kwargs.enable_thinking。"
                f"扁平写法报错：{flat_detail}。"
                "上线前必须让 ai_base._thinking_extra_body 按端点类型输出嵌套形式，"
                "否则每次调用都会失败。"
            ),
            data,
        )
    return CheckResult(
        "enable_thinking extra_body",
        WARN,
        (
            "两种写法都被拒绝，说明该端点不支持 thinking 开关。"
            f"扁平：{flat_detail}；嵌套：{nested_detail}。"
            "部署时应设置 AI_THINKING_ENABLED=false 以免每次调用都带上无效字段。"
        ),
        data,
    )


CHECKS = (
    ("GET /v1/models", check_models),
    ("短补全", check_short_completion),
    ("长 JSON / 截断", check_long_json),
    ("enable_thinking extra_body", check_enable_thinking),
)


def print_plan(config: SmokeConfig) -> None:
    print("千问自部署端点 smoke —— 计划（dry-run，不发起任何请求）")
    print(f"  base_url : {config.base_url}")
    print(f"  model    : {config.model}")
    print(f"  api_key  : {'<已提供>' if config.api_key else '<空>'}")
    print(f"  max_tokens: {config.max_tokens}")
    print("  将执行的检查：")
    for index, (name, _) in enumerate(CHECKS, start=1):
        print(f"    {index}. {name}")
    print()
    print("说明：api_key 不能为空字符串。ai_base.py:187-198 在 AI_API_KEY 为空时")
    print("     直接把 client 置为 None 并禁用全部 AI 能力，因此无鉴权端点也必须")
    print("     配一个占位符（例如 EMPTY）。")


def print_report(results: list[CheckResult], config: SmokeConfig) -> None:
    print()
    print("=" * 72)
    print(f"千问自部署端点 smoke 报告  base_url={config.base_url}  model={config.model}")
    print("=" * 72)
    for result in results:
        print(f"[{result.status:4}] {result.name}")
        print(f"       {result.detail}")
        if config.verbose and result.data:
            print(f"       data: {json.dumps(result.data, ensure_ascii=False)}")
    print("-" * 72)
    failed = [r for r in results if r.status == FAIL]
    warned = [r for r in results if r.status == WARN]
    if failed:
        print(f"结论：不可上线。{len(failed)} 项阻断，{len(warned)} 项警告。")
        for result in failed:
            print(f"  阻断 · {result.name}")
    elif warned:
        print(f"结论：可用，但有 {len(warned)} 项需要在部署配置里处理。")
        for result in warned:
            print(f"  警告 · {result.name}")
    else:
        print("结论：全部通过，可以按 .env.example 的自部署段配置接入。")
    print("=" * 72)


async def run_checks(config: SmokeConfig) -> int:
    try:
        from openai import AsyncOpenAI
    except ImportError:
        print("缺少 openai 包，请在 backend 虚拟环境中运行本脚本。", file=sys.stderr)
        return 2

    import httpx

    client = AsyncOpenAI(
        base_url=config.base_url,
        api_key=config.api_key,
        timeout=httpx.Timeout(config.timeout, connect=10.0),
        max_retries=0,
    )

    results: list[CheckResult] = []
    try:
        for name, check in CHECKS:
            # Reachability gates the rest: without it every later check would
            # just repeat the same connection error.
            if results and results[0].blocking:
                results.append(
                    CheckResult(name, SKIP, "端点不可达，跳过")
                )
                continue
            results.append(await check(client, config))
    finally:
        await client.close()

    print_report(results, config)
    return 1 if any(r.blocking for r in results) else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="验证自部署千问端点是否满足灵知的调用要求",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("QWEN_BASE_URL", os.getenv("AI_API_BASE", "")),
        help="OpenAI 兼容端点，例如 http://10.0.0.5:8000/v1（默认读 QWEN_BASE_URL / AI_API_BASE）",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("QWEN_MODEL", os.getenv("AI_MODEL", "")),
        help="模型 ID，需与 /v1/models 返回一致（默认读 QWEN_MODEL / AI_MODEL）",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("QWEN_API_KEY", os.getenv("AI_API_KEY", "EMPTY")),
        help="占位符即可；不能为空字符串（默认读 QWEN_API_KEY / AI_API_KEY，回落 EMPTY）",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=int(os.getenv("AI_MAX_TOKENS", "8192")),
        help="长 JSON 检查使用的输出上限，默认与 AI_MAX_TOKENS 一致（8192）",
    )
    parser.add_argument(
        "--timeout", type=float, default=180.0, help="单次请求超时秒数，默认 180"
    )
    parser.add_argument("--verbose", action="store_true", help="报告中附带原始数据")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印将要执行的检查，不发起任何请求",
    )
    args = parser.parse_args()

    config = SmokeConfig(
        base_url=args.base_url.strip(),
        model=args.model.strip(),
        api_key=args.api_key,
        max_tokens=args.max_tokens,
        timeout=args.timeout,
        verbose=args.verbose,
    )

    if args.dry_run:
        print_plan(config)
        return 0

    missing = [
        flag
        for flag, value in (("--base-url", config.base_url), ("--model", config.model))
        if not value
    ]
    if missing:
        print(f"缺少必需参数：{', '.join(missing)}（或设置对应环境变量）", file=sys.stderr)
        print("先用 --dry-run 查看将执行的检查。", file=sys.stderr)
        return 2
    if not config.api_key:
        print(
            "--api-key 不能为空：ai_base 在 AI_API_KEY 为空时会禁用全部 AI 能力，"
            "无鉴权端点请填占位符（例如 EMPTY）。",
            file=sys.stderr,
        )
        return 2

    return asyncio.run(run_checks(config))


if __name__ == "__main__":
    raise SystemExit(main())
