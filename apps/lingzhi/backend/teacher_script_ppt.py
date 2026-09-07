"""Joint handout/page generation and deterministic lowering into the V6 manuscript."""
from __future__ import annotations

import inspect
import json
from copy import deepcopy
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic_core import from_json

from course_document import CourseBlock, CourseDocument, CourseSection, stable_hash
from course_presentation_graph import block_source_text, compile_course_presentation_graph
from ppt_fixed_draft import form_type, lower_fixed_response
from ppt_fixed_templates import compile_fixed_template, fixed_capabilities, fixed_slug
from ppt_teaching_manuscript import compile_teaching_manuscript, refresh_manuscript
from ppt_teaching_planner import normalize_page_response
from teacher_script import normalize_teacher_script_section, validate_teacher_script_section

CONTRACT = "script_ppt_bundle_v1"
DEFAULT_THEME = "qizhi-classroom"


class BundleBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    block_id: str
    content: str = Field(min_length=1)
    # Individual page validation must not discard an otherwise valid handout.
    pages: Any = Field(default_factory=list)


class ScriptPptBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blocks: list[BundleBlock] = Field(min_length=1)


def generation_contract(template):
    forms = {}
    for layout in template.layouts:
        slug = fixed_slug(layout.template_layout_id)
        if slug == "figure":
            continue  # Images are available only after explicit asset adoption.
        forms[layout.template_layout_id] = form_type(slug, authored=True).model_json_schema()
    return {
        "schema_version": CONTRACT,
        "response": ScriptPptBundle.model_json_schema(),
        "page": {"layout_id": "one of forms", "page_goal": "本页实际教学目的", "fields": "对应版式表单"},
        "forms": forms,
        "capabilities": fixed_capabilities(template),
    }


def lower_bundle_pages(document, template, blocks):
    graph = compile_course_presentation_graph(document, teaching_plan={})
    sources = {b.block_id: {"block_id": b.block_id, "block_revision": b.internal_revision,
                           "full_text": block_source_text(b)} for b in document.blocks}
    owners = {b: unit.teaching_unit_id for unit in graph.units for b in unit.primary_block_ids}
    planned = []
    for block in blocks:
        block_id = block["block_id"]
        if not block.get("ppt_pages"):
            raise ValueError(f"script_ppt_pages_missing:{block_id}")
        for index, raw in enumerate(block["ppt_pages"]):
            if not isinstance(raw, dict) or set(raw) != {"layout_id", "page_goal", "fields"}:
                raise ValueError(f"script_ppt_page_fields_invalid:{block_id}:{index}")
            layout = template.get_layout(raw["layout_id"])
            if layout is None or not str(raw["page_goal"]).strip():
                raise ValueError(f"script_ppt_layout_invalid:{block_id}:{index}")
            lowered = lower_fixed_response(raw["fields"], raw)
            normalized = normalize_page_response(lowered, {block_id: sources[block_id]})
            planned.append({**normalized, "page_id": f"{block_id}:ppt:{index + 1}",
                            "teaching_unit_id": owners[block_id], "source_block_ids": [block_id]})
    return graph, planned


def validate_block_pages(block, template):
    """Use the real source, field, relationship and font-capacity gates per block."""
    bid = block["block_id"]
    document = CourseDocument(course_id="script-ppt-validation", title=block.get("title") or "讲义",
        document_revision=stable_hash(block["content"], prefix="script_"),
        sections=[CourseSection(section_id="section", title="讲义", position=0)],
        blocks=[CourseBlock(block_id=bid, section_id="section", position=0,
                           payload={"markdown": block["content"]}, internal_revision=stable_hash(block["content"], prefix="block_"))])
    graph, planned = lower_bundle_pages(document, template, [block])
    compile_teaching_manuscript(document, graph, template, {}, planned)


async def _notify(callback, *args):
    if callback:
        result = callback(*args)
        if inspect.isawaitable(result):
            await result


async def generate_bundle(*, invoke, contract, instructions, template, on_delta=None,
                          on_reset=None, on_checkpoint=None, seed_blocks=None, immutable_handout=False):
    modules = contract["modules"]
    expected = [m["block_id"] for m in modules]
    checkpoint = deepcopy(seed_blocks or {})
    blocks = {}
    for module in modules:
        seed = checkpoint.get(module["block_id"])
        if seed and (immutable_handout or validate_teacher_script_section(
            {"blocks": [seed]}, {**contract, "modules": [module]}
        ).get("passed")):
            blocks[module["block_id"]] = seed
    if immutable_handout and set(blocks) != set(expected):
        raise ValueError("script_ppt_frozen_handout_missing")
    forms = generation_contract(template)
    joint_instruction = (
        instructions.replace("只输出完整 Markdown 正文", "正文保持完整 Markdown")
        + "\n最终只输出 JSON，格式以下方 response 为准，不在 JSON 外写正文。每个 block 同时包含 content 和 pages。"
        "content 按前述要求编写完整讲义正文，不含本环节的二级标题；pages 同时组织本环节的课堂展示，"
        "每页只有 layout_id、page_goal、fields。页面必须有具体内容，覆盖必要条件、定义、推导、例题及答案；"
        "不同页各有目的，不能重复同一句摘要。不要为每个环节重复封面或目录。"
        "fields 使用选中版式的表单；来源填写 sources=[{block_id:本环节ID,quote:本次content中的连续原文}]。"
        "公式、代码、数据与引文必须引用精确原文，保留公式定界符、代码换行与缩进。"
        "页数根据内容和容量确定，不能裁掉条件或答案；问答版式只用于真实练习。"
        "只使用当前请求列出的 block_id，按既定顺序返回。不要输出布局代码或位置字号。\n"
        + json.dumps(forms, ensure_ascii=False)
        + "\n教学环节身份：" + json.dumps([{k: m.get(k) for k in ("block_id", "title", "role")} for m in modules], ensure_ascii=False)
    )
    buffer, visible = "", ""

    async def reset():
        nonlocal buffer, visible
        buffer, visible = "", ""
        await _notify(on_reset)

    async def stream(delta):
        nonlocal buffer, visible
        buffer += delta
        try:
            value = from_json(buffer, allow_partial="trailing-strings")
        except ValueError:
            return
        if not isinstance(value, dict) or not isinstance(value.get("blocks", []), list):
            return
        titles = {m["block_id"]: m["title"] for m in modules}
        text = "\n\n".join(f"## {titles[b['block_id']]}\n{b.get('content', '')}" for b in value.get("blocks", [])
                           if isinstance(b, dict) and b.get("block_id") in titles)
        if text.startswith(visible):
            await _notify(on_delta, text[len(visible):])
        elif text:
            await _notify(on_reset)
            await _notify(on_delta, text)
        visible = text

    errors = []
    for attempt in range(3):
        missing = [bid for bid in expected if bid not in blocks]
        if not missing:
            break
        raw = await invoke("请同时完成讲义正文与对应 PPT 页面。", joint_instruction
            + "\n本次仅返回这些环节：" + json.dumps(missing, ensure_ascii=False)
            + "\n待修复问题：" + json.dumps(errors, ensure_ascii=False),
            output_tokens=min(16000, max(2000, sum(int(m.get("max_characters") or 900) * 2 for m in modules))),
            stream_delta=stream, stream_reset=reset)
        try:
            response = ScriptPptBundle.model_validate_json(raw or "")
            ids = [b.block_id for b in response.blocks]
            if len(set(ids)) != len(ids) or set(ids) != set(missing):
                raise ValueError("script_ppt_block_identity_mismatch")
        except ValueError as error:
            errors = [str(error)]
            continue
        errors = []
        for item in response.blocks:
            module = next(m for m in modules if m["block_id"] == item.block_id)
            candidate = {**deepcopy(module), "content": item.content.strip(), "ppt_pages": item.pages if isinstance(item.pages, list) else [item.pages],
                         "generation_contract_version": CONTRACT}
            quality = validate_teacher_script_section({"blocks": [candidate]}, {**contract, "modules": [module]})
            if not quality.get("passed"):
                errors.extend(quality.get("blocking_issues") or [])
                continue
            blocks[item.block_id] = candidate
            await _notify(on_checkpoint, deepcopy(candidate))
    if set(blocks) != set(expected):
        from ai_base import AIProviderRequestError
        raise AIProviderRequestError("讲义未通过当前教案的质量检查：" + json.dumps(errors, ensure_ascii=False))

    # Repairs own only failing page fields; accepted text and pages are immutable inputs.
    for bid in expected:
        block = blocks[bid]
        page_errors = []
        pages = deepcopy(block.get("ppt_pages") or [])
        groups = deepcopy(block.get("ppt_page_groups") or [[p] for p in pages] or [[]])
        attempts = list(block.get("ppt_repair_attempts") or [0] * len(groups))
        if len(attempts) != len(groups):
            raise ValueError("script_ppt_checkpoint_invalid")
        for index, group in enumerate(groups):
            candidate_pages = group
            while True:
                try:
                    validate_block_pages({**block, "ppt_pages": candidate_pages}, template)
                    break
                except (ValueError, RuntimeError, KeyError) as error:
                    detail = str(error)
                    if attempts[index] >= 2:
                        page_errors.append({"block_id": bid, "page_index": index, "message": detail})
                        break
                    try:
                        attempts[index] += 1
                        block.update(ppt_page_groups=groups, ppt_repair_attempts=attempts)
                        await _notify(on_checkpoint, deepcopy(block))
                        raw = await invoke("修复当前 PPT 页面，只返回 {\"pages\":[...]}，必要时拆分本页。",
                            joint_instruction + "\n讲义正文固定，不得改写：" + json.dumps({"block_id": bid, "content": block["content"]}, ensure_ascii=False)
                            + "\n只修以下失败页面，保留其他页：" + json.dumps(candidate_pages, ensure_ascii=False)
                            + "\n错误：" + detail, output_tokens=6000, stream_delta=None, stream_reset=None)
                        value = json.loads(raw or "")
                        if not isinstance(value.get("pages"), list):
                            raise ValueError("script_ppt_repair_invalid")
                        candidate_pages = value["pages"]
                        groups[index] = candidate_pages
                    except Exception as exc:
                        if getattr(exc, "retryable", True) is False:
                            page_errors.append({"block_id": bid, "page_index": index, "message": str(exc)})
                            break
                        if attempts[index] >= 2:
                            page_errors.append({"block_id": bid, "page_index": index, "message": str(exc)})
                            break
            groups[index] = candidate_pages
            block["ppt_pages"] = [p for group in groups for p in group]
            block.update(ppt_page_groups=groups, ppt_repair_attempts=attempts)
            block["ppt_errors"] = page_errors
            await _notify(on_checkpoint, deepcopy(block))
    result = normalize_teacher_script_section({"blocks": [blocks[bid] for bid in expected]}, contract)
    result["quality_report"] = validate_teacher_script_section(result, contract)
    return result


def compile_bundle_manuscript(document, template, sections, *, plan_revision_id, script_revision_id):
    blocks = [b for s in sections for b in s["blocks"]]
    graph, planned = lower_bundle_pages(document, template, blocks)
    manuscript = compile_teaching_manuscript(document, graph, template, {}, planned,
        source_context={"lesson_plan_revision_id": plan_revision_id, "script_revision_id": script_revision_id})
    manuscript.generation_contract_version = CONTRACT
    return refresh_manuscript(manuscript)
