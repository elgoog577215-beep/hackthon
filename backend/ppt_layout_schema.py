"""Pure immutable teaching layout capability records."""
from typing import Literal
from pydantic import Field, model_serializer, model_validator
from ppt_teaching_content import Contract

FONT_FAMILY = "Noto Sans CJK SC"
COMPILER_VERSION = "teaching_scene_v2.4"
RENDERER_VERSION = "teaching_native_v2.3"
QUALITY_VERSION = "teaching_export_v2.4"
LAYOUT_VERSION = "teaching_layout_v2.3"
PLANNER_VERSION = "teaching_planning_v2.4"


class NativeTarget(Contract):
    kind: Literal["text", "image"] = "text"
    shape_id: int = Field(gt=0)
    group_path: list[int] = Field(default_factory=list)
    row: int | None = Field(default=None, ge=0)
    column: int | None = Field(default=None, ge=0)
    geometry_pt: tuple[float, float, float, float] | None = None

    @model_serializer(mode="wrap")
    def serialize(self, handler):
        value = handler(self)
        if self.kind == "text":
            value.pop("kind", None)
        return value


class NativeConnection(Contract):
    shape_id: int = Field(gt=0)
    source_slot: str
    target_slot: str
    start_site: int = Field(ge=0, le=3)
    end_site: int = Field(ge=0, le=3)
    geometry_pt: tuple[float, float, float, float]
    directed: bool
    label_slot: str = ""


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
    connections: dict[str, NativeConnection] = Field(default_factory=dict)
    static_artwork_data: str = Field(default="", max_length=8_000_000)
    static_artwork_sha256: str = ""
    source_slide_number: int = Field(default=0, ge=0)
    source_sha256: str = ""
    certification: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def verify_artwork(self):
        if self.static_artwork_data or self.static_artwork_sha256:
            import base64
            import hashlib
            data = base64.b64decode(self.static_artwork_data, validate=True)
            if not data.startswith(b'\x89PNG\r\n\x1a\n') or hashlib.sha256(data).hexdigest() != self.static_artwork_sha256:
                raise ValueError('native_artwork_digest_mismatch')
        return self

    @model_serializer(mode="wrap")
    def serialize(self, handler):
        value = handler(self)
        for key in ("connections", "static_artwork_data", "static_artwork_sha256"):
            if not value.get(key):
                value.pop(key, None)
        return value
