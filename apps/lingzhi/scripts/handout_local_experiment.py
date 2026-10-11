"""Run the existing handout service against an explicitly selected local Qwen.

Generated inputs, partial output and results stay outside the Git repository.
This entry point neither starts a server nor changes the application's .env.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
import time
from urllib.parse import urlparse


def sample_input() -> dict:
    return {
        "course_title": "微积分入门",
        "lesson": {"title": "从平均变化率到导数", "key_points": ["导数的极限定义", "切线的几何意义"]},
        "course_context": {"target_audience": "学过函数和基础极限的大学一年级学生"},
        "requirements": "中文教材式讲义，约 1800 字。突出定义、结论和易错点。完整推导平方函数的导数，给出切线例题，并提供一题自测及独立解答。",
        "sections": [{"node_id": "local-derivative", "node_name": "导数与切线"}],
        "plan_sections": {"local-derivative": {
            "knowledge_names": ["平均变化率", "割线斜率", "差商极限", "导数定义", "切线斜率", "切线方程"],
            "knowledge_structure": [{"concept_group": "变化率到切线", "knowledge_points": [
                {"name": "平均变化率", "statement": "非零增量下，函数增量与自变量增量的比值。"},
                {"name": "割线斜率", "statement": "连接曲线上两点的直线斜率。", "aliases": ["割线"]},
                {"name": "差商极限", "statement": "自变量增量趋于零时差商的有限极限。", "aliases": ["平均变化率的极限"]},
                {"name": "导数定义", "statement": "函数在一点的导数由差商的有限极限定义。", "aliases": ["导数", "瞬时变化率"]},
                {"name": "切线斜率", "statement": "函数在该点可导时，切线斜率等于导数值。"},
                {"name": "切线方程", "statement": "利用切点和导数值写出切线的点斜式方程。"},
            ]}],
            # Synthetic, explicitly supplied lesson-plan relationships for the
            # local experiment; these do not modify any saved course graph.
            "knowledge_relations": [
                {"source_name": "平均变化率", "target_name": "割线斜率", "relation_type": "equivalent_to", "reason": "同一差商的数量解释与几何解释。", "conditions": ["两点横坐标不同，即 h≠0"]},
                {"source_name": "割线斜率", "target_name": "差商极限", "relation_type": "prerequisite", "reason": "让第二个点逼近第一个点，考察割线斜率的极限。", "conditions": ["趋近过程不直接代入 h=0"]},
                {"source_name": "差商极限", "target_name": "导数定义", "relation_type": "derives", "reason": "有限差商极限确定函数在该点的导数值。", "conditions": ["差商有有限极限"], "derivation_steps": ["构造非零增量下的差商", "令增量趋于零", "把所得有限极限记作该点导数"]},
                {"source_name": "导数定义", "target_name": "切线斜率", "relation_type": "equivalent_to", "reason": "在可导点，导数值是切线斜率的数值表达。", "conditions": ["函数在切点可导"]},
                {"source_name": "切线斜率", "target_name": "切线方程", "relation_type": "applies_to", "reason": "把斜率与切点坐标代入点斜式，再核验过点和斜率。", "conditions": ["切点坐标和导数值已知"]},
                {"source_name": "平均变化率", "target_name": "导数定义", "relation_type": "contrasts_with", "reason": "区间平均变化与一点瞬时变化容易混淆。", "distinction": "平均变化率对应非零区间；导数来自增量趋于零的极限，不能把差商直接代入零。"},
            ],
            "source_materials": [{"filename": "实验材料.txt", "locator": "第 1—3 段",
                "source_text": "平均变化率是 [f(a+h)-f(a)]/h，h≠0。若 h→0 时差商有有限极限，该极限称为 f 在 a 处的导数。对 f(x)=x²，差商为 2a+h，因此 f'(a)=2a。在 a=2 处，点为 (2,4)，斜率为 4，切线为 y-4=4(x-2)。"}],
        }},
    }


def project_sections(parsed: dict, outlines: list[dict]) -> list[dict]:
    from teacher_script import parse_handout_blocks
    return [{"section_node_id": section["node_id"], "title": section.get("node_name", ""),
             **parse_handout_blocks(parsed["completed"][section["node_id"]], section["node_id"], identity="local-experiment", complete=True)}
            for section in outlines if section["node_id"] in parsed["completed"]]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="Loopback OpenAI-compatible /v1 endpoint")
    parser.add_argument("--output", type=Path, required=True, help="New experiment directory outside the repository")
    parser.add_argument("--input", type=Path, help="Frozen JSON input; defaults to a synthetic calculus lesson")
    args = parser.parse_args()
    endpoint = urlparse(args.base_url)
    if endpoint.hostname not in {"localhost", "127.0.0.1", "::1"} or endpoint.scheme not in {"http", "https"} or endpoint.path.rstrip("/") != "/v1" or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment:
        parser.error("Use a loopback /v1 endpoint without embedded credentials")
    app_root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    if output.is_relative_to(app_root.parents[1]):
        parser.error("Generated output must be outside the repository")
    if output.exists() and any(output.iterdir()):
        parser.error("Choose an empty output directory to preserve previous experiments")
    payload = json.loads(args.input.read_text(encoding="utf-8-sig")) if args.input else sample_input()
    sections = payload.get("sections") or []
    if not sections or any(not s.get("node_id") for s in sections):
        parser.error("Input must contain sections with original node_id values")
    output.mkdir(parents=True, exist_ok=True)
    (output / "input.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    # Settings live only in this subprocess. The production provider policy stays
    # intact, including the exact model identity and the absence of fallbacks.
    key = os.environ.get("LINGZHI_LOCAL_API_KEY") or "local-experiment"
    for name in ("ZJU_QWEN_API_KEY", "AI_API_KEY", "AI_PPT_API_KEY"):
        os.environ[name] = key
    for name in ("ZJU_QWEN_BASE_URL", "AI_API_BASE", "AI_PPT_API_BASE"):
        os.environ[name] = args.base_url.rstrip("/")
    for name in ("AI_MODEL", "AI_MODEL_FAST", "AI_MODEL_CANDIDATES", "AI_MODEL_FAST_CANDIDATES", "AI_ASSESSMENT_GENERATOR_MODELS", "AI_ASSESSMENT_SOLVER_MODELS", "AI_ASSESSMENT_REVIEWER_MODELS", "AI_PPT_STORY_MODELS", "AI_PPT_VISUAL_MODELS"):
        os.environ[name] = "qwen3.8-27b"
    for name in ("MODELSCOPE_API_KEY", "MODELSCOPE_BASE_URL", "MODELSCOPE_MODEL", "MODELSCOPE_MODEL_CANDIDATES", "MODELSCOPE_MODEL_FAST_CANDIDATES", "LINGZHI_TEST_ALLOW_EXTERNAL_TEXT_PROVIDERS"):
        os.environ[name] = ""
    os.environ["AI_LOCAL_PROVIDER"] = "http"
    os.environ["LINGZHI_TASK_RUNTIME_MODE"] = "isolated_test"
    logging.disable(logging.CRITICAL)
    sys.path.insert(0, str(app_root / "backend"))

    async def run() -> int:
        import httpx
        from course_generation.service import CourseService
        from course_generation.prompts import PROMPT_CONTRACT_VERSION
        from teacher_script import parse_handout_stream

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(args.base_url.rstrip("/") + "/models", headers={"Authorization": f"Bearer {key}"})
            response.raise_for_status()
            if "qwen3.8-27b" not in {m.get("id") for m in response.json().get("data", [])}:
                raise ValueError("Start the local server with model alias qwen3.8-27b")
        service = CourseService()
        service._course_generation_artifacts["local-experiment"] = {"course_name": payload.get("course_title", "")}
        request_count, prompt_hash = 0, ""
        original_call = service._call_llm

        async def recorded_call(prompt, instructions, **kwargs):
            nonlocal request_count, prompt_hash
            request_count += 1
            frozen_prompt = instructions + "\n\n" + prompt
            prompt_hash = hashlib.sha256(frozen_prompt.encode("utf-8")).hexdigest()
            (output / "prompt.txt").write_text(frozen_prompt, encoding="utf-8")
            return await original_call(prompt, instructions, **kwargs)

        service._call_llm = recorded_call
        chunks: list[str] = []
        start, last_write, first_delta = time.monotonic(), 0.0, None

        def delta(text: str) -> None:
            nonlocal last_write, first_delta
            if text:
                chunks.append(text)
                first_delta = first_delta if first_delta is not None else time.monotonic() - start
                if time.monotonic() - last_write > 1:
                    (output / "partial.md").write_text("".join(chunks), encoding="utf-8")
                    last_write = time.monotonic()

        def reset() -> None:
            chunks.clear()
            (output / "partial.md").write_text("", encoding="utf-8")

        try:
            generated = await service.generate_teacher_handout(
                course_id="local-experiment", outline_sections=sections,
                plan_sections=payload.get("plan_sections") or {}, lesson_context=payload.get("lesson") or {},
                course_context=payload.get("course_context") or {}, requirements=payload.get("requirements", ""),
                on_content_delta=delta, on_content_reset=reset,
            )
        except Exception as exc:
            (output / "partial.md").write_text("".join(chunks), encoding="utf-8")
            (output / "report.json").write_text(json.dumps({"status": "failed", "error_type": type(exc).__name__, "characters_received": sum(map(len, chunks)), "seconds": round(time.monotonic() - start, 2)}, indent=2), encoding="utf-8")
            print(f"Generation stopped: {type(exc).__name__}; partial output preserved. No retry.")
            return 1
        (output / "partial.md").write_text(generated["text"], encoding="utf-8")
        parsed = parse_handout_stream(generated["text"], generated["section_ids"], provider_complete=True)
        parsed["sections"] = project_sections(parsed, sections)
        parsed["course_title"] = payload.get("course_title", "")
        parsed["lesson_title"] = (payload.get("lesson") or {}).get("title", "")
        # The graph consumes this same frozen plan, never a second model call.
        parsed["plan_sections"] = payload.get("plan_sections") or {}
        parsed["error"] = parsed["error"] or next((s["error"] for s in parsed["sections"] if s["error"]), "")
        (output / "handout.md").write_text(generated["text"], encoding="utf-8")
        (output / "handout.json").write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
        report = {"status": "passed" if not parsed["error"] else "structure_failed", "model": "qwen3.8-27b",
                  "prompt_version": PROMPT_CONTRACT_VERSION, "prompt_sha256": prompt_hash, "model_requests": request_count,
                  "seconds": round(time.monotonic() - start, 2), "first_delta_seconds": first_delta,
                  "characters": len(generated["text"]), "structure_error": parsed["error"]}
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False))
        return 0 if not parsed["error"] else 1

    with tempfile.TemporaryDirectory(prefix="lingzhi-local-handout-") as data_dir:
        os.environ["LINGZHI_DATA_DIR"] = data_dir
        return asyncio.run(run())


if __name__ == "__main__":
    raise SystemExit(main())
