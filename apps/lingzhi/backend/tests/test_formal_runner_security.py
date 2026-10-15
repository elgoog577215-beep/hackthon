from __future__ import annotations

import subprocess
from types import SimpleNamespace

from runner import app as runner_app


def test_runner_health_requires_available_oci_engine(monkeypatch):
    import pytest
    from fastapi import HTTPException
    monkeypatch.setattr(runner_app.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=1))
    with pytest.raises(HTTPException) as failure:
        runner_app.health()
    assert failure.value.status_code == 503


def test_wsl_prefix_keeps_isolation_and_uses_utf8(monkeypatch):
    captured = {}
    def execute(command, **kwargs):
        captured.update(command=command, kwargs=kwargs)
        return SimpleNamespace(returncode=0, stdout='结果\n', stderr='__RUNNER_EXIT__0')
    monkeypatch.setattr(runner_app, 'DOCKER_COMMAND', ['wsl.exe', '--exec', 'docker'])
    monkeypatch.setattr(runner_app.subprocess, 'run', execute)
    assert runner_app._run_one(language='python', code='print("结果")', stdin='', expected='结果', test_id='unicode')['passed']
    assert captured['command'][:4] == ['wsl.exe', '--exec', 'docker', 'run']
    assert '--read-only' in captured['command'] and '--network' in captured['command']
    assert captured['kwargs']['encoding'] == 'utf-8'


def test_runner_uses_one_shot_locked_down_container(monkeypatch):
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return SimpleNamespace(
            stdout="42\n",
            stderr="\n__RUNNER_EXIT__0",
            returncode=0,
        )

    monkeypatch.setattr(runner_app.subprocess, "run", fake_run)

    result = runner_app._run_one(
        language="python",
        code="print(42)",
        stdin="",
        expected="42",
        test_id="hidden-1",
    )

    command = captured["command"]
    assert result["passed"] is True
    assert "--network" in command
    assert "--pull=never" in command
    assert command[command.index("--network") + 1] == "none"
    assert "--read-only" in command
    assert "--interactive" in command
    assert "--name" in command
    assert ["--cap-drop", "ALL"] == command[
        command.index("--cap-drop"):command.index("--cap-drop") + 2
    ]
    assert "--pids-limit" in command
    assert ["--memory", "128m"] == command[
        command.index("--memory"):command.index("--memory") + 2
    ]
    assert ["--user", "65534:65534"] == command[
        command.index("--user"):command.index("--user") + 2
    ]
    assert captured["kwargs"]["timeout"] == 5


def test_missing_engine_or_image_is_not_a_student_runtime_error(monkeypatch):
    monkeypatch.setattr(runner_app.subprocess, 'run', lambda *a, **k: SimpleNamespace(
        returncode=125, stdout='', stderr='Docker engine unavailable'))
    result = runner_app._run_one(language='python', code='print(42)', stdin='', expected='42', test_id='engine')
    assert result['failure_category'] == 'runner_unavailable'


def test_infrastructure_failure_does_not_record_a_wrong_grade(monkeypatch):
    import asyncio
    import practice_grading
    class UnavailableRunner:
        async def judge(self, **kwargs):
            return {'passed':False, 'total_count':2, 'passed_count':0, 'failure_categories':['runner_unavailable']}
    monkeypatch.setattr(practice_grading, 'code_runner_client', UnavailableRunner())
    result = asyncio.run(practice_grading.PracticeGrader().grade(
        {'revision_id':'q', 'answer_spec':{'type':'runner', 'validator_config':{'test_bundle_id':'test'}}},
        {'submitted_answer_payload':{'language':'python', 'code':'print(42)'}}))
    assert result['status'] == 'pending_review' and result['passed'] is None and result['score'] is None


def test_runner_rejects_timeout_and_output_abuse(monkeypatch):
    calls = []

    def timeout(*args, **kwargs):
        calls.append(args[0])
        if args[0][1:3] == ["rm", "--force"]:
            return SimpleNamespace(stdout="", stderr="", returncode=0)
        raise subprocess.TimeoutExpired(cmd="docker", timeout=5)

    monkeypatch.setattr(runner_app.subprocess, "run", timeout)
    timed_out = runner_app._run_one(
        language="javascript",
        code="while(true){}",
        stdin="",
        expected="",
        test_id="timeout",
    )
    assert timed_out["failure_category"] == "timeout"
    assert any(command[1:3] == ["rm", "--force"] for command in calls)

    monkeypatch.setattr(
        runner_app.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            stdout="x" * (runner_app.MAX_OUTPUT + 1),
            stderr="\n__RUNNER_EXIT__0",
            returncode=0,
        ),
    )
    too_large = runner_app._run_one(
        language="python",
        code="print('x')",
        stdin="",
        expected="",
        test_id="output",
    )
    assert too_large["failure_category"] == "output_limit"
