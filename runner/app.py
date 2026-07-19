"""Internal-only isolated judge.

The API process never evaluates student source itself. It launches a fresh,
locked-down OCI container for each hidden test and returns only redacted
results. Production deployment must expose this service on a private network
and provide Docker/compatible OCI access to this service only.
"""

from __future__ import annotations

import hashlib
import hmac
import base64
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any, Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field


DATA_DIR = Path(
    os.getenv("RUNNER_DATA_DIR", "/var/lib/lingzhi-runner")
)
TOKEN = os.getenv("FORMAL_RUNNER_TOKEN", "")
MAX_OUTPUT = 32 * 1024
IMAGES = {
    "python": os.getenv(
        "RUNNER_PYTHON_IMAGE",
        "python:3.12-alpine",
    ),
    "javascript": os.getenv(
        "RUNNER_JAVASCRIPT_IMAGE",
        "node:22-alpine",
    ),
}

app = FastAPI(title="Lingzhi Formal Runner", docs_url=None)


class HiddenTest(BaseModel):
    test_id: str = Field(min_length=1, max_length=100)
    stdin: str = Field(default="", max_length=32768)
    expected_output: str = Field(max_length=32768)


class TestBundleRequest(BaseModel):
    language: Literal["python", "javascript"]
    tests: list[HiddenTest] = Field(min_length=1, max_length=100)


class JudgeRequest(BaseModel):
    task_revision_id: str = Field(min_length=1, max_length=200)
    language: Literal["python", "javascript"]
    code: str = Field(min_length=1, max_length=200000)
    test_bundle_id: str = Field(min_length=1, max_length=200)


def require_token(
    authorization: str = Header(default=""),
) -> None:
    if (
        not TOKEN
        or not authorization.startswith("Bearer ")
        or not hmac.compare_digest(
            authorization[7:],
            TOKEN,
        )
    ):
        raise HTTPException(status_code=401, detail="unauthorized")


@app.get("/internal/health", dependencies=[Depends(require_token)])
def health() -> dict[str, Any]:
    return {
        "status": "ready",
        "languages": sorted(IMAGES),
        "isolation": "one_shot_oci",
    }


@app.post(
    "/internal/test-bundles",
    dependencies=[Depends(require_token)],
)
def register_bundle(payload: TestBundleRequest) -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    raw = payload.model_dump()
    canonical = json.dumps(
        raw,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    bundle_id = f"tb_{digest[:24]}"
    target = DATA_DIR / f"{bundle_id}.json"
    if not target.exists():
        temporary = DATA_DIR / f".{bundle_id}.{uuid4().hex}.tmp"
        temporary.write_text(canonical, encoding="utf-8")
        os.replace(temporary, target)
    return {
        "test_bundle_id": bundle_id,
        "digest": f"sha256:{digest}",
        "test_count": len(payload.tests),
    }


@app.post("/internal/judge", dependencies=[Depends(require_token)])
def judge(payload: JudgeRequest) -> dict[str, Any]:
    bundle = _load_bundle(payload.test_bundle_id)
    if bundle.get("language") != payload.language:
        raise HTTPException(
            status_code=409,
            detail="test_bundle_language_mismatch",
        )
    started = time.monotonic()
    results = []
    for hidden_test in bundle.get("tests") or []:
        results.append(
            _run_one(
                language=payload.language,
                code=payload.code,
                stdin=str(hidden_test.get("stdin") or ""),
                expected=str(
                    hidden_test.get("expected_output") or ""
                ),
                test_id=str(hidden_test.get("test_id") or ""),
            )
        )
    passed_count = sum(item["passed"] for item in results)
    return {
        "status": (
            "passed"
            if passed_count == len(results)
            else "failed"
        ),
        "passed": passed_count == len(results),
        "passed_count": passed_count,
        "total_count": len(results),
        "failure_categories": sorted({
            item["failure_category"]
            for item in results
            if item["failure_category"]
        }),
        "tests": [
            {
                "test_id": item["test_id"],
                "passed": item["passed"],
                "failure_category": item["failure_category"],
            }
            for item in results
        ],
        "resource_usage": {
            "wall_time_ms": int(
                (time.monotonic() - started) * 1000
            ),
            "output_limit_bytes": MAX_OUTPUT,
            "memory_limit_mb": 128,
        },
        "output": "",
    }


def _load_bundle(bundle_id: str) -> dict[str, Any]:
    if not bundle_id.startswith("tb_"):
        raise HTTPException(status_code=404, detail="bundle_not_found")
    path = DATA_DIR / f"{bundle_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="bundle_not_found")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise HTTPException(status_code=500, detail="bundle_corrupt")
    return value


def _run_one(
    *,
    language: str,
    code: str,
    stdin: str,
    expected: str,
    test_id: str,
) -> dict[str, Any]:
    suffix = ".py" if language == "python" else ".js"
    interpreter = "python" if language == "python" else "node"
    encoded_code = base64.b64encode(
        code.encode("utf-8")
    ).decode("ascii")
    container_name = f"lingzhi-judge-{uuid4().hex}"
    docker_command = [
        "docker",
        "run",
        "--rm",
        "--interactive",
        "--name",
        container_name,
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        "32",
        "--memory",
        "128m",
        "--memory-swap",
        "128m",
        "--cpus",
        "0.5",
        "--user",
        "65534:65534",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=16m",
        "--env",
        f"USER_CODE_B64={encoded_code}",
        IMAGES[language],
        "sh",
        "-c",
        (
            f'printf %s "$USER_CODE_B64" | base64 -d '
            f">/tmp/main{suffix} || exit 97; "
            f"{interpreter} /tmp/main{suffix} "
            f">/tmp/program-output 2>&1; status=$?; "
            "head -c 32769 /tmp/program-output; "
            'printf "\\n__RUNNER_EXIT__%s" "$status" >&2'
        ),
    ]
    try:
        result = subprocess.run(
            docker_command,
            input=stdin,
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
    except subprocess.TimeoutExpired:
        _force_remove_container(container_name)
        return _test_result(test_id, False, "timeout")
    except (OSError, subprocess.SubprocessError):
        return _test_result(
            test_id,
            False,
            "runner_unavailable",
        )
    output = (result.stdout or "")[: MAX_OUTPUT + 1]
    error = (result.stderr or "")[: MAX_OUTPUT + 1]
    if len(output) > MAX_OUTPUT or len(error) > MAX_OUTPUT:
        return _test_result(test_id, False, "output_limit")
    exit_marker = "__RUNNER_EXIT__"
    student_status = None
    if exit_marker in error:
        raw_status = error.rsplit(exit_marker, 1)[-1].strip()
        try:
            student_status = int(raw_status)
        except ValueError:
            student_status = None
    if result.returncode != 0 or student_status != 0:
        return _test_result(test_id, False, "runtime_error")
    passed = output.strip() == expected.strip()
    return _test_result(
        test_id,
        passed,
        "" if passed else "wrong_answer",
    )


def _force_remove_container(container_name: str) -> None:
    try:
        subprocess.run(
            ["docker", "rm", "--force", container_name],
            text=True,
            capture_output=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        pass


def _test_result(
    test_id: str,
    passed: bool,
    failure_category: str,
) -> dict[str, Any]:
    return {
        "test_id": test_id,
        "passed": passed,
        "failure_category": failure_category,
    }
