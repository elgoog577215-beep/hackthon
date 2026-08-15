#!/usr/bin/env python3
"""AI 老师问答链路真机冒烟。

为什么单独写：课程生成审计脚本不覆盖问答链路，而问答走的是**流式**
路径（`ai_qa_service.answer_question_stream` -> `AIBase._stream_llm`），
与课程生成的非流式路径是两套代码。流式截断此前没有重试兜底，一次截断
就以空回答收场，必须真机验证。

数据红线：全部使用构造的上下文包，不读取任何真实课程与学生作答。

端点从环境变量读取，不硬编码。

用法：
    scripts/ai_teacher_qa_smoke.py --dry-run
    scripts/ai_teacher_qa_smoke.py --out /tmp/qa_smoke.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


# 构造上下文：刻意不引用任何真实课程 ID 或学习者数据。
def _constructed_package(with_web_source: bool) -> dict[str, Any]:
    package: dict[str, Any] = {
        "request": {"locale": "zh-CN"},
        "scene": {"scene_id": "smoke-scene", "title": "构造场景：条件概率"},
        "runtime": {"mode": "learning"},
        "conversation": {
            "recent_messages": [
                {"role": "user", "content": "我在看条件概率这一节。"},
                {"role": "assistant", "content": "好的，你想先弄清哪一部分？"},
            ]
        },
        "knowledge_context": {
            "focus": "条件概率的定义与乘法公式",
            "points": [
                "条件概率要求条件事件概率非零",
                "乘法公式由条件概率定义直接改写得到",
            ],
        },
    }
    if with_web_source:
        package["sources"] = [
            {
                "type": "web",
                "id": "S1",
                "title": "构造来源：条件概率讲义",
                "summary": "条件概率定义为 P(A|B)=P(AB)/P(B)，要求 P(B)>0。",
            }
        ]
    return package


CASES = [
    ("short_answer", "什么是条件概率？一句话说清。", False),
    ("long_structured", (
        "请系统讲解条件概率：定义、成立条件、与乘法公式的关系、"
        "一个具体例子、两个常见误区，以及一个可自测的小任务。"
        "分小节展开，尽量详细。"
    ), False),
    ("with_web_citation", "根据给出的资料说明条件概率的定义。", True),
]


async def run_case(service: Any, name: str, question: str, web: bool) -> dict:
    started = time.perf_counter()
    chunks: list[str] = []
    error = ""
    try:
        async for chunk in service.answer_question_stream(
            question,
            context_package=_constructed_package(web),
        ):
            chunks.append(chunk)
    except Exception as exc:  # noqa: BLE001 - 冒烟需要如实记录任何失败
        error = f"{type(exc).__name__}: {str(exc)[:200]}"
    text = "".join(chunks)
    return {
        "case": name,
        "ok": bool(text) and not error,
        "error": error,
        "latency_s": round(time.perf_counter() - started, 2),
        "chunk_count": len(chunks),
        "answer_chars": len(text),
        "answer_head": text[:120],
        "cited_marker": "[S1]" in text if web else None,
    }


async def main_async(args: argparse.Namespace) -> int:
    # 与运行时同源：ai_base 也是从仓库根的 .env 读部署配置。
    # 必须先加载再检查，否则只看 shell 环境会误报"端点未配置"。
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    base = os.getenv("AI_API_BASE", "").strip()
    model = os.getenv("AI_MODEL", "").strip()
    if not base or not model:
        print("需要 AI_API_BASE 与 AI_MODEL（端点不硬编码）", file=sys.stderr)
        return 2
    from ai_qa_service import AIQAService

    service = AIQAService()
    results = []
    for name, question, web in CASES:
        result = await run_case(service, name, question, web)
        results.append(result)
        print(json.dumps({"case_result": result}, ensure_ascii=False), flush=True)

    report = {
        "schema_version": "ai_teacher_qa_smoke_v1",
        "endpoint_model": model,
        "cases": results,
        "all_ok": all(item["ok"] for item in results),
        "note": "全部为构造上下文，未使用真实课程与学生作答。",
    }
    if args.out:
        Path(args.out).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(json.dumps({"qa_smoke_report": report}, ensure_ascii=False, indent=2))
    return 0 if report["all_ok"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="AI 老师问答链路真机冒烟")
    parser.add_argument("--out", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.dry_run:
        print("AI 老师问答冒烟计划（dry-run，不发起任何请求）")
        for name, question, web in CASES:
            print(f"  - {name}: {question[:40]}...（web 来源={web}）")
        print("  端点：从 AI_API_BASE / AI_MODEL 读取，不硬编码")
        print("  数据：全部构造，不读真实课程与学生作答")
        return 0
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
