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
    parser.add_argument("--stage", choices=("handout", "outline", "g2"), default="handout")
    parser.add_argument("--course-json", type=Path, help="Synthetic accepted outline for the G2 chain")
    parser.add_argument("--case", default="statistics_basic")
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be positive")
    if args.stage == "g2" and (not args.course_json or args.mock):
        parser.error("G2 requires --course-json and a real selfhost provider")
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
                    return "<!-- section:" + json.loads(a[0])["sections"][0]["section_id"] + " -->\n" + "测试正文。" * 400 + "\n<!-- handout:end -->"
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
                from teacher_script import parse_handout_stream
                section_id = f"s-{index}"
                result = await service.generate_teacher_handout(
                    course_id=f"benchmark-{index}", outline_sections=[{"node_id": section_id, "node_name": "导数定义与切线"}],
                    plan_sections={section_id: {"knowledge_names": ["导数定义", "切线斜率"]}}, lesson_context={},
                    requirements="从差商极限解释导数，完整推导平方函数的导数；给出一点处切线例题，再提供一题练习和参考解答。",
                    on_content_delta=delta)
                parsed = parse_handout_stream(result["text"], [section_id], provider_complete=True)
                return {"seconds":round(time.monotonic()-start, 3), "first_delta_seconds":first,
                        "delta_count":deltas, "characters":len(result["text"]),
                        "passed":not parsed["error"], "metrics":result["telemetry"], "content":result["text"]}
            start = time.monotonic()
            samples = await asyncio.gather(*(lesson(i) for i in range(count)))
            return {"concurrency":count, "seconds":round(time.monotonic()-start, 3),
                    "model_call_count":requests, "samples":samples}
        async def run():
            if args.stage == "handout":
                return [await measure(1), await measure(2)]
            if args.stage == "g2":
                from copy import deepcopy
                from teacher_lesson_authoring import TeacherLessonAuthoringRepository, TeacherLessonAuthoringService, lesson_scope
                from teaching_design import recommend_lesson_arrangement
                from course_document import stable_hash
                source = json.loads(args.course_json.read_text())
                rows = []
                for index in range(args.runs):
                    course = deepcopy(source)
                    course_id = course["course_id"] = f"g2-synthetic-{index}"
                    lesson_id = next(n["node_id"] for n in course["nodes"] if n.get("node_level") == 1)
                    outline_id = str(course.get("blueprint_revision_id") or stable_hash(course["course_plan"], prefix="outline"))
                    repo = TeacherLessonAuthoringRepository(Path(isolated) / f"run-{index}")
                    repo.set_outline(course_id, outline_id)
                    arrangement = recommend_lesson_arrangement(course, lesson_id, source_outline_revision_id=outline_id)
                    repo.save_arrangement_revision(course_id, lesson_id, arrangement, source_outline_revision_id=outline_id)
                    service = CourseService()
                    authoring = TeacherLessonAuthoringService(repo)
                    metrics = []
                    invoke = service._call_llm
                    async def measured(*a, **kw):
                        downstream = kw.get("telemetry_sink")
                        def sink(item):
                            metrics.append(item)
                            if downstream: downstream(item)
                        kw["telemetry_sink"] = sink
                        return await invoke(*a, **kw)
                    service._call_llm = measured
                    async def persist(checkpoint):
                        repo.update_job(course_id, job["id"], checkpoint=checkpoint)
                    async def planner(current, target, on_progress):
                        return await service.prepare_teacher_lesson_plan(course_data=current, lesson_unit_id=target,
                            lesson_arrangement=arrangement, on_phase=on_progress, on_checkpoint=persist)
                    job = repo.create_job(course_id, lesson_id, source_outline_revision_id=outline_id)
                    start = time.monotonic()
                    plan_job = await authoring.run_plan_job(course_id=course_id, lesson_unit_id=lesson_id, job_id=job["id"], course_data=course, planner=planner)
                    row = {"run":index+1, "plan_status":plan_job["status"], "plan_calls":sum(m.get("physical_request_count",1) for m in metrics),
                           "plan_seconds":round(time.monotonic()-start,3), "plan_metrics":deepcopy(metrics),
                           "plan_error_code":(plan_job.get("error") or {}).get("code"), "plan_job":plan_job}
                    if plan_job["status"] == "completed":
                        lesson = repo.lesson(course_id, lesson_id)
                        plan = next(r for r in lesson["revisions"] if r["revision_id"] == lesson["working_revision_id"])["plan"]
                        plan_sections = {s["node_id"]:s for s in plan["sections"]}
                        scope = lesson_scope(course, lesson_id)
                        service.register_course_generation_metadata(course_id, course)
                        async def handout(**kw):
                            return await service.generate_teacher_handout(course_id=course_id, plan_sections=plan_sections,
                                lesson_context={"title":scope["lesson"].get("node_name"), "source":course.get("requirements", "")}, **kw)
                        metrics.clear()
                        script_job = repo.create_job(course_id, lesson_id, job_type="teacher_lesson_script_generation", source_outline_revision_id=outline_id)
                        start = time.monotonic()
                        script_job = await authoring.run_script_job(course_id=course_id, lesson_unit_id=lesson_id,
                            job_id=script_job["id"], source_plan_revision_id=lesson["working_revision_id"],
                            outline_sections=scope["sections"], plan_sections=plan_sections, generator=handout, expected_script_revision="")
                        row.update(handout_status=script_job["status"], handout_calls=sum(m.get("physical_request_count",1) for m in metrics),
                                   handout_seconds=round(time.monotonic()-start,3), handout_metrics=deepcopy(metrics),
                                   handout_error_code=(script_job.get("error") or {}).get("code"), handout_job=script_job)
                    rows.append(row)
                    args.output.parent.mkdir(parents=True, exist_ok=True)
                    args.output.write_text(json.dumps({"stage":"g2", "runs":rows}, ensure_ascii=False, indent=2))
                return rows
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
    if args.stage in {"outline", "g2"}:
        print(json.dumps({"stage": args.stage, "runs": [{k: v for k, v in row.items() if k not in {"result", "plan_job", "handout_job"}} for row in results]}, ensure_ascii=False))
    else:
        print(json.dumps({"mock":args.mock,"runs":[{**r,"samples":[{k:v for k,v in s.items() if k!='content'} for s in r['samples']]} for r in results]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
