"""运行时产品策略，集中隔离录屏专用能力。"""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Mapping


DEFAULT_DEMO_COURSE_IDS = frozenset({"demo-matrix-growth-v2"})
_TRUE_VALUES = {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class ProductRuntimePolicy:
    """描述当前进程允许启用的非标准运行能力。"""

    demo_mode_enabled: bool = False
    demo_course_ids: frozenset[str] = DEFAULT_DEMO_COURSE_IDS

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> "ProductRuntimePolicy":
        values = environment if environment is not None else os.environ
        enabled = str(values.get("EVOLUTION_DEMO_MODE") or "").strip().lower()
        configured_course_ids = values.get("EVOLUTION_DEMO_COURSE_IDS")
        if configured_course_ids is None:
            course_ids = DEFAULT_DEMO_COURSE_IDS
        else:
            course_ids = frozenset(
                item.strip()
                for item in str(configured_course_ids).split(",")
                if item.strip()
            )
        return cls(
            demo_mode_enabled=enabled in _TRUE_VALUES,
            demo_course_ids=course_ids,
        )

    def allows_demo_overrides(self, course_id: str | None) -> bool:
        normalized_course_id = str(course_id or "").strip()
        return bool(
            self.demo_mode_enabled
            and normalized_course_id
            and normalized_course_id in self.demo_course_ids
        )


def demo_overrides_enabled(course_id: str | None) -> bool:
    """只对显式列入白名单的课程启用录屏专用行为。"""
    return ProductRuntimePolicy.from_environment().allows_demo_overrides(course_id)


__all__ = [
    "DEFAULT_DEMO_COURSE_IDS",
    "ProductRuntimePolicy",
    "demo_overrides_enabled",
]
