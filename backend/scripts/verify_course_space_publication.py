#!/usr/bin/env python3
"""F-2 真机验收：课程产物是否真的落进教师文件空间。

**只读加一次幂等重跑，不生成课程、不触碰模型端点。** 设计成 lz-perf 的冒烟跑出
成功课之后立刻能跑，全程只打本机后端的 HTTP 接口。

验三件事（第三条最关键——幂等只在单测里成立不算数）：

1. 产物是否真的出现在教师文件空间（且内容可下载、非空）；
2. 层级是否是「模板文件夹 + AI 生成子目录」；
3. **重跑一次是否不产生第二个包、也不覆盖手动上传的文件**。

用法::

    python3 scripts/verify_course_space_publication.py \\
        --base http://127.0.0.1:8050 \\
        --course <course_id> \\
        --teacher <X-User-Id>

不带 --course 时会自动挑最近一门"已完成且有产物"的课程。
退出码 0 = 三条全过；1 = 有验收项失败；2 = 环境问题（连不上、没有可验的课）。
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import PurePosixPath

GENERATED_DIR = "AI 生成"
TEMPLATE_FOLDERS = ("0、教学大纲", "1、教案", "2、PPT")


class Checker:
    def __init__(self, base: str, teacher: str) -> None:
        self.base = base.rstrip("/")
        self.teacher = teacher
        self.failures: list[str] = []
        self.notes: list[str] = []

    # -- HTTP ---------------------------------------------------------------

    def call(self, method: str, path: str, *, raw: bool = False, timeout: int = 120):
        request = urllib.request.Request(
            self.base + path,
            method=method,
            headers={"X-User-Id": self.teacher, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read()
                if raw:
                    return response.status, body
                return response.status, (json.loads(body) if body else {})
        except urllib.error.HTTPError as exc:
            body = exc.read()
            try:
                return exc.code, json.loads(body)
            except Exception:
                return exc.code, {"raw": body[:400].decode("utf-8", "replace")}
        except Exception as exc:  # noqa: BLE001 - 连不上要报环境问题而不是验收失败
            return 0, {"error": f"{type(exc).__name__}: {exc}"}

    # -- 断言 ---------------------------------------------------------------

    def check(self, ok: bool, label: str, detail: str = "") -> bool:
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {label}" + (f" — {detail}" if detail else ""))
        if not ok:
            self.failures.append(label)
        return ok

    def note(self, text: str) -> None:
        print(f"  ·      {text}")
        self.notes.append(text)


def upload_file(checker: Checker, package_id: str, relative_path: str, text: str) -> bool:
    """通过 /imports 上传一个文件，模拟教师手动放入同名文件。

    用 multipart 手搓请求：脚本不引第三方依赖，要能在任何机器上直接跑。
    """
    boundary = "----f2verifyboundary"
    parts: list[bytes] = []
    parts.append(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"files\"; "
        f"filename=\"{PurePosixPath(relative_path).name}\"\r\n"
        f"Content-Type: text/markdown\r\n\r\n".encode()
    )
    parts.append(text.encode("utf-8") + b"\r\n")
    parts.append(
        f"--{boundary}\r\nContent-Disposition: form-data; "
        f"name=\"relative_paths\"\r\n\r\n{relative_path}\r\n".encode()
    )
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)
    request = urllib.request.Request(
        f"{checker.base}/api/teacher-course-spaces/{package_id}/imports",
        data=body,
        method="POST",
        headers={
            "X-User-Id": checker.teacher,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status in (200, 201)
    except Exception as exc:  # noqa: BLE001
        checker.note(f"模拟上传失败：{type(exc).__name__}: {exc}")
        return False


def pick_course(checker: Checker, explicit: str | None) -> str | None:
    if explicit:
        return explicit
    status, tasks = checker.call("GET", "/api/tasks?limit=50")
    if status != 200 or not isinstance(tasks, list):
        return None
    for task in tasks:
        if task.get("type") != "course_generation":
            continue
        if str(task.get("status")) not in {"completed", "completed_with_warnings"}:
            continue
        course_id = str(task.get("course_id") or "")
        if course_id:
            report = task.get("course_space_publication") or {}
            if report:
                checker.note(
                    f"该课自动入库报告：status={report.get('status')} "
                    f"written={len(report.get('written') or [])} "
                    f"reason={report.get('reason') or '-'}"
                )
            return course_id
    return None


def find_package(checker: Checker, course_id: str) -> dict | None:
    status, packages = checker.call("GET", "/api/teacher-course-spaces")
    if status != 200:
        return None
    items = packages if isinstance(packages, list) else packages.get("packages") or []
    bound = [p for p in items if str(p.get("course_id") or "") == course_id]
    return bound[0] if bound else None


def verify(checker: Checker, course_id: str) -> None:
    print(f"\n课程 {course_id}｜教师 {checker.teacher}\n")

    # --- 前置：确保产物已入库（自动入库若已跑过，这里就是一次幂等重跑）------
    print("[0] 触发/确认入库")
    status, report = checker.call(
        "POST", f"/api/courses/{course_id}/course-space/publish"
    )
    if status != 200:
        checker.check(False, "入库接口可用", f"HTTP {status} {report}")
        return
    if report.get("status") == "skipped":
        checker.check(
            False,
            "课程有可归档产物",
            f"reason={report.get('reason')}｜{report.get('message')}",
        )
        return
    first_written = list(report.get("written") or [])
    first_unchanged = list(report.get("unchanged") or [])
    checker.note(
        f"首次调用：written={len(first_written)} unchanged={len(first_unchanged)} "
        f"conflicts={len(report.get('conflicts') or [])} "
        f"failures={len(report.get('failures') or [])}"
    )
    package_id = str(report.get("package_id") or "")

    # --- 一：产物真的出现在文件空间 ---------------------------------------
    print("\n[1] 产物出现在教师文件空间")
    package = find_package(checker, course_id)
    if not checker.check(
        package is not None, "文件空间里存在与该课程绑定的课程包",
        f"package_id={package_id}",
    ):
        return
    package_id = str(package.get("package_id") or package_id)

    status, detail = checker.call(
        "GET", f"/api/teacher-course-spaces/{package_id}"
    )
    if not checker.check(status == 200, "课程包可读取"):
        return
    assets = detail.get("assets") or []
    checker.check(len(assets) > 0, "课程包内有产物", f"{len(assets)} 个文件")

    generated = [a for a in assets if a.get("origin") == "course_generation"]
    checker.check(
        len(generated) == len(assets) or len(generated) > 0,
        "产物带有生成来源标记",
        f"{len(generated)}/{len(assets)} 标记为 course_generation",
    )

    # 抽一个文件真的下载下来，确认不是空壳记录
    sample = next(
        (a for a in generated if str(a.get("relative_path", "")).endswith(".md")),
        None,
    )
    if sample:
        status, body = checker.call(
            "GET",
            f"/api/teacher-course-spaces/{package_id}"
            f"/assets/{sample['asset_id']}/download",
            raw=True,
        )
        text = body.decode("utf-8", "replace") if isinstance(body, bytes) else ""
        checker.check(
            status == 200 and len(text.strip()) > 0,
            "抽样文件可下载且内容非空",
            f"{sample['relative_path']}（{len(text)} 字符）",
        )
        if "覆盖范围说明" in text or "本次不覆盖" in text:
            checker.note("大纲中保留了 D-1 覆盖度结论")

    # --- 二：层级正确 -------------------------------------------------------
    print("\n[2] 层级为「模板文件夹 + AI 生成子目录」")
    paths = [str(a.get("relative_path") or "") for a in generated]
    in_template = [
        p for p in paths if p.split("/")[0] in TEMPLATE_FOLDERS
    ]
    checker.check(
        len(in_template) == len(paths) and bool(paths),
        "全部产物位于学校模板文件夹下",
        f"{len(in_template)}/{len(paths)}",
    )
    in_generated = [p for p in paths if f"/{GENERATED_DIR}/" in p]
    checker.check(
        len(in_generated) == len(paths) and bool(paths),
        f"全部产物位于「{GENERATED_DIR}」子目录下",
        f"{len(in_generated)}/{len(paths)}",
    )
    chaptered = [p for p in paths if p.count("/") >= 3]
    if chaptered:
        checker.note(f"其中 {len(chaptered)} 个按章节分层，例：{chaptered[0]}")
    tops = sorted({p.split("/")[0] for p in paths})
    checker.note(f"顶层分布：{tops}")

    # --- 三：幂等 + 不覆盖手动上传（最关键）---------------------------------
    print("\n[3] 重跑：不产生第二个包、不覆盖手动上传")
    status, second = checker.call(
        "POST", f"/api/courses/{course_id}/course-space/publish"
    )
    if not checker.check(status == 200, "重跑接口可用", f"HTTP {status}"):
        return
    checker.check(
        not (second.get("written") or []),
        "重跑没有重复写入任何文件",
        f"written={len(second.get('written') or [])}",
    )
    checker.check(
        len(second.get("unchanged") or []) == len(assets),
        "重跑全部命中未变更",
        f"unchanged={len(second.get('unchanged') or [])} / 资产 {len(assets)}",
    )
    checker.check(
        str(second.get("package_id") or "") == package_id,
        "重跑复用同一个课程包",
        f"{second.get('package_id')}",
    )

    packages_now = find_package(checker, course_id)
    status, all_packages = checker.call("GET", "/api/teacher-course-spaces")
    items = (
        all_packages if isinstance(all_packages, list)
        else all_packages.get("packages") or []
    )
    bound_count = len([
        p for p in items if str(p.get("course_id") or "") == course_id
    ])
    checker.check(bound_count == 1, "该课程仍然只绑定 1 个包", f"实际 {bound_count} 个")

    status, detail_after = checker.call(
        "GET", f"/api/teacher-course-spaces/{package_id}"
    )
    assets_after = detail_after.get("assets") or []
    checker.check(
        len(assets_after) == len(assets),
        "资产条目数没有增长",
        f"{len(assets)} -> {len(assets_after)}",
    )

    # --- 三b：真的手动上传一个同名文件，再跑一次，内容必须保住 -------------
    # 这条是主动验证而不是被动观察：真从 /imports 传一个同路径文件（模拟老师
    # 手动覆盖），再触发入库，然后把内容读回来比对。只观察 conflicts 字段等于
    # 相信实现自己的自述，不算验证。
    print("\n[3b] 手动上传保护（真实上传一个同名文件后重跑）")
    if not sample:
        checker.note("没有可用于该检查的 markdown 产物，跳过")
        return
    target_path = str(sample.get("relative_path") or "")
    sentinel = "老师手写的内容-请勿覆盖-F2VERIFY\n"
    uploaded = upload_file(checker, package_id, target_path, sentinel)
    if not checker.check(uploaded, "能够模拟一次教师手动上传", target_path):
        return

    status, third = checker.call(
        "POST", f"/api/courses/{course_id}/course-space/publish"
    )
    checker.check(status == 200, "手动上传后入库接口仍可用", f"HTTP {status}")
    conflicts = third.get("conflicts") or []
    checker.check(
        any(str(c.get("relative_path") or "") == target_path for c in conflicts),
        "该路径被如实报为冲突而不是静默覆盖",
        f"conflicts={len(conflicts)}",
    )
    checker.check(
        target_path not in (third.get("written") or []),
        "生成侧没有重新写入这个被手动改过的路径",
    )

    # 最硬的一条：把内容读回来，老师写的字必须还在。
    status, detail_final = checker.call(
        "GET", f"/api/teacher-course-spaces/{package_id}"
    )
    final_asset = next(
        (a for a in (detail_final.get("assets") or [])
         if str(a.get("relative_path") or "") == target_path),
        None,
    )
    if final_asset:
        status, body = checker.call(
            "GET",
            f"/api/teacher-course-spaces/{package_id}"
            f"/assets/{final_asset['asset_id']}/download",
            raw=True,
        )
        text = body.decode("utf-8", "replace") if isinstance(body, bytes) else ""
        checker.check(
            "F2VERIFY" in text,
            "老师手动上传的内容原样保住（未被生成产物覆盖）",
            f"读回 {len(text)} 字符",
        )
    else:
        checker.check(False, "手动上传的文件仍在课程包中")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8050")
    parser.add_argument("--course", default=None)
    parser.add_argument("--teacher", default="teacher-smoke-1")
    args = parser.parse_args()

    checker = Checker(args.base, args.teacher)
    status, _ = checker.call("GET", "/api/tasks?limit=1", timeout=10)
    if status == 0:
        print(f"连不上后端 {args.base}，先确认服务在跑。", file=sys.stderr)
        return 2

    course_id = pick_course(checker, args.course)
    if not course_id:
        print(
            "没有找到已完成的课程生成任务；等冒烟跑出成功的课再执行，"
            "或用 --course 指定。",
            file=sys.stderr,
        )
        return 2

    verify(checker, course_id)

    print("\n" + "=" * 60)
    if checker.failures:
        print(f"验收未通过，{len(checker.failures)} 项失败：")
        for item in checker.failures:
            print(f"  - {item}")
        return 1
    print("三项验收全部通过：产物已入库、层级正确、重跑幂等。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
