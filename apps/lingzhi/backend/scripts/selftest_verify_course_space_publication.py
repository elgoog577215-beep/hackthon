#!/usr/bin/env python3
"""用本机 fixture 服务空跑一遍验收脚本，确认它真的会判对也会判错。

**不碰共享端点、不生成课程。** 目的：验收脚本本身是代码，只在真机上第一次运行
等于未经测试——这里先用可控的假后端把「全过」和「该失败时确实失败」两条路都走一遍。
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

SCRIPT = str(__import__("pathlib").Path(__file__).with_name("verify_course_space_publication.py"))
COURSE = "course-smoke-1"
PKG = "tcs-fixture-1"

ASSETS = [
    {"asset_id": "a1", "relative_path": "0、教学大纲/AI 生成/微积分-课程大纲.md",
     "origin": "course_generation", "size_bytes": 100},
    {"asset_id": "a2", "relative_path": "1、教案/AI 生成/微积分-全课教案.md",
     "origin": "course_generation", "size_bytes": 200},
    {"asset_id": "a3", "relative_path": "1、教案/AI 生成/第1章 极限/1.1 函数极限.md",
     "origin": "course_generation", "size_bytes": 300},
]


def make_handler(scenario: str):
    state = {"publish_calls": 0}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # 静音
            pass

        def _send(self, payload, status=200, raw=False):
            body = payload if raw else json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/api/tasks":
                self._send([{
                    "type": "course_generation", "status": "completed",
                    "course_id": COURSE,
                    "course_space_publication": {"status": "completed", "written": ASSETS},
                }])
            elif path == "/api/teacher-course-spaces":
                packages = [{"package_id": PKG, "course_id": COURSE,
                             "course_name": "微积分", "asset_count": len(ASSETS)}]
                if scenario == "duplicate_package":
                    packages.append({"package_id": "tcs-fixture-2", "course_id": COURSE,
                                     "course_name": "微积分", "asset_count": 3})
                self._send(packages)
            elif path == f"/api/teacher-course-spaces/{PKG}":
                assets = list(ASSETS)
                if scenario == "grew" and state["publish_calls"] >= 2:
                    assets = assets + [{"asset_id": "a4",
                                        "relative_path": "1、教案/AI 生成/重复.md",
                                        "origin": "course_generation", "size_bytes": 10}]
                if scenario == "bad_layout":
                    assets = [{**ASSETS[0], "relative_path": "随手放的目录/大纲.md"}]
                self._send({"package_id": PKG, "assets": assets})
            elif "/download" in path:
                if state.get("manual_uploaded") and "/a1/" in path:
                    body = ("老师手写的内容-请勿覆盖-F2VERIFY\n"
                            if scenario != "silent_overwrite"
                            else "# 被生成产物覆盖了\n")
                    self._send(body.encode("utf-8"), raw=True)
                    return
                self._send("# 微积分｜课程大纲\n\n## 覆盖范围说明\n- 本次不覆盖：中值定理\n"
                           .encode("utf-8"), raw=True)
            else:
                self._send({}, status=404)

        def do_POST(self):
            if self.path.endswith("/imports"):
                length = int(self.headers.get("Content-Length") or 0)
                self.rfile.read(length)
                state["manual_uploaded"] = True
                self._send({"batch_id": "b1", "outcomes": []})
                return
            if path_is_publish(self.path):
                state["publish_calls"] += 1
                first = state["publish_calls"] == 1
                written = [a["relative_path"] for a in ASSETS] if first else []
                unchanged = [] if first else [a["relative_path"] for a in ASSETS]
                if state.get("manual_uploaded"):
                    conflicts = ([] if scenario == "silent_overwrite"
                                 else [{"relative_path": ASSETS[0]["relative_path"],
                                        "reason": "manual_upload_present"}])
                    written = ([ASSETS[0]["relative_path"]]
                               if scenario == "silent_overwrite" else [])
                    self._send({"status": "completed", "package_id": PKG,
                                "written": written,
                                "unchanged": [a["relative_path"] for a in ASSETS[1:]],
                                "conflicts": conflicts, "failures": []})
                    return
                if scenario == "rewrites" and not first:
                    written = [ASSETS[0]["relative_path"]]
                    unchanged = [a["relative_path"] for a in ASSETS[1:]]
                self._send({
                    "status": "completed", "package_id": PKG,
                    "written": written, "unchanged": unchanged,
                    "conflicts": [], "failures": [],
                })
            else:
                self._send({}, status=404)

    return Handler


def path_is_publish(path: str) -> bool:
    return path.endswith("/course-space/publish")


def run(scenario: str, port: int) -> int:
    server = HTTPServer(("127.0.0.1", port), make_handler(scenario))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = subprocess.run(
            [sys.executable, SCRIPT, "--base", f"http://127.0.0.1:{port}",
             "--teacher", "teacher-fixture"],
            capture_output=True, text=True, timeout=60,
        )
        return result.returncode, result.stdout
    finally:
        server.shutdown()


if __name__ == "__main__":
    cases = [
        ("happy", 0, "三条全过"),
        ("duplicate_package", 1, "重跑产生了第二个包 —— 必须判失败"),
        ("grew", 1, "资产条目增长 —— 必须判失败"),
        ("rewrites", 1, "重跑重复写入 —— 必须判失败"),
        ("bad_layout", 1, "层级不对 —— 必须判失败"),
        ("silent_overwrite", 1, "静默覆盖了老师手动上传 —— 必须判失败"),
    ]
    port = 9310
    ok = True
    for scenario, expected, label in cases:
        code, out = run(scenario, port)
        port += 1
        mark = "OK " if code == expected else "BAD"
        if code != expected:
            ok = False
        print(f"[{mark}] {scenario:<18} 退出码={code}（期望 {expected}）— {label}")
        if code != expected:
            print(out[-1200:])
    print()
    print("脚本自检通过：该过的过、该失败的失败。" if ok else "脚本自检未通过。")
    sys.exit(0 if ok else 1)
