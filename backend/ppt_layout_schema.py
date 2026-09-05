"""Pure immutable teaching layout capability records."""
from typing import Literal
from pydantic import Field
from ppt_teaching_content import Contract

FONT_FAMILY = "Noto Sans CJK SC"
COMPILER_VERSION = "teaching_scene_v2.2"
RENDERER_VERSION = "teaching_native_v2.2"
QUALITY_VERSION = "teaching_export_v2.2"
LAYOUT_VERSION = "teaching_layout_v2.2"
PLANNER_VERSION = "teaching_planning_v2.2"


class NativeTarget(Contract):
    shape_id: int = Field(gt=0)
    group_path: list[int] = Field(default_factory=list)
    row: int | None = Field(default=None, ge=0)
    column: int | None = Field(default=None, ge=0)
    geometry_pt: tuple[float, float, float, float] | None = None


class LayoutExecution(Contract):
    capability_contract_version: Literal["teaching_layout_v2"] = "teaching_layout_v2"
    mode: Literal["native_fill", "component_render"]
    component_id: str
    component_version: str = LAYOUT_VERSION
    expression_kinds: list[str] = Field(min_length=1)
    max_subjects: int = Field(default=2, ge=2, le=4)
    max_dimensions: int = Field(default=4, ge=1, le=6)
    max_nodes: int = Field(default=8, ge=2, le=12)
    font_family: str = FONT_FAMILY
    font_sha256: str
    font_floor_pt: float = Field(default=20, ge=18)
    targets: dict[str, NativeTarget] = Field(default_factory=dict)
    source_slide_number: int = Field(default=0, ge=0)
    source_sha256: str = ""
    certification: dict = Field(default_factory=dict)

