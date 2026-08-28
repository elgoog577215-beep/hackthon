#!/usr/bin/env python3
"""Fail when backend modules import one another in a cycle.

The check reads imports without importing application code, so it is safe in CI
and does not need provider keys or local runtime data.
"""

from __future__ import annotations

import argparse
import ast
from collections import Counter
from pathlib import Path
import sys
from typing import Iterable


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"


def backend_modules() -> dict[str, Path]:
    return {path.stem: path for path in BACKEND_ROOT.glob("*.py")}


def dependency_graph(modules: dict[str, Path]) -> dict[str, set[str]]:
    graph = {name: set() for name in modules}
    for name, path in modules.items():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                target = node.module.split(".", 1)[0]
                if target in modules:
                    graph[name].add(target)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    target = alias.name.split(".", 1)[0]
                    if target in modules:
                        graph[name].add(target)
    return graph


def imported_backend_modules(
    path: Path,
    module_names: set[str],
) -> set[str]:
    """Read direct backend imports without importing application code."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    dependencies: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            target = node.module.split(".", 1)[0]
            if target in module_names:
                dependencies.add(target)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                target = alias.name.split(".", 1)[0]
                if target in module_names:
                    dependencies.add(target)
    return dependencies


def _ranked(
    values: Iterable[tuple[str, int]],
    *,
    limit: int,
) -> list[tuple[str, int]]:
    return sorted(values, key=lambda item: (-item[1], item[0]))[:limit]


def architecture_report(
    modules: dict[str, Path],
    graph: dict[str, set[str]],
    *,
    limit: int = 12,
) -> str:
    """Return a deterministic source-only architecture inventory."""
    incoming = Counter(
        dependency
        for dependencies in graph.values()
        for dependency in dependencies
    )
    line_counts = {
        name: len(path.read_text(encoding="utf-8").splitlines())
        for name, path in modules.items()
    }
    stateful_modules = {
        "storage",
        "task_manager",
        "course_repository",
        "course_versions",
        "generation_workspace",
        "learning_asset_storage",
        "material_storage",
        "question_bank",
        "teacher_lesson_repository",
    }
    route_rows: list[tuple[str, set[str], set[str]]] = []
    for path in sorted((BACKEND_ROOT / "routers").glob("*.py")):
        dependencies = imported_backend_modules(path, set(modules))
        stateful = dependencies & stateful_modules
        if stateful or len(dependencies) >= 8:
            route_rows.append((path.name, dependencies, stateful))

    lines = [
        "后端依赖报告（仅读取源码，不启动服务）",
        f"- 顶层模块：{len(modules)}",
        f"- 循环依赖组：{len(cyclic_groups(graph))}",
        "",
        "被调用最多的模块：",
    ]
    lines.extend(
        f"- {name}.py：{count} 个顶层模块直接导入"
        for name, count in _ranked(incoming.items(), limit=limit)
    )
    lines.extend(["", "直接依赖最多的模块："])
    lines.extend(
        f"- {name}.py：{count} 个顶层依赖"
        for name, count in _ranked(
            ((name, len(dependencies)) for name, dependencies in graph.items()),
            limit=limit,
        )
    )
    lines.extend(["", "行数最多的顶层模块："])
    lines.extend(
        f"- {name}.py：{count} 行"
        for name, count in _ranked(line_counts.items(), limit=limit)
    )
    lines.extend(["", "需继续检查职责的路由："])
    if not route_rows:
        lines.append("- 未发现直接导入状态对象或依赖过多的路由文件。")
    else:
        for name, dependencies, stateful in sorted(
            route_rows,
            key=lambda item: (-len(item[1]), item[0]),
        )[:limit]:
            reason = (
                "状态对象=" + ",".join(sorted(stateful))
                if stateful
                else f"直接业务依赖={len(dependencies)}"
            )
            lines.append(f"- routers/{name}：{reason}")
    return "\n".join(lines)


def cyclic_groups(graph: dict[str, set[str]]) -> list[list[str]]:
    index = 0
    indexes: dict[str, int] = {}
    low_links: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    groups: list[list[str]] = []

    def visit(module: str) -> None:
        nonlocal index
        indexes[module] = index
        low_links[module] = index
        index += 1
        stack.append(module)
        on_stack.add(module)

        for dependency in sorted(graph[module]):
            if dependency not in indexes:
                visit(dependency)
                low_links[module] = min(low_links[module], low_links[dependency])
            elif dependency in on_stack:
                low_links[module] = min(low_links[module], indexes[dependency])

        if low_links[module] != indexes[module]:
            return
        group: list[str] = []
        while True:
            member = stack.pop()
            on_stack.remove(member)
            group.append(member)
            if member == module:
                break
        if len(group) > 1:
            groups.append(sorted(group))

    for module in sorted(graph):
        if module not in indexes:
            visit(module)
    return sorted(groups)


def main() -> int:
    parser = argparse.ArgumentParser(description="检查后端模块依赖方向")
    parser.add_argument(
        "--report",
        action="store_true",
        help="同时打印调用密度、大文件和路由职责清单",
    )
    parser.add_argument("--limit", type=int, default=12)
    args = parser.parse_args()
    modules = backend_modules()
    graph = dependency_graph(modules)
    groups = cyclic_groups(graph)
    if groups:
        print("错误：后端核心模块出现互相导入：")
        for group in groups:
            print(f"- {' -> '.join(group)} -> {group[0]}")
        print("请把共用对象放到更基础的模块，或由上层调用方传入所需函数。")
        return 1
    print(f"后端依赖检查通过：{len(modules)} 个模块没有循环导入。")
    if args.report:
        print()
        print(architecture_report(
            modules,
            graph,
            limit=max(1, min(int(args.limit), 50)),
        ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
