"""Exercise the real local runtimes through an isolated ASGI app."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
import shlex
import shutil
import sys
import threading

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest

from routers import code_execution as api


@pytest.fixture
def app():
    instance = FastAPI()
    instance.include_router(api.router)

    @instance.get("/heartbeat")
    async def heartbeat():
        return {"alive": True}

    return instance


@pytest.mark.asyncio
@pytest.mark.parametrize("language,code", [
    ("python", 'print("向量", 1 + 1)'),
    ("javascript", 'console.log("向量", 1 + 1)'),
])
async def test_real_runtime_executes_unicode_output(app, language, code):
    if language == "javascript" and not shutil.which("node"):
        pytest.skip("Node.js is not installed on this test host")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/execute", json={"code": code, "language": language})
    assert response.status_code == 200
    result = response.json()
    assert result["success"], result
    assert result["output"].strip() == "向量 2"
    assert result["error"] is None


@pytest.mark.asyncio
async def test_failed_process_without_stderr_still_reports_failure(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/execute", json={"code": "raise SystemExit(7)"})
    result = response.json()
    assert result["success"] is False
    assert result["output"] == ""
    assert result["error"] and "7" in result["error"]


@pytest.mark.asyncio
async def test_running_code_does_not_block_other_requests_or_event_loop(app, monkeypatch):
    started = threading.Event()
    execute = api._execute_code

    def observe_start(*args):
        started.set()
        return execute(*args)

    monkeypatch.setattr(api, "_execute_code", observe_start)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        pending = asyncio.create_task(client.post("/api/execute", json={
            "code": 'import time\ntime.sleep(0.6)\nprint("done")',
        }))
        while not started.is_set():
            await asyncio.sleep(0.005)
        try:
            assert not pending.done(), "the route blocked the event loop until execution finished"
            for _ in range(3):
                heartbeat = await asyncio.wait_for(client.get("/heartbeat"), timeout=0.2)
                assert heartbeat.json() == {"alive": True}
                await asyncio.sleep(0.01)
            assert not pending.done()
        finally:
            response = await pending
        assert response.json()["output"].strip() == "done"


@pytest.mark.asyncio
@pytest.mark.parametrize("language,code", [
    ("python", "import time\ntime.sleep(5)"),
    ("javascript", "while (true) {}"),
])
async def test_timeout_keeps_existing_limit_and_cleans_temporary_files(app, monkeypatch, language, code):
    if language == "javascript" and not shutil.which("node"):
        pytest.skip("Node.js is not installed on this test host")
    directories = []
    original = api.tempfile.mkdtemp

    def track_temp_directory(*args, **kwargs):
        directory = original(*args, **kwargs)
        directories.append(directory)
        return directory

    monkeypatch.setattr(api.tempfile, "mkdtemp", track_temp_directory)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/execute", json={
            "code": code, "language": language, "timeout": 1,
        })
    result = response.json()
    assert result["success"] is False
    assert "超时" in result["error"]
    assert directories and all(not Path(directory).exists() for directory in directories)


@pytest.mark.asyncio
async def test_host_credentials_and_pythonpath_do_not_reach_runtime(app, monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "test-only-secret")
    monkeypatch.setenv("PYTHONPATH", "test-only-extra-modules")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/execute", json={
            "code": 'import os\nprint(os.environ.get("AI_API_KEY"), os.environ.get("PYTHONPATH"))',
        })
    assert response.json()["success"]
    assert response.json()["output"].strip() == "None None"


@pytest.mark.asyncio
async def test_existing_security_validation_blocks_execution(app, monkeypatch):
    def unexpected(*args):
        raise AssertionError("unsafe code reached the executor")

    monkeypatch.setattr(api, "_execute_code", unexpected)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/execute", json={"code": 'import subprocess\nprint("bad")'})
    assert response.json()["success"] is False
    assert "安全" in response.json()["error"]


@pytest.mark.parametrize("language,memory_limit", [("python", 262144), ("javascript", 1048576)])
def test_linux_command_quotes_paths_and_preserves_resource_limits(monkeypatch, language, memory_limit):
    monkeypatch.setattr(api.platform, "system", lambda: "Linux")
    monkeypatch.setattr(api, "_linux_process_limit", lambda: 32)
    runtime = "/opt/teaching runtime/python;echo wrong"
    source = "/tmp/student's work/code.py"
    command = api._build_sandbox_command([runtime], source, language)
    assert command[:2] == ["bash", "-c"]
    limits, execution = command[2].split(" exec ", 1)
    assert shlex.split(execution) == [runtime, source]
    for limit in (f"-v {memory_limit}", "-f 1024", "-u 32", "-t 10"):
        assert limit in limits


def test_runtime_and_windows_environment_are_explicit(monkeypatch, tmp_path):
    monkeypatch.setattr(api.platform, "system", lambda: "Windows")
    monkeypatch.setenv("SystemRoot", "C:\\Windows")
    monkeypatch.setenv("SERVICE_TOKEN", "test-only-token")
    assert api._runtime_command("python") == [sys.executable]
    environment = api._sandbox_environment(str(tmp_path), sys.executable)
    assert environment["SystemRoot"] == "C:\\Windows"
    assert "SERVICE_TOKEN" not in environment
    assert environment["TEMP"] == str(tmp_path)
    assert environment["PATH"].split(os.pathsep)[0] == os.path.dirname(sys.executable)


def test_linux_process_budget_accounts_for_existing_threads(tmp_path):
    for pid, threads in (("100", 37), ("101", 11)):
        process = tmp_path / pid
        process.mkdir()
        (process / "status").write_text(f"Name:\ttest\nThreads:\t{threads}\n")
    (tmp_path / "exited").mkdir()
    (tmp_path / "102").mkdir()  # exited between directory listing and status read
    assert api._linux_process_limit(str(tmp_path)) == 37 + 11 + 32
