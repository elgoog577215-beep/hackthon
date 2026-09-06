#!/usr/bin/env python3
"""真机冒烟：连续跑 N 次 8 课时课程，对照验收线。

验收线（用户定的判据）：
  * 一门 8 课时课程 **30 分钟内**跑完
  * 发布检查全过
  * **10 次里至少 9 次成功**

每次记录：总墙钟 / 逐阶段耗时 / 模型调用次数 / 发布检查是否全过 /
失败时卡在哪一阶段与错误码。

用法::

    python3 backend/tools/release_smoke.py --runs 10 --port 8050 \\
        --tree /home/ubuntu/lingzhi-dev/lz-integration

**不打印任何密钥**：只从环境读，不回显。
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ACCEPT_MINUTES = 30.0
SUBJECTS = [
    "操作系统原理", "计算机网络", "数据结构与算法", "数据库系统", "编译原理",
    "计算机组成原理", "软件工程", "人工智能导论", "线性代数", "概率论与数理统计",
]


def api(method: str, url: str, payload: dict | None = None,
        user: str = "smoke", timeout: int = 60) -> tuple[int, dict]:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("X-User-Id", user)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
            return resp.status, (json.loads(body) if body.strip() else {})
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, {"raw": body[:400]}
    except Exception as exc:  # 网络层错误也要如实记录
        return 0, {"error": f"{type(exc).__name__}: {exc}"[:300]}


def stage_breakdown(bill_dir: Path, run_tag: str) -> dict:
    """从 A-1 账单切出逐阶段耗时。流式=正文，是硬判据。"""
    records = []
    for path in bill_dir.glob("*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    if not records:
        return {}
    records.sort(key=lambda r: r.get("seq", 0))
    stream = [r for r in records if r.get("stream")]

    def span(rows):
        if not rows:
            return 0.0, 0.0
        start = min(r["elapsed_s"] - r.get("duration_ms", 0) / 1000 for r in rows)
        end = max(r["elapsed_s"] for r in rows)
        busy = sum(r.get("duration_ms", 0) for r in rows) / 1000
        return end - start, busy

    content_wall, content_busy = span(stream)
    first_stream = min((r["seq"] for r in stream), default=10**9)
    before = [r for r in records if r.get("seq", 0) < first_stream]
    # 目录 = 第一段（到第一次出现大输入之前）；其余算教案
    outline = before[:6]
    teaching = before[6:]
    o_wall, _ = span(outline)
    t_wall, _ = span(teaching)
    return {
        "calls": len(records),
        "stream_calls": len(stream),
        "outline_s": round(o_wall, 1),
        "teaching_s": round(t_wall, 1),
        "content_s": round(content_wall, 1),
        "content_parallelism": (
            round(content_busy / content_wall, 2) if content_wall else 0.0
        ),
        "truncations": sum(
            1 for r in records if "Truncated" in (r.get("retry_reason") or "")
        ),
        "call_failures": sum(
            1 for r in records if r.get("status") != "completed"
        ),
    }


def one_run(index: int, base: str, bill_root: Path, timeout_min: float) -> dict:
    subject = SUBJECTS[index % len(SUBJECTS)]
    user = f"smoke-{index}"
    bill_dir = bill_root / f"run{index:02d}"
    bill_dir.mkdir(parents=True, exist_ok=True)

    started = time.time()
    status, job = api("POST", f"{base}/api/course-generation/generate", {
        "subject": subject,
        "target_audience": "大学二年级学生",
        "difficulty": "intermediate",
        "course_type": "systematic",
        "teacher_course_brief": {
            "schema_version": "teacher_course_brief_v1",
            "target_audience": "大学二年级学生",
            "total_class_hours": 8,
            "lesson_duration_minutes": 45,
            "teaching_context": "classroom",
            "chapter_count": 4,
            "section_count": 8,
        },
    }, user=user)
    if status != 202 or "course_id" not in job:
        return {"run": index, "subject": subject, "ok": False,
                "stage": "submit", "error": str(job)[:200],
                "minutes": 0.0}

    course_id = job["course_id"]
    review = f"{base}/api/courses/{course_id}/generation/review"
    last_step = ""
    deadline = started + timeout_min * 60
    while time.time() < deadline:
        code, data = api("GET", review, user=user, timeout=30)
        state = str(data.get("status") or "")
        step = str(data.get("step") or "")
        if step:
            last_step = step
        if data.get("can_confirm") and "waiting_for_review" in state:
            api("POST",
                f"{base}/api/courses/{course_id}/generation/steps/{step}/confirm",
                {}, user=user, timeout=90)
        elif "failed" in state or "error" in state:
            break
        elif "completed" in state:
            break
        time.sleep(20)

    minutes = (time.time() - started) / 60
    code, final = api("GET", review, user=user, timeout=30)
    state = str(final.get("status") or "")
    artifact = final.get("artifact") or {}
    blocking = artifact.get("blocking_issues") or []
    asset_blocking = artifact.get("asset_blocking_issues") or []
    publishable = artifact.get("publication_allowed")

    result = {
        "run": index,
        "subject": subject,
        "course_id": course_id,
        "minutes": round(minutes, 1),
        "final_status": state,
        "stage": last_step,
        "publication_allowed": publishable,
        "blocking_issues": len(blocking),
        "asset_blocking_issues": len(asset_blocking),
        "quality_status": artifact.get("quality_status"),
    }
    result.update(stage_breakdown(bill_dir, f"run{index}"))
    # 成功判据：跑完 + 发布检查无阻塞 + 在时限内
    result["ok"] = bool(
        "completed" in state
        and not blocking
        and minutes <= ACCEPT_MINUTES
    )
    if not result["ok"]:
        reasons = []
        if "completed" not in state:
            reasons.append(f"未跑完({state or 'timeout'})@{last_step}")
        if blocking:
            reasons.append(f"发布阻塞{len(blocking)}条:{str(blocking[:1])[:120]}")
        if minutes > ACCEPT_MINUTES:
            reasons.append(f"超时{minutes:.1f}min>{ACCEPT_MINUTES}min")
        result["fail_reason"] = "; ".join(reasons)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--base", default="http://127.0.0.1:8050")
    ap.add_argument("--bill-root", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--timeout-min", type=float, default=45.0)
    args = ap.parse_args()

    results = []
    for i in range(args.runs):
        print(f"=== run {i+1}/{args.runs} ===", flush=True)
        r = one_run(i, args.base, args.bill_root, args.timeout_min)
        results.append(r)
        args.out.write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        flag = "OK " if r["ok"] else "FAIL"
        print(f"  [{flag}] {r['minutes']}min  {r.get('final_status','')} "
              f"calls={r.get('calls','?')} "
              f"{r.get('fail_reason','')}", flush=True)

    ok = [r for r in results if r["ok"]]
    mins = sorted(r["minutes"] for r in results)
    print("\n" + "=" * 60)
    print(f"成功 {len(ok)}/{len(results)}")
    if mins:
        print(f"中位耗时 {statistics.median(mins):.1f} min  "
              f"范围 {mins[0]:.1f}~{mins[-1]:.1f} min")
    print(f"30 分钟内: {sum(1 for m in mins if m <= ACCEPT_MINUTES)}/{len(mins)}")
    print(f"验收线(>=9/10 且 <=30min): "
          f"{'通过' if len(ok) >= 0.9 * len(results) else '未通过'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
