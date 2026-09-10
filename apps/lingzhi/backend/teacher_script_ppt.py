"""Joint handout/page generation and deterministic lowering into the V6 manuscript."""
from __future__ import annotations

import asyncio
import inspect
import json
import re
from copy import deepcopy
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic_core import from_json

from course_document import CourseBlock, CourseDocument, CourseSection, stable_hash
from course_presentation_graph import block_source_text, compile_course_presentation_graph
from ppt_fixed_draft import form_type, lower_fixed_response
from ppt_fixed_templates import fixed_capabilities, fixed_slug
from ppt_page_repair_units import (
    full_page_repair_unit,
    page_repair_source_units,
    page_repair_unit_block,
)
from ppt_source_quotes import source_excerpt_catalog
from ppt_repair_response import parse_page_response
from ppt_teaching_manuscript import compile_teaching_manuscript, refresh_manuscript
from ppt_teaching_planner import normalize_page_response
from teacher_script import normalize_teacher_script_section, validate_teacher_script_section

CONTRACT = "script_ppt_bundle_v1"
DEFAULT_THEME = "qizhi-classroom"
RECOVERY_CONTRACT = "ppt_page_recovery_v3"


class PptPageRepairTimeout(RuntimeError):
    retryable = True
    code = "lesson_ppt_page_timeout"

    def __init__(self, block_id: str, repair_unit_id: str) -> None:
        self.block_id = block_id
        self.repair_unit_id = repair_unit_id
        super().__init__(
            "PPT 页面生成超时，已保留讲义、已完成页面和来源范围检查点；"
            "重试只处理未完成内容。"
        )


def describe_bundle_failure(exc: Exception) -> dict[str, Any] | None:
    technical_detail = str(exc)
    if isinstance(exc, PptPageRepairTimeout):
        return {
            "code": exc.code,
            "message": str(exc),
            "category": "provider",
            "recovery_action": "retry_original",
            "retryable": True,
            "failed_step": "pages",
            "failed_block_id": exc.block_id,
            "repair_unit_id": exc.repair_unit_id,
            "technical_detail": technical_detail,
        }
    response_failure = "script_ppt_response_" in technical_detail
    match = re.search(r"source_excerpt_mismatch:([^:\s]+)", technical_detail)
    unknown_quote = re.search(r"source_quote_id_unknown:([^:\s]+)", technical_detail)
    capacity_failure = bool(re.search(
        r"string_too_long|fixed_field_text_too_long|teaching_text_capacity_exceeded|should have at most \d+ characters|"
        r"type=too_long|List should have at most \d+ items",
        technical_detail,
    ))
    page_contract_failure = bool(re.search(
        r"source_revision_stale|source_block_unknown|source_quote_choice_conflict|selected_artifact_not_exact|"
        r"teaching_fact_token_unsupported|teaching_.*(?:capacity|supported)|script_ppt_(?:page|layout)|"
        r"string_type|Input should be a valid string|model_type|Input should be a valid dictionary",
        technical_detail,
    ))
    if match is None and unknown_quote is None and not capacity_failure and not page_contract_failure and not response_failure:
        return None
    if response_failure:
        code = "lesson_ppt_model_response_invalid"
        message = "页面修复未返回可用的结构化内容，已保留讲义、已完成页面和原始失败原因。"
        failed_block_id = ""
    elif capacity_failure:
        code = "lesson_ppt_page_capacity_failed"
        message = "页面文字超过当前版式容量，系统没有保存无法完整显示的内容稿。"
        failed_block_id = ""
    elif match is not None or unknown_quote is not None:
        code = "lesson_ppt_source_grounding_failed"
        message = "页面引用未能匹配讲义原文，系统没有保存来源不可靠的内容稿。"
        failed_block_id = match.group(1) if match else ""
    else:
        code = "lesson_ppt_page_contract_failed"
        message = "页面内容或版式未通过最终检查，系统已保留讲义和可重试检查点。"
        failed_block_id = ""
    return {
        "code": code,
        "message": message,
        "category": "structure" if response_failure else "quality",
        "recovery_action": "retry_original",
        "retryable": True,
        "failed_step": "pages" if response_failure else "sources",
        "failed_block_id": failed_block_id,
        "technical_detail": technical_detail,
    }


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


def _block_literal_source_ranges(block: dict[str, Any]) -> list[dict[str, Any]]:
    block_id = block["block_id"]
    return source_excerpt_catalog({
        block_id: {
            "block_id": block_id,
            "block_revision": stable_hash(block["content"], prefix="block_"),
            "full_text": block["content"],
        }
    })


def _grounded_fallback_page(block: dict[str, Any], template) -> dict[str, Any]:
    catalog = _block_literal_source_ranges(block)
    source_text = str(block.get("content") or "").strip()
    if not catalog and source_text:
        catalog = [{"block_id": block["block_id"], "quote": source_text}]
    points = []
    seen = set()
    for item in catalog:
        quote = str(item.get("quote") or "").strip()
        if not quote or quote in seen:
            continue
        seen.add(quote)
        points.append({
            "text": _compact_screen_text(quote, 52),
            "sources": [{"block_id": str(item.get("block_id") or block["block_id"]), "quote": quote}],
        })
        if len(points) == 3:
            break
    if not points:
        raise ValueError(f"script_ppt_pages_missing:{block['block_id']}")
    title = _compact_screen_text(str(block.get("title") or "讲义要点"), 28)
    return {
        "layout_id": template.layout_id("bullets"),
        "page_goal": title,
        "fields": {
            "title": title,
            "notes": "模型未返回可用页面，已根据当前讲义原文整理要点。",
            "split_reason": "使用讲义原文生成保底页面",
            "points": points,
        },
    }


def _compact_screen_text(value: str, limit: int) -> str:
    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text
    for separator in ("。", "；", ";", "，", ","):
        clause = text.split(separator, 1)[0].strip()
        if 1 < len(clause) <= limit:
            return clause
    prefix = text[: max(1, limit - 1)].rstrip("，,；;：: ")
    if re.search(r"[A-Za-z0-9_+#.]$", prefix) and len(text) > len(prefix) and re.match(r"[A-Za-z0-9_+#.]", text[len(prefix)]):
        prefix = re.sub(r"\s*[A-Za-z0-9_+#.]+$", "", prefix).rstrip("，,；;：: ")
    return prefix + "…"


def _value_at_path(value: Any, path: tuple[Any, ...]) -> tuple[Any, Any] | None:
    current = value
    for segment in path[:-1]:
        if not isinstance(current, (dict, list)):
            return None
        current = current[segment]
    return (current, path[-1]) if path else None


def _unwrap_source_text(value: Any) -> Any:
    if isinstance(value, dict) and isinstance(value.get("text"), str):
        return value["text"]
    return value


def _fit_page_capacity(page: dict[str, Any], catalog: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    fitted = deepcopy(page)
    fields = fitted.get("fields")
    if not isinstance(fields, dict):
        return fitted
    model = form_type(fixed_slug(str(fitted.get("layout_id") or "")), authored=True)
    for _ in range(4):
        try:
            model.model_validate(fields)
            break
        except ValidationError as exc:
            changed = False
            for issue in exc.errors():
                target = _value_at_path(fields, tuple(issue.get("loc") or ()))
                if target is None:
                    continue
                owner, key = target
                if issue.get("type") == "string_type":
                    wrapped = owner[key]
                    if isinstance(wrapped, dict) and isinstance(wrapped.get("text"), str):
                        if key == "text" and "sources" not in owner and isinstance(wrapped.get("sources"), list):
                            owner["sources"] = wrapped["sources"]
                        owner[key] = wrapped["text"]
                        changed = True
                elif issue.get("type") == "missing" and key == "text" and isinstance(owner, dict):
                    choices = owner.get("sources") or []
                    if len(choices) == 1 and isinstance(choices[0], dict):
                        selected = next((item for item in (catalog or []) if item.get("quote_id") == choices[0].get("quote_id")), None)
                        literal = str(choices[0].get("quote") or "")
                        if selected is not None:
                            owner[key] = selected["quote"]
                            changed = True
                        elif literal and any(literal in item["quote"] and item["block_id"] == choices[0].get("block_id") for item in (catalog or [])):
                            owner[key] = literal
                            changed = True
                elif issue.get("type") == "string_too_long":
                    limit = int((issue.get("ctx") or {}).get("max_length") or 0)
                    if limit > 0:
                        owner[key] = _compact_screen_text(str(owner[key]), limit)
                        changed = True
                elif issue.get("type") == "too_long" and len(tuple(issue.get("loc") or ())) > 1:
                    limit = int((issue.get("ctx") or {}).get("max_length") or 0)
                    if limit > 0 and isinstance(owner[key], list):
                        owner[key] = owner[key][:limit]
                        changed = True
                elif issue.get("type") == "model_type" and isinstance(owner[key], str):
                    class_name = str((issue.get("ctx") or {}).get("class_name") or "")
                    source = _portable_source_choice(owner[key], catalog or [], str(key))
                    if source and re.fullmatch(r"TextField|TextUpTo\d+|ExplainedPoint|RadialSatellite", class_name):
                        owner[key] = {"text": owner[key], "sources": [source]}
                        changed = True
                    elif source and class_name == "ExactField":
                        owner[key] = {"sources": [source]}
                        changed = True
            if not changed:
                break
    return fitted


def _balanced_capacity_chunks(items: list[Any], maximum: int, minimum: int) -> list[list[Any]]:
    count = max(2, (len(items) + maximum - 1) // maximum)
    base, remainder = divmod(len(items), count)
    chunks = []
    offset = 0
    for index in range(count):
        size = base + (1 if index < remainder else 0)
        chunks.append(items[offset:offset + size])
        offset += size
    original = deepcopy(chunks)
    for index, chunk in enumerate(chunks):
        missing = max(0, minimum - len(chunk))
        if not missing:
            continue
        if index > 0:
            chunks[index] = original[index - 1][-missing:] + chunk
        elif len(original) > 1:
            chunks[index] = chunk + original[index + 1][:missing]
    return chunks


def _split_page_list_capacity(page: dict[str, Any]) -> list[dict[str, Any]]:
    fields = page.get("fields")
    if not isinstance(fields, dict):
        return [page]
    model = form_type(fixed_slug(str(page.get("layout_id") or "")), authored=True)
    try:
        model.model_validate(fields)
        return [page]
    except ValidationError as exc:
        overflow = next((issue for issue in exc.errors()
                         if issue.get("type") == "too_long" and len(tuple(issue.get("loc") or ())) == 1), None)
    if overflow is None:
        return [page]
    key = tuple(overflow.get("loc") or ())[0]
    items = fields.get(key)
    maximum = int((overflow.get("ctx") or {}).get("max_length") or 0)
    schema = model.model_json_schema().get("properties", {}).get(key, {})
    minimum = int(schema.get("minItems") or 1)
    if not isinstance(items, list) or maximum <= 0 or len(items) <= maximum:
        return [page]
    chunks = _balanced_capacity_chunks(items, maximum, minimum)
    total = len(chunks)
    split_pages = []
    for index, chunk in enumerate(chunks, start=1):
        split = deepcopy(page)
        split["fields"][key] = chunk
        split["fields"]["split_reason"] = f"{key} 超过单页容量，拆分为第 {index}/{total} 页"
        split_pages.append(split)
    return split_pages


def _source_query(owner: dict[str, Any]) -> str:
    return " ".join(str(owner.get(key) or "") for key in ("text", "heading", "label", "title") if owner.get(key))


def _quote_score(query: str, quote: str) -> tuple[int, int]:
    query_tokens = set(re.findall(r"[a-z0-9_+#.]+|[\u4e00-\u9fff]", query.lower()))
    quote_tokens = set(re.findall(r"[a-z0-9_+#.]+|[\u4e00-\u9fff]", quote.lower()))
    return len(query_tokens & quote_tokens), -len(quote)


def _context_catalog(context: str, catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if context == "formula":
        matched = [item for item in catalog if re.search(r"\$|\\\(|\\\[", str(item.get("quote") or ""))]
        return matched or catalog
    if context == "code":
        matched = [item for item in catalog if re.fullmatch(r"```[\s\S]*```", str(item.get("quote") or "").strip())]
        if not matched:
            matched = [item for item in catalog if re.fullmatch(r"`[^`\n]+`", str(item.get("quote") or "").strip())]
        return matched or catalog
    if context in {"value", "unit", "data"}:
        matched = [item for item in catalog if re.search(r"\d", str(item.get("quote") or ""))]
        return matched or catalog
    return catalog


def _portable_source_choice(query: str, catalog: list[dict[str, Any]], context: str = "") -> dict[str, str] | None:
    candidates = _context_catalog(context, catalog)
    if not candidates:
        return None
    best = max(candidates, key=lambda item: _quote_score(query, str(item.get("quote") or "")))
    if _quote_score(query, str(best.get("quote") or ""))[0] <= 0:
        best = min(candidates, key=lambda item: len(str(item.get("quote") or "")))
    return {"block_id": str(best["block_id"]), "quote": str(best["quote"])}


def _stabilize_source_choices(value: Any, catalog: list[dict[str, Any]], context: str = "", source_texts=None) -> None:
    from slide_source_tokens import _protected_tokens

    allowed = {item["quote_id"]: item for item in catalog}
    if isinstance(value, dict):
        choices = value.get("sources")
        query = _source_query(value)
        candidates = _context_catalog(context, catalog)
        if isinstance(choices, list) and candidates:
            best = max(candidates, key=lambda item: _quote_score(query, str(item.get("quote") or ""))) if query else None
            resolved = []
            for choice in choices:
                selected = allowed.get(choice.get("quote_id")) if isinstance(choice, dict) else None
                if selected is None and isinstance(choice, dict) and not choice.get("quote_id") and choice.get("block_id") and choice.get("quote"):
                    literal = str(choice["quote"])
                    if (literal in (source_texts or {}).get(choice["block_id"], "")
                            or any(literal in str(item.get("quote") or "") and item["block_id"] == choice["block_id"] for item in catalog)):
                        resolved.append(choice)
                        continue
                if selected is None and best is not None and _quote_score(query, str(best.get("quote") or ""))[0] > 0:
                    selected = best
                if selected is None:
                    shortest = min(candidates, key=lambda item: len(str(item.get("quote") or "")))
                    # A source-only artifact has no claim text to disambiguate
                    # multiple code/formula choices. Do not guess a short one.
                    if query or all(shortest["quote"] in item["quote"] for item in candidates):
                        selected = shortest
                if selected is not None:
                    resolved.append({"block_id": selected["block_id"], "quote": selected["quote"]})
                else:
                    resolved.append(choice)
            # An existing literal may be real but support only part of the text.
            # Bind additional exact ranges, never add claims to the handout or
            # remove factual tokens from the screen to make validation pass.
            if query:
                supported = _protected_tokens("\n".join(str(s.get("quote") or "") for s in resolved if isinstance(s, dict)))
                missing = _protected_tokens(query) - supported
                while missing:
                    supporting = [item for item in candidates if missing & _protected_tokens(str(item.get("quote") or ""))]
                    if not supporting:
                        break  # Leave an unsupported claim for bounded model repair.
                    selected = max(supporting, key=lambda item: (
                        len(missing & _protected_tokens(str(item["quote"]))),
                        _quote_score(query, str(item["quote"])),
                    ))
                    resolved.append({"block_id": selected["block_id"], "quote": selected["quote"]})
                    missing -= _protected_tokens(str(selected["quote"]))
            if resolved != choices:
                value["sources"] = resolved
        for key, child in value.items():
            _stabilize_source_choices(child, catalog, str(key), source_texts)
    elif isinstance(value, list):
        for child in value:
            _stabilize_source_choices(child, catalog, context, source_texts)


def _expand_identifier_shorthand(value, content):
    names = set(re.findall(r"(?<![A-Za-z0-9_.])[A-Za-z_][A-Za-z0-9_.]{2,}(?![A-Za-z0-9_.])", content))

    def expand(match):
        left, right = match.group(1), match.group(2)
        if left not in names or right in names:
            return match.group(0)
        candidates = [name for name in names if name.endswith(right) and len(name) > len(right) + 2
                      and left.startswith(name[:-len(right)])]
        return left + "/" + candidates[0] if len(candidates) == 1 else match.group(0)

    if isinstance(value, dict):
        for key, child in value.items():
            if key == "sources":
                continue
            if key in {"text", "heading", "title", "page_goal"} and isinstance(child, str):
                value[key] = re.sub(r"(?<![A-Za-z0-9_.])([A-Za-z_][A-Za-z0-9_.]{2,})\s*/\s*([A-Z][A-Za-z0-9_]+)(?![A-Za-z0-9_])", expand, child)
            else:
                _expand_identifier_shorthand(child, content)
    elif isinstance(value, list):
        for child in value:
            _expand_identifier_shorthand(child, content)


def _prepare_page_candidates(pages: list[Any], block: dict[str, Any], template=None) -> list[Any]:
    catalog = _block_literal_source_ranges(block)
    prepared = []
    for page in pages:
        if not isinstance(page, dict):
            prepared.append(page)
            continue
        candidate = deepcopy(page)
        _expand_identifier_shorthand(candidate, block["content"])
        for key in ("layout_id", "page_goal"):
            if key in candidate:
                candidate[key] = _unwrap_source_text(candidate[key])
        try:
            candidate = _fit_page_capacity(candidate, catalog)
            splits = _split_page_list_capacity(candidate)
            normalized_splits = []
            for split_candidate in splits:
                split_candidate = _fit_page_capacity(split_candidate, catalog)
                _stabilize_source_choices(split_candidate, catalog, source_texts={block["block_id"]: block["content"]})
                if template is not None:
                    from ppt_code_pagination import paginate_code_page
                    normalized_splits.extend(paginate_code_page(split_candidate, block, template))
                else:
                    normalized_splits.append(split_candidate)
            prepared.extend(normalized_splits)
        except (ValueError, KeyError, TypeError, AttributeError, IndexError):
            # Malformed model output must reach the same bounded validation /
            # repair path as source failures, rather than abort preparation.
            prepared.append(deepcopy(page))
    return prepared


def completion_seed_blocks(blocks, checkpoint):
    """Keep current handout authority separate from resumable page state."""
    seeds = {}
    for block in blocks:
        bid = block["block_id"]
        saved = checkpoint.get(bid)
        seed = deepcopy(block)
        if saved is not None:
            for key in tuple(seed):
                if key.startswith("ppt_"):
                    seed.pop(key)
            if saved.get("content") == block.get("content"):
                seed.update({key: deepcopy(value) for key, value in saved.items() if key.startswith("ppt_")})
        # Each explicit attempt has its own finite repair budget. The caller
        # resumes the original job; it never restarts accepted handout text.
        seed.pop("ppt_repair_attempts", None)
        seed.pop("ppt_repair_state", None)
        seed["generation_contract_version"] = CONTRACT
        seeds[bid] = seed
    return seeds


def require_valid_bundle_pages(sections):
    for section in sections:
        for block in section["blocks"]:
            errors = block.get("ppt_errors") or []
            if errors:
                detail = "; ".join(str(error.get("message") or "invalid page") for error in errors)
                raise ValueError(f"script_ppt_page_validation_failed:{block['block_id']}: {detail}")


async def _notify(callback, *args):
    if callback:
        result = callback(*args)
        if inspect.isawaitable(result):
            await result


def _page_repair_prompt(block, pages, template, validation_error, repair_error="", repair_unit=None):
    known = {layout.template_layout_id: layout for layout in template.layouts}
    selected = {p.get("layout_id") for p in pages if isinstance(p, dict)} & set(known)
    if not selected:
        slugs = {"bullets", "comparison", "flow", "question", "summary"}
        if "`" in block["content"] or "~~~" in block["content"] or (repair_unit or {}).get("source_kind") == "code":
            slugs.add("code")
        if re.search(r"\$|\\\[|\\\(", block["content"]):
            slugs.add("formula")
        selected = {lid for lid in known if fixed_slug(lid) in slugs}
    catalog = _block_literal_source_ranges(block)
    code_ranges = [r for r in catalog if re.fullmatch(r"```[\s\S]*?```", r["quote"].strip())]
    catalog = [r for r in catalog if not any(c["start"] <= r["start"] and r["end"] <= c["end"] and r != c for c in code_ranges)]
    return (
        "你正在把已经固定的讲义整理为课堂PPT页面。只返回一个JSON对象 {\"pages\":[...]}，不得输出Markdown或解释。"
        "pages 至少一页，每页仅含 layout_id、page_goal、fields；fields 遵守对应表单。"
        "保留教学条件、例题和解答，覆盖本环节内容，避免重复封面。普通文案简洁，标识符和数值只能来自所给原文。"
        "sources 只返回 quote_id，格式为 [{\"quote_id\":\"提供的ID\"}]。代码、公式和数据使用精确来源；长代码由系统按实际容量连续分页，不必裁掉代码。"
        "不得修改讲义，不得补写讲义没有的API或事实。\n"
        + json.dumps({"block_id": block["block_id"], "title": block.get("title"), "role": block.get("role"),
            "repair_unit": repair_unit or full_page_repair_unit(block["block_id"], block["content"]),
            "forms": {lid: form_type(fixed_slug(lid), authored=True).model_json_schema() for lid in sorted(selected)},
            "literal_source_ranges": catalog, "pages_to_repair": pages,
            "validation_error": validation_error, "previous_repair_error": repair_error}, ensure_ascii=False)
    )


async def generate_bundle(*, invoke, contract, instructions, template, on_delta=None,
                          on_reset=None, on_checkpoint=None, seed_blocks=None, immutable_handout=False,
                          provider_recovery_sleep=asyncio.sleep):
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
            response = ScriptPptBundle.model_validate(parse_page_response(raw))
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
    provider_recovery_used = False
    response_contract_failed = False
    for bid in expected:
        block = blocks[bid]
        block["ppt_recovery_contract_version"] = RECOVERY_CONTRACT
        page_errors = []
        pages = deepcopy(block.get("ppt_pages") or [])
        groups = deepcopy(block.get("ppt_page_groups") or [[p] for p in pages] or [[]])
        attempts = list(block.get("ppt_repair_attempts") or [0] * len(groups))
        if len(attempts) != len(groups):
            raise ValueError("script_ppt_checkpoint_invalid")
        repair_units = deepcopy(block.get("ppt_page_repair_units") or [])
        if repair_units and len(repair_units) != len(groups):
            raise ValueError("script_ppt_checkpoint_invalid")
        if not repair_units:
            if len(groups) == 1 and not groups[0] and not pages:
                repair_units = page_repair_source_units(bid, block["content"])
                groups = [[] for _ in repair_units]
                attempts = [0 for _ in repair_units]
            else:
                whole = full_page_repair_unit(bid, block["content"])
                repair_units = [deepcopy(whole) for _ in groups]
        normalized_groups, unit_attempts, normalized_units = [], [], []
        for group, used, repair_unit in zip(groups, attempts, repair_units, strict=True):
            repair_block = page_repair_unit_block(block, repair_unit)
            prepared = _prepare_page_candidates(group, repair_block, template)
            normalized_groups.extend([[page] for page in prepared] or [[]])
            unit_attempts.extend([used] * max(1, len(prepared)))
            normalized_units.extend([deepcopy(repair_unit)] * max(1, len(prepared)))
        groups, attempts, repair_units = normalized_groups, unit_attempts, normalized_units
        for index, group in enumerate(groups):
            candidate_pages = group
            repair_unit = repair_units[index]
            repair_block = page_repair_unit_block(block, repair_unit)
            previous_repair_error = ""
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
                        block.update(
                            ppt_recovery_contract_version=RECOVERY_CONTRACT,
                            ppt_page_groups=groups,
                            ppt_page_repair_units=repair_units,
                            ppt_repair_attempts=attempts,
                            ppt_repair_state={
                                "page_group": index + 1,
                                "total_page_groups": len(groups),
                                "attempt": attempts[index],
                                "max_attempts": 2,
                                "error": detail,
                                "repair_unit_id": repair_unit["repair_unit_id"],
                                "source_start": repair_unit["source_start"],
                                "source_end": repair_unit["source_end"],
                                "source_chars": repair_unit["source_chars"],
                            },
                        )
                        await _notify(on_checkpoint, deepcopy(block))
                        raw = await invoke("修复当前 PPT 页面，只返回 {\"pages\":[...]}，必要时拆分本页。",
                            _page_repair_prompt(repair_block, candidate_pages, template, detail, previous_repair_error, repair_unit),
                            output_tokens=min(3500, max(1800, repair_unit["source_chars"] + 1000)),
                            stream_delta=None, stream_reset=None)
                        value = parse_page_response(raw)
                        if not isinstance(value.get("pages"), list) or not value["pages"]:
                            raise ValueError("script_ppt_response_invalid_shape:pages_must_be_nonempty_array")
                        candidate_pages = _prepare_page_candidates(value["pages"], repair_block, template)
                        groups[index] = candidate_pages
                    except Exception as exc:
                        previous_repair_error = str(exc)
                        issue = {"block_id": bid, "page_index": index, "validation_error": detail,
                                 "repair_error": str(exc), "message": detail + "; repair_failed: " + str(exc)}
                        from course_generation_errors import classify_generation_failure
                        failure = classify_generation_failure(exc)
                        timeout_failure = (
                            failure.get("code") == "provider_timeout"
                            or getattr(exc, "code", "") == "lesson_script_model_timeout"
                        )
                        if timeout_failure or failure.get("code") == "provider_unavailable" or str(exc).startswith("script_ppt_response_empty"):
                            block.update(ppt_pages=[p for g in groups for p in g], ppt_page_groups=groups,
                                         ppt_page_repair_units=repair_units, ppt_repair_attempts=attempts,
                                         ppt_errors=[*page_errors, issue])
                            if not provider_recovery_used and attempts[index] < 2:
                                provider_recovery_used = True
                                block["ppt_repair_state"].update(waiting_for_provider=True, retry_after_seconds=31)
                                await _notify(on_checkpoint, deepcopy(block))
                                await provider_recovery_sleep(31)
                                continue
                            await _notify(on_checkpoint, deepcopy(block))
                            if timeout_failure:
                                raise PptPageRepairTimeout(bid, repair_unit["repair_unit_id"]) from exc
                            raise
                        if getattr(exc, "retryable", True) is False:
                            page_errors.append(issue)
                            break
                        if attempts[index] >= 2:
                            page_errors.append(issue)
                            response_contract_failed = str(exc).startswith("script_ppt_response_")
                            break
            if not candidate_pages and not immutable_handout:
                try:
                    candidate_pages = _prepare_page_candidates(
                        [_grounded_fallback_page(repair_block, template)], repair_block, template
                    )
                    validate_block_pages({**block, "ppt_pages": candidate_pages}, template)
                    page_errors = [error for error in page_errors if error.get("page_index") != index]
                except (ValueError, RuntimeError, KeyError):
                    candidate_pages = []
            groups[index] = candidate_pages
            block["ppt_pages"] = [p for group in groups for p in group]
            block.update(ppt_page_groups=groups, ppt_page_repair_units=repair_units, ppt_repair_attempts=attempts)
            block.pop("ppt_repair_state", None)
            block["ppt_errors"] = page_errors
            await _notify(on_checkpoint, deepcopy(block))
            if response_contract_failed:
                break
        if response_contract_failed:
            break
    result = normalize_teacher_script_section({"blocks": [blocks[bid] for bid in expected]}, contract)
    result["quality_report"] = validate_teacher_script_section(result, contract)
    return result


def compile_bundle_manuscript(document, template, sections, *, plan_revision_id, script_revision_id):
    require_valid_bundle_pages(sections)
    blocks = [b for s in sections for b in s["blocks"]]
    graph, planned = lower_bundle_pages(document, template, blocks)
    manuscript = compile_teaching_manuscript(document, graph, template, {}, planned,
        source_context={"lesson_plan_revision_id": plan_revision_id, "script_revision_id": script_revision_id})
    manuscript.generation_contract_version = CONTRACT
    return refresh_manuscript(manuscript)
