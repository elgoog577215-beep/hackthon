"""Ephemeral production-router host for the real-browser presentation smoke.

It uses the real presentation service/router with a temporary repository and a
fixed published course, so browser verification never mutates a user's course.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from copy import deepcopy
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi import FastAPI

from course_document import document_from_legacy_course
from presentation_generation import PresentationService
from presentation_repository import PresentationRepository
from presentation_source import project_presentation_source, source_packet
from routers.presentations import configure_presentation_service, router


COURSE_ID = "browser-course"


class _BrowserPresentationAI:
    async def _call_llm(self, prompt: str, **_kwargs) -> str:
        if prompt.lstrip().startswith("{"):
            request = json.loads(prompt)
            slide = request["slide"]
            blocks = list(slide.get("blocks") or [])
            blocks.append({
                "block_id": f"{slide['slide_id']}-browser-ai",
                "type": "callout",
                "title": "补充例子",
                "content": request.get("instruction") or "用变量地址解释指针。",
                "items": [],
                "metadata": {},
            })
            return json.dumps({"changes": {"blocks": blocks[:4]}}, ensure_ascii=False)
        layout_match = re.search(r"页面版式：(L\d{2})", prompt)
        layout = layout_match.group(1) if layout_match else "L04"
        title_match = re.search(r"标题：([^\n]+)", prompt)
        key_match = re.search(r"核心信息：([^\n]+)", prompt)
        block_type = {
            "L02": "bullets", "L04": "callout", "L05": "comparison", "L06": "bullets",
            "L07": "code", "L08": "comparison", "L09": "exercise", "L10": "bullets",
        }.get(layout)
        blocks = [] if block_type is None else [{
            "block_id": f"browser-{layout}",
            "type": block_type,
            "title": "课程要点",
            "content": "int x = 10; int *p = &x;" if block_type == "code" else "来自当前页绑定的指针课程来源。",
            "items": ["地址由 & 获取", "通过 * 解引用"] if block_type in {"bullets", "exercise"} else [],
            "metadata": {"left": "误区：空指针可直接解引用", "right": "正确：先判空再使用"} if block_type == "comparison" else {},
        }]
        return json.dumps({
            "title": title_match.group(1) if title_match else "课件页面",
            "subtitle": "",
            "key_message": key_match.group(1) if key_match else "指针保存内存地址",
            "blocks": blocks,
            "speaker_notes": "结合内存格演示地址和值的关系。",
        }, ensure_ascii=False)

    @staticmethod
    def _extract_json(response: str) -> dict:
        return json.loads(response)


def _course() -> dict:
    legacy = {
        "course_id": COURSE_ID,
        "course_name": "C语言 · 指针与内存",
        "current_course_version_id": "cv-browser-1",
        "publication_allowed": True,
        "is_published": True,
        "course_blueprint": {"positioning": "从内存模型理解指针"},
        "nodes": [
            {
                "node_id": "chapter-1",
                "parent_node_id": "root",
                "node_name": "第2章 指针",
                "node_level": 1,
                "node_content": "",
            },
            {
                "node_id": "section-1",
                "parent_node_id": "chapter-1",
                "node_name": "指针与地址",
                "node_level": 2,
                "learning_objective": "解释地址、指针和值的关系",
                "objective_id": "obj-pointer",
                "node_content": "## 指针\n\n指针变量保存另一个变量的内存地址。",
                "content_blocks": [
                    {
                        "block_id": "block-pointer",
                        "type": "concept",
                        "title": "指针定义",
                        "content": "int x = 10; int *p = &x; 指针 p 保存 x 的地址。",
                        "metadata": {},
                    },
                    {
                        "block_id": "block-deref",
                        "type": "example",
                        "title": "解引用示例",
                        "content": "*p 通过地址访问 x 的值；空指针不可直接解引用。",
                        "metadata": {},
                    },
                ],
            },
        ],
        "learning_assets": {
            "questions": [
                {"question_id": "q1", "node_id": "section-1", "prompt": "&x 表示什么？"}
            ],
            "misconceptions": [
                {
                    "misconception_id": "m1",
                    "node_id": "section-1",
                    "text": "空指针可以直接解引用",
                }
            ],
        },
    }
    document = document_from_legacy_course(legacy)
    canonical = deepcopy(legacy)
    canonical.pop("nodes")
    canonical.update(
        {
            "course_schema_version": "course_document_v1",
            "course_document_authoritative": True,
            "course_document_revision": document.document_revision,
            "course_document": document.model_dump(mode="json"),
        }
    )
    return canonical


COURSE = _course()
_temp_repository = tempfile.TemporaryDirectory(prefix="lingzhi-presentation-browser-")


def _load_course(course_id: str) -> dict:
    if course_id != COURSE_ID:
        raise KeyError(course_id)
    return deepcopy(COURSE)


repository = PresentationRepository(Path(_temp_repository.name) / "presentations")
service = PresentationService(
    repository,
    course_loader=_load_course,
    source_projector=project_presentation_source,
    source_packet_builder=source_packet,
    ai_factory=_BrowserPresentationAI,
)
configure_presentation_service(service)

app = FastAPI()
app.include_router(router, prefix="/api")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "course_id": COURSE_ID}
