"""Measure the existing teacher generation service with isolated synthetic data."""
import argparse
import asyncio
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-root", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stage", choices=("handout", "outline"), default="handout")
    parser.add_argument("--case", default="statistics_basic")
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be positive")
    if args.stage == "outline" and args.mock:
        parser.error("Outline request-count mocks are covered by backend tests; omit --mock for model evaluation")
    if args.output.resolve().is_relative_to(args.app_root.resolve()):
        parser.error("Save generated benchmark output outside the repository")
    from dotenv import load_dotenv
    load_dotenv(args.env_file, override=True)
    for key in ("MODELSCOPE_API_KEY", "MODELSCOPE_BASE_URL", "MODELSCOPE_MODEL", "MODELSCOPE_MODEL_CANDIDATES", "MODELSCOPE_MODEL_FAST_CANDIDATES"):
        os.environ[key] = ""
    logging.disable(logging.CRITICAL)
    with tempfile.TemporaryDirectory(prefix="teacher-benchmark-") as isolated:
        os.environ["LINGZHI_DATA_DIR"] = isolated
        os.environ["LINGZHI_TASK_RUNTIME_MODE"] = "isolated_test"
        sys.path.insert(0, str(args.app_root / "backend"))
        from course_generation.service import CourseService

        async def measure(count):
            service = CourseService()
            requests = 0
            original = service._call_llm
            async def counted(*a, **kw):
                nonlocal requests
                requests += 1
                if args.mock:
                    await asyncio.sleep(0.05)
                    return "## 核心教学\n\n" + "重复讲解。" * 400
                return await original(*a, **kw)
            service._call_llm = counted
            async def lesson(index):
                start = time.monotonic()
                first = None
                deltas = 0
                def delta(text):
                    nonlocal first, deltas
                    if text:
                        deltas += 1
                        first = first if first is not None else time.monotonic() - start
                result = await service.generate_teacher_script_section(
                    course_id=f"benchmark-{index}",
                    outline_section={"node_id":f"s-{index}", "node_name":"导数定义与切线",
                        "module_plan":[{"module_id":"core_explanation", "label":"核心教学"}]},
                    current_plan_section={"node_id":f"s-{index}", "teaching_modules":[{
                        "module_id":"core_explanation", "planned_minutes":10,
                        "knowledge_names":["导数定义", "切线斜率"]}]},
                    requirements="从差商极限解释导数，完整推导平方函数的导数；给出一点处切线例题，再提供一题练习和参考解答。",
                    on_content_delta=delta)
                return {"seconds":round(time.monotonic()-start, 3), "first_delta_seconds":first,
                        "delta_count":deltas, "characters":len(result.get("content", "")),
                        "passed":result["quality_report"]["passed"],
                        "advice_count":len(result["quality_report"].get("review_issues") or []),
                        "content":result.get("content", "")}
            start = time.monotonic()
            samples = await asyncio.gather(*(lesson(i) for i in range(count)))
            return {"concurrency":count, "seconds":round(time.monotonic()-start, 3),
                    "model_call_count":requests, "samples":samples}
        async def run():
            if args.stage == "handout":
                return [await measure(1), await measure(4)]
            fixture = args.app_root / "docs/评测/课程与课件样例/生成链路收敛/固定输入.json"
            cases = json.loads(fixture.read_text())["cases"]
            case = next((item for item in cases if item["case_id"] == args.case), None)
            if case is None:
                raise ValueError("Unknown evaluation case")
            rows = []
            for index in range(args.runs):
                service = CourseService()
                latest = {}
                started = time.monotonic()
                try:
                    result = await service.build_course_draft(
                        course_id=f"outline-benchmark-{index}", topic=case["title"],
                        target_audience=case["audience"],
                        requirements=case["source_text"] + "\n" + "\n".join(case["requirements"]),
                        teacher_course_brief={"lecture_count": case["lesson_count"],
                            "total_class_hours": case["lesson_count"], "course_period_minutes": 45,
                            "target_audience": case["audience"], "teaching_context": "classroom"},
                        stop_after_outline=True, on_checkpoint=lambda item: latest.update(item),
                    )
                    status, error_type = "completed", ""
                except Exception as error:
                    result = latest
                    status, error_type = "failed", type(error).__name__
                stage = (result.get("generation_stage_artifacts") or {}).get("outline") or {}
                rows.append({"run": index + 1, "case_id": args.case,
                    "status": status, "error_type": error_type,
                    "seconds": round(time.monotonic() - started, 3),
                    "model_call_count": stage.get("model_call_count", 0),
                    "repair_count": stage.get("repair_count", 0),
                    "metrics": stage.get("request_metrics") or [],
                    "issues": (stage.get("validation_report") or {}).get("issues") or [],
                    "result": result})
            return rows
        results = asyncio.run(run())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"mock":args.mock,"runs":results}, ensure_ascii=False, indent=2))
    if args.stage == "outline":
        print(json.dumps({"stage": "outline", "runs": [{k: v for k, v in row.items() if k != "result"} for row in results]}, ensure_ascii=False))
    else:
        print(json.dumps({"mock":args.mock,"runs":[{**r,"samples":[{k:v for k,v in s.items() if k!='content'} for s in r['samples']]} for r in results]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
