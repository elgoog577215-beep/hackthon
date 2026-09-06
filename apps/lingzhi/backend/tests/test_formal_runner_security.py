from __future__ import annotations

import subprocess
from types import SimpleNamespace

from runner import app as runner_app


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
