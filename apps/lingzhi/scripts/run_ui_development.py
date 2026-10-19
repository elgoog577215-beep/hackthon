"""Run independent teacher/student development services on loopback.

No accounts are created. Each backend uses its own repository-external data.
Credentials are read from the existing private .env into process environments.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request

from dotenv import dotenv_values
from configure_zju_qwen_provider import REMOVED_TEXT_SETTINGS

APP = Path(__file__).resolve().parents[1]
REPOSITORY = APP.parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--teacher-port", type=int, default=5173)
    parser.add_argument("--student-port", type=int, default=5174)
    parser.add_argument("--teacher-api-port", type=int, default=8000)
    parser.add_argument("--student-api-port", type=int, default=8001)
    args = parser.parse_args()
    state = args.state_dir.expanduser().resolve()
    if state == REPOSITORY or REPOSITORY in state.parents or state in REPOSITORY.parents:
        parser.error("Development state must be outside the repository and its parent directories")
    ports = [args.teacher_port, args.student_port, args.teacher_api_port, args.student_api_port]
    if len(set(ports)) != 4 or any(not 1024 <= port <= 65535 for port in ports):
        parser.error("Four distinct local ports between 1024 and 65535 are required")
    npm = shutil.which("npm")
    if not npm:
        parser.error("npm is required")
    # Check before starting anything; never terminate an existing service.
    for port in ports:
        with socket.socket() as handle:
            try:
                handle.bind(("127.0.0.1", port))
            except OSError:
                parser.error(f"Port {port} is occupied; existing services were left untouched")
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    environment = {
        **os.environ,
        **{key: value for key, value in dotenv_values(APP / ".env").items() if value is not None},
    }
    environment.update(
        {
            "QIZHI_AUTH_VERIFY_URL": "",
            "LINGZHI_LOCAL_STUDY_AUTH": "false",
            "LINGZHI_RUNTIME_MODE": "development",
            "GIT_AUTO_SYNC_ENABLED": "false",
            "VITE_QIZHI_AUTH_REQUIRED": "false",
        }
    )
    # Old private env files may still contain retired provider settings. Empty
    # them in the child processes so dotenv cannot reintroduce a text fallback.
    environment.update({key: "" for key in REMOVED_TEXT_SETTINGS})
    token = secrets.token_urlsafe(40)
    children: list[subprocess.Popen] = []
    logs = []

    def stop(*_args):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        for surface, api_port, peer_port, ui_port, peer_ui in (
            ("teacher", args.teacher_api_port, args.student_api_port, args.teacher_port, args.student_port),
            ("student", args.student_api_port, args.teacher_api_port, args.student_port, args.teacher_port),
        ):
            data = state / f"{surface}-data"
            data.mkdir(exist_ok=True, mode=0o700)
            env = {
                **environment,
                "LINGZHI_DATA_DIR": str(data),
                "LINGZHI_DEV_SURFACE": surface,
                "LINGZHI_EXCHANGE_ROLE": surface,
                "LINGZHI_EXCHANGE_NODE_ID": f"development-{surface}",
                "LINGZHI_EXCHANGE_PEER_ID": f"development-{'student' if surface == 'teacher' else 'teacher'}",
                "LINGZHI_EXCHANGE_PEER_URL": f"http://127.0.0.1:{peer_port}",
                "LINGZHI_EXCHANGE_TOKEN": token,
                "VITE_APP_SURFACE": surface,
                "VITE_API_PROXY_TARGET": f"http://127.0.0.1:{api_port}",
                "VITE_API_BASE_URL": "",
                "VITE_BASE_PATH": "/",
                "VITE_LEARNER_USER_ID": "local-student:development",
                "VITE_TEACHER_USER_ID": "development-teacher",
                "VITE_STUDY_APP_URL": f"http://127.0.0.1:{peer_ui}/study" if surface == "teacher" else "",
            }
            for kind, command, cwd in (
                (
                    "api",
                    [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(api_port)],
                    APP / "backend",
                ),
                (
                    "ui",
                    [npm, "run", "dev", "--", "--host", "127.0.0.1", "--port", str(ui_port), "--strictPort"],
                    APP / "frontend",
                ),
            ):
                path = state / f"{surface}-{kind}.log"
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
                output = os.fdopen(descriptor, "a")
                logs.append(output)
                children.append(
                    subprocess.Popen(
                        command, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT, start_new_session=True
                    )
                )
        deadline = time.monotonic() + 45
        pending = {f"http://127.0.0.1:{port}/health" for port in (args.teacher_api_port, args.student_api_port)}
        while pending and time.monotonic() < deadline:
            if any(process.poll() is not None for process in children):
                raise RuntimeError("A development process exited; inspect the private state directory logs")
            for url in list(pending):
                try:
                    with urllib.request.urlopen(url, timeout=1) as response:
                        if response.status == 200:
                            pending.remove(url)
                except OSError:
                    pass
            time.sleep(0.25)
        if pending:
            raise RuntimeError("Development API startup timed out; inspect the private state directory logs")
        print(f"教师端：http://127.0.0.1:{args.teacher_port}/courses", flush=True)
        print(f"学生端：http://127.0.0.1:{args.student_port}/study", flush=True)
        print("本机开发模式；无需账号密码；教师与学生数据独立。", flush=True)
        while all(process.poll() is None for process in children):
            time.sleep(1)
        raise RuntimeError("A development process exited; inspect the private state directory logs")
    except KeyboardInterrupt:
        pass
    finally:
        for process in children:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
        for process in children:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        for output in logs:
            output.close()


if __name__ == "__main__":
    main()
