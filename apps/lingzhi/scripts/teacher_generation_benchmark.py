"""Compare teacher generation with isolated data and one/four concurrent samples."""
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
    args = parser.parse_args()
    from dotenv import load_dotenv
    load_dotenv(args.env_file, override=True)
    for key in ("MODELSCOPE_API_KEY", "MODELSCOPE_BASE_URL", "MODELSCOPE_MODEL", "MODELSCOPE_MODEL_CANDIDATES", "MODELSCOPE_MODEL_FAST_CANDIDATES"):
        os.environ.pop(key, None)
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
            return [await measure(1), await measure(4)]
        results = asyncio.run(run())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"mock":args.mock,"runs":results}, ensure_ascii=False, indent=2))
    print(json.dumps({"mock":args.mock,"runs":[{**r,"samples":[{k:v for k,v in s.items() if k!='content'} for s in r['samples']]} for r in results]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
