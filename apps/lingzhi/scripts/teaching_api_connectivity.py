"""Exercise teaching APIs over real HTTP, Vite proxy, SSE and WebSocket.

Uses synthetic sources, a new data directory and two disposable processes.
The model must be an explicitly selected loopback qwen3.8-27b endpoint.
Never starts, stops or changes the user's existing application instances.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.parse import urlparse
import uuid

import httpx

APP_ROOT = Path(__file__).resolve().parents[1]
SOURCE = """# 二维向量的线性组合

二维向量按分量运算。给定 u=(1,2)、v=(2,1)，则 2v=(4,2)，
w=u+2v=(5,4)。数乘将两个分量同时乘以系数。
首尾连接法将 2v 的起点平移到 u 的终点 (1,2)，终点为 (5,4)。
从原点指向 (5,4) 的向量就是 w。该例为公开自编测试资料。
"""
TEACHER_ID = "connectivity-teacher"
COURSE_ID = "connectivity-synthetic-course"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def isolated_environment(output: Path, model_base: str) -> dict[str, str]:
    env = os.environ.copy()
    env.update({"LINGZHI_DATA_DIR": str(output / "data"),
                "LINGZHI_TASK_RUNTIME_MODE": "isolated_test",
                "LINGZHI_LOCAL_STUDY_AUTH": "true", "GIT_AUTO_SYNC_ENABLED": "false",
                "AI_LOCAL_PROVIDER": "http", "QIZHI_AUTH_VERIFY_URL": "",
                "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
    key = env.get("LINGZHI_LOCAL_API_KEY") or "local-experiment"
    for name in ("ZJU_QWEN_API_KEY", "AI_API_KEY", "AI_PPT_API_KEY"):
        env[name] = key
    for name in ("ZJU_QWEN_BASE_URL", "AI_API_BASE", "AI_PPT_API_BASE"):
        env[name] = model_base
    for name in ("AI_MODEL", "AI_MODEL_FAST", "AI_MODEL_CANDIDATES", "AI_MODEL_FAST_CANDIDATES",
                 "AI_ASSESSMENT_GENERATOR_MODELS", "AI_ASSESSMENT_SOLVER_MODELS",
                 "AI_ASSESSMENT_REVIEWER_MODELS", "AI_PPT_STORY_MODELS", "AI_PPT_VISUAL_MODELS"):
        env[name] = "qwen3.8-27b"
    for name in ("MODELSCOPE_API_KEY", "MODELSCOPE_BASE_URL", "MODELSCOPE_MODEL",
                 "MODELSCOPE_MODEL_CANDIDATES", "MODELSCOPE_MODEL_FAST_CANDIDATES",
                 "LINGZHI_TEST_ALLOW_EXTERNAL_TEXT_PROVIDERS"):
        env[name] = ""
    return env


def teacher_fixture() -> dict:
    return {"course_id": COURSE_ID, "course_name": "接口连通性公开测试",
            "authoring_surface": "teacher", "owner_id": TEACHER_ID,
            "blueprint_revision_id": "connectivity-outline", "current_course_version_id": "",
            "nodes": [
                {"node_id": "L1-1", "parent_node_id": "root", "node_level": 1, "node_name": "第一讲"},
                {"node_id": "L2-1-1", "parent_node_id": "L1-1", "node_level": 2,
                 "node_name": "二维向量", "node_content": SOURCE, "generation_status": "completed"}],
            "course_plan": {"chapters": [{"node_id": "L1-1", "title": "第一讲",
                "sections": [{"node_id": "L2-1-1", "title": "二维向量"}]}]}}


def teacher_plan() -> dict:
    points = [{"name": "分量运算", "statement": "u=(1,2)、v=(2,1)，2v=(4,2)，u+2v=(5,4)。"},
              {"name": "首尾连接", "statement": "将 2v 起点平移到 (1,2)，终点为 (5,4)，原点到终点为 w。"},
              {"name": "平移不改变向量", "statement": "平移只改变起点，不改变两个分量及位移。"}]
    return {"schema_version": "course_teaching_plan_v3",
            "source_outline_revision_id": "connectivity-outline", "sections": [{
                "node_id": "L2-1-1", "learning_objective": "能计算并解释二维向量线性组合。",
                "key_points": ["分量运算", "首尾连接", "平移不改变向量"], "key_difficulties": ["平移不改变向量"],
                "in_class_checks": ["计算 u+2v 并解释终点。"], "homework": ["核验 (5,4)。"],
                "teaching_notes": ["只使用给定坐标。"],
                "knowledge_structure": [{"knowledge_points": points}],
                "teaching_modules": [{"module_id": "core_explanation", "teaching_purpose": "解释向量组合",
                    "knowledge_names": ["分量运算", "首尾连接", "平移不改变向量"], "planned_minutes": 20,
                    "teacher_activity": "按分量和首尾连接两种方法解释。",
                    "student_activity": "核验目标向量的终点。"}]}]}


class Probe:
    def __init__(self, client: httpx.AsyncClient, output: Path):
        self.client, self.output = client, output
        self.results: list[dict] = []

    def record(self, name: str, passed: bool, *, fatal: bool = True, **details):
        self.results.append({"name": name, "passed": passed, **details})
        print(json.dumps(self.results[-1], ensure_ascii=False), flush=True)
        if not passed and fatal:
            raise AssertionError(name)

    async def request(self, name: str, method: str, path: str, expected=200, *, fatal=True, **kwargs):
        start = time.monotonic()
        response = await self.client.request(method, path, **kwargs)
        statuses = expected if isinstance(expected, tuple) else (expected,)
        if response.status_code not in statuses:
            (self.output / (name + "-error.txt")).write_text(response.text, encoding="utf-8")
        self.record(name, response.status_code in statuses, fatal=fatal, method=method, path=path,
                    http_status=response.status_code, seconds=round(time.monotonic() - start, 2))
        return response

    async def poll(self, path: str, headers: dict, extract, *, timeout: float = 600):
        start, count = time.monotonic(), 0
        while time.monotonic() - start < timeout:
            response = await self.client.get(path, headers=headers)
            response.raise_for_status()
            body = response.json()
            status = extract(body)
            count += 1
            if status not in {"pending", "running"}:
                return body, status, count, round(time.monotonic() - start, 2)
            await asyncio.sleep(1)
        raise TimeoutError("Own disposable task did not finish within the probe deadline")

    async def sse(self, name: str, path: str, payload: dict, headers: dict, *, terminal="done"):
        events, chunks, event = [], [], ""
        start = time.monotonic()
        async with self.client.stream("POST", path, json=payload,
                                      headers={**headers, "Accept": "text/event-stream"}) as response:
            self.record(name + "_http", response.status_code == 200
                        and "text/event-stream" in response.headers.get("content-type", ""),
                        method="POST", path=path, http_status=response.status_code)
            async for line in response.aiter_lines():
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:"):
                    body = json.loads(line[5:].strip())
                    events.append((event, body))
                    if event == "answer":
                        chunks.append(body.get("chunk", ""))
        (self.output / (name + ".json")).write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
        self.record(name + "_complete", bool(chunks) and any(e == terminal for e, _ in events)
                    and not any(e == "error" for e, _ in events),
                    event_types=sorted({e for e, _ in events}), characters=sum(map(len, chunks)),
                    seconds=round(time.monotonic() - start, 2))
        return events


async def personal_chain(probe: Probe):
    p = "/api/study"
    config = (await probe.request("study_config", "GET", p + "/auth/config")).json()
    probe.record("local_auth_isolated", config["local_login_enabled"] is True)
    await probe.request("anonymous_denied", "GET", p + "/auth/me", 401)
    accounts = []
    password = uuid.uuid4().hex
    for name in ("probe_student_a", "probe_student_b"):
        data = (await probe.request("register_" + name, "POST", p + "/auth/register",
            json={"username": name, "password": password})).json()
        accounts.append({"Authorization": "Bearer " + data["token"]})
    headers, foreign = accounts
    await probe.request("wrong_password", "POST", p + "/auth/login", 401,
                        json={"username": "probe_student_a", "password": "deliberately_wrong"})
    await probe.request("login", "POST", p + "/auth/login",
                        json={"username": "probe_student_a", "password": password})
    me = (await probe.request("identity", "GET", p + "/auth/me", headers=headers)).json()
    probe.record("identity_role", me["role"] == "student")
    source = (await probe.request("paste_and_parse", "POST", p + "/sources/text", headers=headers,
                               json={"title": "向量测试.md", "content": SOURCE})).json()
    probe.record("source_ranges", bool(source["sections"]) and source["status"] in {"parsed", "degraded"})
    await probe.request("upload_and_parse", "POST", p + "/sources/upload", headers=headers,
                        files={"file": ("另份公开测试.md", SOURCE.encode(), "text/markdown")})
    downloaded = await probe.request("source_download", "GET", p + "/sources/" + source["id"] + "/download", headers=headers)
    probe.record("source_hash", hashlib.sha256(downloaded.content).hexdigest() == source["sha256"])
    await probe.request("source_list", "GET", p + "/sources", headers=headers)
    await probe.request("source_foreign_denied", "GET", p + "/sources/" + source["id"] + "/download", 404, headers=foreign)
    payload = {"request_id": uuid.uuid4().hex, "title": "公开向量测试讲义", "purpose": "systematic",
               "level": "beginner", "time_minutes": 10, "language": "zh",
               "requirements": "简洁讲解给定坐标的计算和几何意义，约800字，附一题自测和独立解答。",
               "selections": [{"asset_id": source["id"], "section_id": source["sections"][0]["id"]}]}
    await probe.request("invalid_scope_denied", "POST", p + "/materials", 422, headers=headers,
                        json={**payload, "selections": [{"asset_id": source["id"], "section_id": "absent"}]})
    material = (await probe.request("handout_start", "POST", p + "/materials", headers=headers, json=payload)).json()
    duplicate = (await probe.request("handout_duplicate", "POST", p + "/materials", headers=headers, json=payload)).json()
    probe.record("handout_same_task", material["id"] == duplicate["id"] and material["task_id"] == duplicate["task_id"])
    await probe.request("handout_request_conflict", "POST", p + "/materials", 409, headers=headers,
                        json={**payload, "title": "冲突请求"})
    path = p + "/materials/" + material["id"]
    await probe.request("material_foreign_denied", "GET", path, 404, headers=foreign)
    await probe.request("legacy_task_path_denied", "GET", "/api/tasks/" + material["task_id"], (403, 404),
                        headers=headers)
    saved, status, polls, seconds = await probe.poll(path, headers, lambda b: b["status"])
    (probe.output / "personal-handout.json").write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")
    probe.record("handout_completed_and_saved", status == "completed", task_status=status, polls=polls, seconds=seconds,
                 error_code=(saved.get("task") or {}).get("error_code"))
    revision = saved["revisions"][-1]
    section = revision["sections"][0]
    probe.record("handout_structure_and_source", section["complete"] and bool(section["blocks"])
                 and section["source"]["source_sha256"] == source["sha256"])
    await probe.request("material_list", "GET", p + "/materials", headers=headers)
    await probe.request("material_reopen", "GET", path, headers=headers)
    await probe.request("save_note", "PUT", path + "/note", headers=headers,
                        json={"revision_id": revision["id"], "content": "核验结果 w=(5,4)。"})
    reopened = (await probe.request("note_reopen", "GET", path, headers=headers)).json()
    probe.record("note_persisted", reopened["notes"][revision["id"]]["content"] == "核验结果 w=(5,4)。")
    await probe.request("wrong_note_revision", "PUT", path + "/note", 409, headers=headers,
                        json={"revision_id": "obsolete", "content": "test"})
    exported = await probe.request("handout_export", "GET", path + "/export", headers=headers)
    probe.record("export_has_source_and_body", source["sha256"] in exported.text and section["content"] in exported.text)
    history = (await probe.request("assistant_history", "GET", path + "/assistant", headers=headers)).json()
    probe.record("assistant_initially_empty", not history["messages"])
    question = {"request_id": uuid.uuid4().hex, "revision_id": revision["id"], "section_id": section["id"],
                "block_id": "", "quote": "", "language": "zh",
                "text": "解释资料中的 w=u+2v。请用二维向量图表示原向量、首尾连接和结果，标注依据。"}
    await probe.request("assistant_version_conflict", "POST", path + "/assistant", 409,
                        headers=headers, json={**question, "revision_id": "obsolete"})
    answer = (await probe.request("assistant_start", "POST", path + "/assistant", headers=headers, json=question)).json()
    duplicate = (await probe.request("assistant_duplicate", "POST", path + "/assistant", headers=headers, json=question)).json()
    probe.record("assistant_same_task", answer["messages"][-1]["task_ref"] == duplicate["messages"][-1]["task_ref"]
                 and len(duplicate["messages"]) == 2)
    await probe.request("assistant_request_conflict", "POST", path + "/assistant", 409,
                        headers=headers, json={**question, "text": "another question"})
    await probe.request("assistant_foreign_denied", "GET", path + "/assistant", 404, headers=foreign)
    saved_answer, status, polls, seconds = await probe.poll(path + "/assistant", headers, lambda b: b["messages"][-1]["status"])
    (probe.output / "personal-assistant.json").write_text(json.dumps(saved_answer, ensure_ascii=False, indent=2), encoding="utf-8")
    probe.record("assistant_completed_and_saved", status == "complete" and bool(saved_answer["messages"][-1]["content"]),
                 task_status=status, polls=polls, seconds=seconds)
    await probe.request("assistant_reopen", "GET", path + "/assistant", headers=headers)
    # Completed jobs are idempotent no-ops: these checks must not call the model again.
    await probe.request("completed_handout_continue", "POST", path + "/continue", headers=headers)
    task_id = answer["messages"][-1]["task_ref"]["task_id"]
    await probe.request("completed_assistant_continue", "POST", path + "/assistant/" + task_id + "/continue", headers=headers)
    await probe.request("assistant_foreign_continue_denied", "POST", path + "/assistant/" + task_id + "/continue", 404, headers=foreign)
    unchanged = (await probe.request("completed_reply_unchanged", "GET", path + "/assistant", headers=headers)).json()
    probe.record("continue_did_not_duplicate", unchanged["messages"] == saved_answer["messages"])
    probe.record("real_diagram_fences", "```lingzhi-diagram" in section["content"]
                 and "```lingzhi-diagram" in saved_answer["messages"][-1]["content"])
    await probe.request("logout", "POST", p + "/auth/logout", headers=headers)
    await probe.request("expired_session_denied", "GET", p + "/auth/me", 401, headers=headers)


async def teacher_chain(probe: Probe):
    headers = {"X-User-Id": TEACHER_ID}
    path = "/api/teacher/courses/" + COURSE_ID
    await probe.request("teacher_authoring_read", "GET", path + "/lesson-authoring", headers=headers)
    await probe.request("teacher_plan_save", "PATCH", path + "/lessons/L1-1/plan/draft", headers=headers,
                        json={"plan": teacher_plan(), "source_outline_revision_id": "connectivity-outline"})
    job = (await probe.request("teacher_handout_start", "POST", path + "/lessons/L1-1/script/generate", 202,
        headers=headers, json={"request_id": uuid.uuid4().hex,
            "requirements": "根据教案给定的坐标，简洁讲解向量组合，约800字，并用二维向量图辅助解释。"})).json()["job"]
    result, status, polls, seconds = await probe.poll(path + "/lesson-jobs/" + job["id"], headers, lambda b: b["job"]["status"])
    (probe.output / "teacher-handout-job.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    probe.record("teacher_handout_completed", status == "completed", fatal=False,
                 task_status=status, polls=polls, seconds=seconds,
                 error_code=(result["job"].get("error") or {}).get("code"))
    if status != "completed":
        probe.record("teacher_failed_output_retained", bool(result["job"].get("raw_response")))
    preview_path = "/api/teacher/courses/" + COURSE_ID + "/preview"
    preview = (await probe.request("teacher_preview_read", "GET", preview_path, headers=headers)).json()
    probe.record("teacher_body_readable", preview["availability"]["reading"])
    if status == "completed":
        probe.record("teacher_handout_saved", bool(preview["handouts"]))
    await probe.request("teacher_preview_foreign_denied", "GET", preview_path, 404,
                        headers={"X-User-Id": "connectivity-other"})
    question = "用资料中的坐标简要说明 w=u+2v，并画出原向量和首尾连接。"
    for perspective in ("learner", "teacher"):
        events = await probe.sse("qa_" + perspective, "/api/ask_events",
            {"course_id": COURSE_ID, "node_id": "L2-1-1", "question": question,
             "perspective": perspective, "request_id": uuid.uuid4().hex}, headers)
        context = next(body for event, body in events if event == "context")
        cid = context["conversation_id"]
        history = (await probe.request("qa_" + perspective + "_history", "GET",
             "/api/ai-teacher/conversations/" + cid, headers=headers, params={"course_id": COURSE_ID})).json()
        final_answer = next(body["answer"] for event, body in events if event == "final_answer")
        reply = history["messages"][-1]
        probe.record("qa_" + perspective + "_persisted", reply["role"] == "assistant"
                     and reply["status"] == "complete" and reply["content"] == final_answer)
    await probe.sse("preview_qa", preview_path + "/ask",
        {"preview_revision": preview["preview_revision"], "question": question}, headers, terminal="complete")
    await probe.request("preview_stale_revision", "POST", preview_path + "/ask", 409, headers=headers,
                        json={"preview_revision": "obsolete", "question": question})
    await companion_chain(probe, preview, headers)


async def companion_chain(probe: Probe, preview: dict, headers: dict):
    preview_path = "/api/teacher/courses/" + COURSE_ID + "/preview"
    response = await probe.request("preview_companion", "POST", preview_path + "/study-dialogue", headers=headers,
        json={"preview_revision": preview["preview_revision"], "language": "en",
              "question": "As a supplied synthetic example, u=(1,2), v=(2,1), w=u+2v=(5,4). Explain the calculation and show a vector diagram."}, fatal=False)
    dialogue = response.json()
    if response.status_code == 200:
        probe.record("preview_companion_json", isinstance(dialogue.get("reply"), str) and "draft" in dialogue)
    (probe.output / "preview-companion.json").write_text(json.dumps(dialogue, ensure_ascii=False, indent=2), encoding="utf-8")
    course = (await probe.request("course_read", "GET", "/api/courses/" + COURSE_ID, headers=headers)).json()
    dialogue_path = "/api/courses/" + COURSE_ID + "/learning-records/study-dialogues"
    conversation = (await probe.request("companion_open", "POST", dialogue_path + "/open", headers=headers,
        json={"kind": "explain", "node_id": "L2-1-1", "language": "zh",
              "course_version_id": course.get("current_course_version_id") or ""})).json()
    command = {"expected_revision": conversation["study_workspace"]["revision"], "action": "discuss",
               "text": "说明为什么组合后的终点是 (5,4)，用资料中的向量图解释。",
               "request_id": uuid.uuid4().hex, "language": "zh"}
    command_path = dialogue_path + "/" + conversation["conversation_id"] + "/command"
    discussed = (await probe.request("companion_discuss", "POST", command_path, headers=headers, json=command)).json()
    probe.record("companion_reply_saved", bool(discussed.get("messages"))
                 and discussed["study_workspace"]["revision"] > command["expected_revision"])
    duplicate = (await probe.request("companion_duplicate", "POST", command_path, headers=headers, json=command)).json()
    probe.record("companion_idempotent", duplicate == discussed)
    await probe.request("companion_request_conflict", "POST", command_path, 409,
                        headers=headers, json={**command, "text": "different request"})
    (probe.output / "companion.json").write_text(json.dumps(discussed, ensure_ascii=False, indent=2), encoding="utf-8")


async def run(probe: Probe, model_base: str, key: str, frontend_port: int, only: str):
    model_response = await probe.client.get(model_base + "/models", headers={"Authorization": "Bearer " + key})
    probe.record("model_directory", model_response.status_code == 200
                 and "qwen3.8-27b" in {item.get("id") for item in model_response.json().get("data", [])})
    health = (await probe.request("proxy_runtime_readiness", "GET", "/api/health")).json()
    probe.record("runtime_ready", health["ready"] and health["checks"]["text_model"]["configured"])
    await probe.request("frontend_preview_asset", "GET", "/dev/teaching-diagram-preview.html")
    import websockets
    async with websockets.connect(f"ws://127.0.0.1:{frontend_port}/ws", open_timeout=10) as ws:
        await ws.send(json.dumps({"type": "ping"}))
        reply = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
        probe.record("websocket_proxy_ping", reply.get("type") == "pong")
    if only in {"all", "personal"}:
        await personal_chain(probe)
    if only in {"all", "teacher"}:
        await teacher_chain(probe)
    if only == "companion":
        headers = {"X-User-Id": TEACHER_ID}
        preview = (await probe.request("teacher_preview_read", "GET",
            "/api/teacher/courses/" + COURSE_ID + "/preview", headers=headers)).json()
        await companion_chain(probe, preview, headers)
    if any(not item["passed"] for item in probe.results):
        raise AssertionError("Some checks failed; independent interfaces were still tested")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-base-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--only", choices=("all", "personal", "teacher", "companion"), default="all")
    args = parser.parse_args()
    endpoint = urlparse(args.model_base_url)
    if endpoint.hostname not in {"localhost", "127.0.0.1", "::1"} or endpoint.scheme not in {"http", "https"} or endpoint.path.rstrip("/") != "/v1" or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment:
        parser.error("Use a loopback /v1 endpoint without embedded credentials")
    output = args.output.resolve()
    if output.is_relative_to(APP_ROOT.parents[1]) or (output.exists() and any(output.iterdir())):
        parser.error("Use a new/empty output directory outside the repository")
    node = shutil.which("node")
    vite = APP_ROOT / "frontend/node_modules/vite/bin/vite.js"
    if not node or not vite.is_file():
        parser.error("Install the application's existing frontend dependencies first")
    output.mkdir(parents=True, exist_ok=True)
    fixture_path = output / "teacher-fixture.json"
    fixture_path.write_text(json.dumps(teacher_fixture(), ensure_ascii=False, indent=2), encoding="utf-8")
    backend_port, frontend_port = free_port(), free_port()
    while frontend_port == backend_port:
        frontend_port = free_port()
    env = isolated_environment(output, args.model_base_url.rstrip("/"))
    launcher = """import json, sys
from pathlib import Path
from storage import storage
from course_document import document_from_generation_draft
source = json.load(open(sys.argv[1], encoding='utf-8'))
source['course_document'] = document_from_generation_draft(source).model_dump(mode='json')
storage.save_course_sync(source['course_id'], source)
from ai_base import AIBase
original_call = AIBase._call_llm
counter = 0
async def recorded_call(self, *args, **kwargs):
    global counter
    counter += 1
    call_number = counter
    result = await original_call(self, *args, **kwargs)
    Path(sys.argv[1]).with_name(f'model-response-{call_number}.txt').write_text(result or '', encoding='utf-8')
    return result
AIBase._call_llm = recorded_call
import uvicorn
uvicorn.run('main:app', host='127.0.0.1', port=int(sys.argv[2]), log_level='warning')
"""
    processes: list[subprocess.Popen] = []
    report = {"status": "failed", "scope": "isolated_local_real_http", "chains": args.only, "model": "qwen3.8-27b"}
    report["probe_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    report["base_commit"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=APP_ROOT, text=True).strip()
    probe = None
    try:
        with ExitStack() as stack:
            for name, command, cwd, child_env in [
                ("backend", [sys.executable, "-c", launcher, str(fixture_path), str(backend_port)], APP_ROOT / "backend", env),
                ("frontend", [node, str(vite), "--host", "127.0.0.1", "--port", str(frontend_port), "--strictPort"], APP_ROOT / "frontend",
                 {**env, "VITE_API_PROXY_TARGET": f"http://127.0.0.1:{backend_port}", "VITE_API_BASE_URL": "/", "VITE_QIZHI_AUTH_REQUIRED": "false"}),
            ]:
                log = stack.enter_context((output / (name + ".log")).open("w", encoding="utf-8"))
                processes.append(subprocess.Popen(command, cwd=cwd, env=child_env, stdout=log, stderr=subprocess.STDOUT,
                                                  creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0))
            deadline = time.monotonic() + 90
            with httpx.Client(timeout=2, trust_env=False) as client:
                while time.monotonic() < deadline:
                    if any(process.poll() is not None for process in processes):
                        raise RuntimeError("Disposable server exited; inspect the outside-repository log")
                    try:
                        response = client.get(f"http://127.0.0.1:{frontend_port}/api/health")
                        if response.status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(.5)
                else:
                    raise TimeoutError("Disposable services did not become ready")
            async def execute():
                nonlocal probe
                async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{frontend_port}", timeout=180, trust_env=False) as client:
                    probe = Probe(client, output)
                    await run(probe, args.model_base_url.rstrip("/"), env["AI_API_KEY"], frontend_port, args.only)
            print("Disposable services ready; existing instances unchanged.", flush=True)
            asyncio.run(execute())
            report["status"] = "passed"
    except Exception as exc:
        report["error_type"] = type(exc).__name__
        print("Connectivity probe stopped: " + type(exc).__name__, flush=True)
    finally:
        # Terminate only the two processes created by this invocation. No port/PID lookup.
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
        report["checks"] = probe.results if probe else []
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"status": report["status"], "checks": len(report["checks"]),
                          "passed": sum(item["passed"] for item in report["checks"])}, ensure_ascii=False), flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
