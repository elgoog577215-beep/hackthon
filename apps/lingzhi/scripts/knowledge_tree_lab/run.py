"""Run exactly one bounded Qwen stage against an isolated experiment directory.

Usage (from the app): python -m scripts.knowledge_tree_lab.run ROOT core
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
import time
from .pipeline import read, save, digest
from . import prompts

APP = Path(__file__).resolve().parents[2]
LIMITS = {"core": 12000, "atomize": 12000, "teach": 21000, "repair": 16000}


def prompt_for(root, stage, topic, fixtures, evaluation):
    folder = root / topic["id"]
    context = {"course": fixtures["course_context"], "topic": topic,
               "coverage": evaluation["coverage_criteria"][topic["id"]]}
    if stage == "core":
        return prompts.CORE + "\n输入：" + json.dumps(context, ensure_ascii=False)
    if stage == "atomize":
        doc = read(folder / "core.json")
        context.update(base_hash=digest(doc), current=doc)
        return prompts.ATOMIZE + "\n输入：" + json.dumps(context, ensure_ascii=False)
    context["core"] = read(folder / "atomic.json")
    context["compiler_environment"] = read(root / "compiler-environment.json")
    if stage == "teach":
        return prompts.TEACH + "\n输入：" + json.dumps(context, ensure_ascii=False)
    payload = read(folder / "teach.parsed.json")
    context.update(base_hash=digest(payload), teaching=payload,
                   feedback=read(folder / "local-feedback.json"),
                   allowed=read(folder / "repair-scope.json"))
    return prompts.REPAIR + "\n输入：" + json.dumps(context, ensure_ascii=False)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("stage", choices=LIMITS)
    parser.add_argument("--topic", default="all", choices=("all", "types", "if", "for"))
    args = parser.parse_args()
    root = args.root.resolve()
    if root.is_relative_to(APP / "backend" / "data"):
        raise ValueError("experiment_must_be_isolated")
    os.environ["LINGZHI_DATA_DIR"] = str(root / "isolated-data")
    os.environ["LINGZHI_GENERATION_TELEMETRY"] = "false"
    logging.disable(logging.CRITICAL)
    sys.path.insert(0, str(APP / "backend"))
    from ai_base import AIBase
    provider = AIBase()
    fixtures = read(root / "fixtures.json")
    evaluation = read(root / "eval_definition.json")
    frozen = ("fixtures.json", "eval_definition.json", "holdout_probes.json", "protocol.json")
    manifest_path = root / "manifest.json"
    hashes = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in frozen}
    if manifest_path.exists():
        assert read(manifest_path)["inputs_sha256"] == hashes, "frozen_inputs_changed"
    else:
        save(manifest_path, {"model": provider.model_smart, "thinking": False,
             "inputs_sha256": hashes, "max_calls": 12, "attempts_per_call": 1,
             "prompts_sha256": hashlib.sha256(Path(prompts.__file__).read_bytes()).hexdigest()})
    assert read(manifest_path)["prompts_sha256"] == hashlib.sha256(Path(prompts.__file__).read_bytes()).hexdigest(), "prompts_changed"
    try:
        for topic in fixtures["topics"]:
            if args.topic not in ("all", topic["id"]):
                continue
            folder = root / topic["id"]
            folder.mkdir(exist_ok=True)
            result_path = folder / (args.stage + ".result.json")
            if result_path.exists() or len(list(root.glob("*/*.result.json"))) >= 12:
                raise ValueError("duplicate_stage_or_budget_exhausted")
            prompt = prompt_for(root, args.stage, topic, fixtures, evaluation)
            (folder / (args.stage + ".prompt.txt")).write_text(prompt, encoding="utf-8")
            save(result_path, {"state": "started", "stage": args.stage, "topic": topic["id"]})
            print(json.dumps({"event": "started", "stage": args.stage, "topic": topic["id"]}), flush=True)
            start = time.monotonic()
            telemetry, parts = [], []
            task = asyncio.create_task(provider._call_llm(prompt, system_prompt=prompts.SYSTEM,
                retry_count=1, max_attempts=1, enable_thinking=False, max_tokens=LIMITS[args.stage],
                request_timeout_seconds=300, reject_truncated=True, require_stop=True,
                raise_on_failure=True, json_mode=False, on_content_delta=parts.append,
                telemetry_sink=telemetry.append))
            try:
                while not task.done():
                    await asyncio.wait({task}, timeout=25)
                    (folder / (args.stage + ".partial.txt")).write_text("".join(parts), encoding="utf-8")
                    print(json.dumps({"event": "progress", "topic": topic["id"], "stage": args.stage,
                        "seconds": round(time.monotonic() - start, 1), "chars": sum(map(len, parts))}), flush=True)
                response = await task
                (folder / (args.stage + ".raw.txt")).write_text(response or "", encoding="utf-8")
                try:
                    obj = json.loads(response)
                    parse = "strict_json"
                except json.JSONDecodeError:
                    obj = provider._extract_json(response)
                    parse = "extracted_json"
                if not isinstance(obj, dict):
                    raise ValueError("invalid_json")
                save(folder / (args.stage + ".parsed.json"), obj)
                save(result_path, {"state": "completed", "stage": args.stage, "topic": topic["id"],
                     "elapsed_seconds": round(time.monotonic() - start, 2), "parse": parse, "telemetry": telemetry})
                print(json.dumps({"event": "completed", "topic": topic["id"], "stage": args.stage}), flush=True)
            except Exception as exc:
                save(result_path, {"state": "failed", "stage": args.stage, "topic": topic["id"],
                     "error_type": type(exc).__name__, "elapsed_seconds": round(time.monotonic() - start, 2), "telemetry": telemetry})
                print(json.dumps({"event": "failed", "error_type": type(exc).__name__}), flush=True)
                break
    finally:
        if provider.client:
            await provider.client.close()


if __name__ == "__main__":
    asyncio.run(main())
