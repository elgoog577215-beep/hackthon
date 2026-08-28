#!/usr/bin/env python3
"""Fail when backend modules import one another in a cycle.

The check reads imports without importing application code, so it is safe in CI
and does not need provider keys or local runtime data.
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys


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
    modules = backend_modules()
    groups = cyclic_groups(dependency_graph(modules))
    if groups:
        print("错误：后端核心模块出现互相导入：")
        for group in groups:
            print(f"- {' -> '.join(group)} -> {group[0]}")
        print("请把共用对象放到更基础的模块，或由上层调用方传入所需函数。")
        return 1
    print(f"后端依赖检查通过：{len(modules)} 个模块没有循环导入。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
