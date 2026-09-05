#!/usr/bin/env python3
"""Real-model verification of the L3b wiring.

The existing generation smoke drives TaskManager in-process with no frontend,
so it exercises the backend half of the wiring and never the browser half.
This harness closes that gap end to end:

    real generation  ->  every finalized node's body
                     ->  the REAL frontend validator, in a REAL browser
                     ->  the REAL endpoint contract (record_node_render_diagnostics)
                     ->  the node's quality report

It answers the three questions unit tests could not:
  1. does every finalized node actually get validated?
  2. do concurrent finalizations interfere with each other?
  3. how often does the report arrive after the task is already gone (404)?

Deliberately calls ``record_node_render_diagnostics`` directly rather than over
HTTP: the router is a four-line wrapper already covered by tests, while the
part with real risk is the browser->manager->quality path.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
for module_root in (ROOT, BACKEND):
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))


def _browser() -> str:
    explicit = os.environ.get("LAYOUT_SMOKE_BROWSER", "")
    if explicit and Path(explicit).exists():
        return explicit
    cache = Path.home() / ".cache" / "ms-playwright"
    if cache.exists():
        for entry in sorted(cache.iterdir()):
            candidate = entry / "chrome-linux64" / "chrome"
            if entry.name.startswith("chromium-") and candidate.exists():
                return str(candidate)
    return ""


def _playwright_root() -> str:
    for candidate in (
        os.environ.get("PLAYWRIGHT_NODE_PATH", ""),
        "/tmp/lzshot/node_modules",
    ):
        if candidate and (Path(candidate) / "playwright-core").exists():
            return candidate
    return ""


# Runs the project's own validator (bundled via vite) against real node bodies.
_VALIDATOR_DRIVER = r"""
import { validateRenderedContent, renderDiagnosticsFor } from '/src/utils/render-validation.ts'
window.__validate = (items) => {
  const result = validateRenderedContent(items)
  const perNode = {}
  for (const item of items) perNode[item.id] = renderDiagnosticsFor(result, item.id)
  return { passed: result.passed, checked: result.checkedCount, perNode }
}
"""


async def validate_in_browser(nodes: list[dict], port: int) -> dict:
    """Run the real frontend validator over real node bodies in a real browser."""
    node_path = _playwright_root()
    browser_path = _browser()
    if not node_path or not browser_path:
        return {"skipped": True, "reason": "playwright-core 或浏览器不可用"}

    driver = ROOT / "frontend" / "src" / "__l3b_probe__.ts"
    page = ROOT / "frontend" / "l3b-probe.html"
    driver.write_text(_VALIDATOR_DRIVER, encoding="utf-8")
    page.write_text(
        '<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>'
        '<script type="module" src="/src/__l3b_probe__.ts"></script></body></html>',
        encoding="utf-8",
    )
    vite = subprocess.Popen(
        ["npx", "vite", "--port", str(port), "--strictPort"],
        cwd=ROOT / "frontend",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    script = f"""
const {{ chromium }} = require('{node_path}/playwright-core')
const items = {json.dumps([{"id": n["node_id"], "content": n["content"]} for n in nodes], ensure_ascii=False)}
;(async () => {{
  const browser = await chromium.launch({{ executablePath: '{browser_path}' }})
  const page = await browser.newPage()
  let lastError = ''
  for (let attempt = 0; attempt < 60; attempt += 1) {{
    try {{
      await page.goto('http://127.0.0.1:{port}/l3b-probe.html', {{ waitUntil: 'networkidle' }})
      await page.waitForFunction(() => typeof window.__validate === 'function', {{ timeout: 3000 }})
      break
    }} catch (error) {{ lastError = String(error).slice(0, 120); await new Promise(r => setTimeout(r, 1000)) }}
  }}
  const out = await page.evaluate((payload) => window.__validate(payload), items)
  console.log(JSON.stringify(out))
  await browser.close()
}})().catch(e => {{ console.log(JSON.stringify({{ error: String(e).slice(0, 300) }})); process.exit(1) }})
"""
    try:
        proc = subprocess.run(
            ["node", "-e", script],
            capture_output=True,
            text=True,
            timeout=300,
            env={**os.environ, "NODE_PATH": node_path},
        )
        raw = (proc.stdout or "").strip().splitlines()
        return json.loads(raw[-1]) if raw else {"error": (proc.stderr or "")[-300:]}
    finally:
        vite.terminate()
        try:
            vite.wait(timeout=15)
        except subprocess.TimeoutExpired:
            vite.kill()
        driver.unlink(missing_ok=True)
        page.unlink(missing_ok=True)


async def run(subject: str, timeout_seconds: int, port: int) -> dict:
    import jobs.manager as task_manager_module
    from course_repository import CourseDocumentRepository
    from course_generation.service import CourseService
    from course_versions import CourseVersionRepository
    from generation_workspace import GenerationWorkspaceRepository
    from learning_asset_storage import LearningAssetRepository
    from material_storage import MaterialRepository
    from question_bank import QuestionBankRepository
    from storage import Storage
    from jobs.manager import TaskManager

    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="lingzhi-l3b-") as temporary:
        data_root = Path(temporary)
        for name in ("TASKS_FILE", "DEFAULT_TASKS_FILE"):
            setattr(task_manager_module, name, data_root / "generation_jobs.json")
        # Construction mirrors scripts/generation_publication_smoke.py; these
        # repositories have specific expected argument shapes.
        storage = Storage(str(data_root))
        documents = CourseDocumentRepository(storage)
        manager = TaskManager(
            storage,
            CourseService(materials=MaterialRepository(data_root / "materials")),
            None,
            version_repository=CourseVersionRepository(data_root / "course_versions"),
            asset_repository=LearningAssetRepository(data_root / "learning_assets"),
            workspace_repository=GenerationWorkspaceRepository(
                data_root / "generation_workspaces"
            ),
            document_repository=documents,
            question_bank_repository_override=QuestionBankRepository(
                data_root / "question_banks"
            ),
        )
        await manager.start()
        finalized_order: list[str] = []
        try:
            job = await manager.create_generation_job({
                "subject": subject,
                "target_audience": "大学生",
                "difficulty": "beginner",
                "style": "academic",
                "requirements": (
                    "这是 L3b 接线验收课程。生成 1 章 2 节，每节都必须包含至少一个"
                    "块级数学公式（$$...$$），用于验证真实 KaTeX 渲染校验。"
                ),
                "materials": [],
                "material_bindings": [],
                "grounding_strategy": "general_assisted",
                "pedagogy_mode": "math_formal",
                "generation_mode": "fast",
                "course_purpose": "systematic",
            })
            task_id = str(job["job_id"])
            course_id = str(job["course_id"])

            while time.monotonic() - started < timeout_seconds:
                task = manager.tasks[task_id]
                if task.get("status") == "waiting_for_review":
                    review = manager.get_generation_review(course_id)
                    step = str((review or {}).get("step") or "")
                    if step:
                        await manager.confirm_generation_step(course_id, step)
                        continue
                if task.get("status") in {
                    "completed", "completed_with_warnings", "failed", "conflict",
                }:
                    break
                await asyncio.sleep(2)

            course = manager._load_task_course(task_id) or storage.load_course(course_id)
            nodes = [
                {"node_id": str(n.get("node_id")), "content": str(n.get("node_content") or "")}
                for n in course.get("nodes", [])
                if int(n.get("node_level") or 1) == 2 and str(n.get("node_content") or "").strip()
            ]
            finalized_order = [n["node_id"] for n in nodes]

            verdict = await validate_in_browser(nodes, port)
            recorded: dict[str, dict] = {}
            if not verdict.get("skipped") and not verdict.get("error"):
                # Concurrent reporting: this is exactly the interference case
                # unit tests could not cover.
                await asyncio.gather(*[
                    manager.record_node_render_diagnostics(
                        task_id, node_id, diagnostics
                    )
                    for node_id, diagnostics in verdict.get("perNode", {}).items()
                ])
                fresh = manager._load_task_course(task_id) or {}
                for node in fresh.get("nodes", []):
                    if node.get("render_diagnostics"):
                        recorded[str(node.get("node_id"))] = {
                            "render_diagnostics": node["render_diagnostics"],
                            "render_passed": (
                                node.get("generation_quality", {})
                                .get("render_quality", {})
                                .get("passed")
                            ),
                        }

            # 404 behaviour: after the task ends, a late report must not crash.
            late_report_error = ""
            try:
                await manager.record_node_render_diagnostics(
                    task_id, "definitely-not-a-node", {"math_failure_count": 1}
                )
            except Exception as exc:  # noqa: BLE001
                late_report_error = f"{type(exc).__name__}: {exc}"

            return {
                "status": "passed" if recorded else "incomplete",
                "course_id": course_id,
                "task_status": manager.tasks[task_id].get("status"),
                "finalized_nodes": finalized_order,
                "browser_verdict": verdict,
                "recorded_nodes": recorded,
                "coverage": (
                    f"{len(recorded)}/{len(finalized_order)}"
                    if finalized_order else "0/0"
                ),
                "unknown_node_report_error": late_report_error or "无异常（按预期静默忽略）",
                "elapsed_seconds": round(time.monotonic() - started, 2),
            }
        finally:
            await manager.shutdown()


def main() -> int:
    parser = argparse.ArgumentParser(description="L3b 接线的真实模型 + 真实浏览器验收")
    parser.add_argument("--subject", default="一元二次方程的判别式")
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--port", type=int, default=5211)
    args = parser.parse_args()
    try:
        result = asyncio.run(run(args.subject, args.timeout, args.port))
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
