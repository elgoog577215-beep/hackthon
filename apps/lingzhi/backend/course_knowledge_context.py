"""Shared, read-only input adapter for course knowledge generation.

Reuses course pedagogy, evidence compilation/freezing and scope contracts.
Snapshots belong to the existing generation job, never a second course store.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
from typing import Any

from course_document import stable_hash
from course_pedagogy import MODULES, coerce_persisted_profile, resolve_pedagogy_profile
from course_generation.workflow import build_course_knowledge_scope_contract
from evidence_package import freeze_evidence_package
from material_evidence import build_evidence_units
from material_models import EvidencePackage, MaterialBinding, ParsedDocument, DocumentBlock, DocumentLocator

SCHEMA = "knowledge_generation_context_v1"


def documents_from_text_sources(course_id: str, sources: list[dict]) -> tuple[list[dict], list[dict]]:
    """Adapt already available text; does not fetch, parse files or invent sources."""
    documents, bindings = [], []
    seen = set()
    for source in sources:
        key = str(source["id"])
        if key in seen:
            raise ValueError("duplicate_material_source")
        seen.add(key)
        content = str(source["text"])
        asset_id = stable_hash({"course": course_id, "source": key}, prefix="kasset_")
        document = ParsedDocument(document_id="doc_" + asset_id, asset_id=asset_id,
            source_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            parse_status="parsed", parser_name="existing_text_adapter", parser_version="1",
            parse_options_hash="text_v1", created_at="", blocks=[DocumentBlock(
                block_id=key, text=content, order=0,
                locator=DocumentLocator(section_path=[str(source.get("scope_id") or key)]))])
        binding = MaterialBinding(asset_id=asset_id, purpose=source.get("purpose", "content_source"),
            usage_policy="must_use" if source.get("purpose") != "style_reference" else "style_only",
            source_label=key, source_metadata={"origin": "material", "source_key": key,
                "provenance": source.get("provenance", "provided_text")})
        documents.append(document.model_dump(mode="json"))
        bindings.append(binding.model_dump(mode="json"))
    return documents, bindings


def _evidence(course: dict, fallback_sources: list[dict] | None) -> tuple[EvidencePackage, dict]:
    artifacts = course.get("generation_stage_artifacts") or {}
    existing = course.get("evidence_package") if "evidence_package" in course else artifacts.get("evidence_package")
    cid = str(course.get("course_id") or "")
    documents = course.get("parsed_documents") or artifacts.get("parsed_documents") or []
    bindings = course.get("material_bindings") or artifacts.get("material_bindings") or []
    catalog = course.get("evidence_catalog") or artifacts.get("evidence_catalog") or []
    source_mode = "course_materials"
    if existing is not None:
        # A broken explicit package must not fall back to sample materials.
        package = EvidencePackage.model_validate(existing)
        if package.course_id != cid or package.status != "frozen":
            raise ValueError("evidence_package_owner_or_status_mismatch")
        source_mode = "existing_frozen_package"
    else:
        # Only an explicitly requested pilot fallback can supply pilot materials.
        if not documents and not bindings and not catalog and fallback_sources:
            documents, bindings = documents_from_text_sources(cid, fallback_sources)
            source_mode = "explicit_reviewed_pilot_fallback"
        if not catalog:
            by_asset = {b["asset_id"]: b for b in bindings}
            for item in documents:
                doc = ParsedDocument.model_validate(item)
                binding = by_asset.get(doc.asset_id)
                if binding is None:
                    raise ValueError("parsed_material_binding_missing")
                catalog.extend(u.model_dump(mode="json") for u in build_evidence_units(doc, MaterialBinding.model_validate(binding)))
        package = freeze_evidence_package(course_id=cid, evidence=catalog, bindings=bindings, frozen_at="context-derived")
    ids = [u.evidence_id for u in package.units]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate_evidence_identity")
    for unit in package.units:
        if unit.content_hash != hashlib.sha256(unit.source_text.encode("utf-8")).hexdigest():
            raise ValueError("evidence_content_hash_mismatch")
    present = {str(d.get("asset_id")) for d in documents}
    inventory = [{"asset_id": d.get("asset_id"), "parse_status": d.get("parse_status"),
                  "source_sha256": d.get("source_sha256"), "block_count": len(d.get("blocks") or [])} for d in documents]
    represented = {u.asset_id for u in package.units}
    inventory += [{"asset_id": b["asset_id"], "parse_status": "missing_document"} for b in bindings
                  if b["asset_id"] not in present and b["asset_id"] not in represented]
    return package, {"source_mode": source_mode, "inventory": inventory,
        "incomplete_assets": [d["asset_id"] for d in inventory if d.get("parse_status") != "parsed"],
        "binding_revision": stable_hash(bindings, prefix="mbind_"),
        "evidence_count": len(package.units), "factual_evidence_count": sum(u.factual_allowed for u in package.units)}


def _scope(course: dict) -> dict:
    existing = course.get("course_knowledge_scope_contract")
    if existing:
        return deepcopy(existing)
    plan = course.get("course_plan") or course.get("course_outline")
    if isinstance(plan, dict) and any(c.get("sections") for c in plan.get("chapters", [])):
        return build_course_knowledge_scope_contract(plan)
    sections = course.get("knowledge_scope_units")
    if sections is None:
        nodes = (course.get("course_document") or {}).get("sections") or course.get("nodes") or []
        parents = {n.get("parent_section_id") or n.get("parent_node_id") for n in nodes}
        sections = [{"node_id": n.get("section_id") or n.get("node_id"),
            "title": n.get("title") or n.get("node_name"), "learning_objective": n.get("learning_objective", ""),
            "scope_boundary": (n.get("attributes") or {}).get("scope_boundary") or n.get("scope_boundary", "")}
            for n in nodes if (n.get("section_id") or n.get("node_id")) not in parents]
    # Temporary input shape for the old compiler; does not persist old chapters.
    request = course.get("generation_request") or {}
    return build_course_knowledge_scope_contract({"course_title": course.get("course_name", ""),
        "positioning": request.get("requirements", ""),
        "learning_objectives": course.get("learning_objectives") or [str((request.get("course_intent") or {}).get("learning_goal") or "")],
        "chapters": [{"sections": deepcopy(sections or [])}]})


def build_knowledge_generation_context(course: dict[str, Any], *, fallback_sources: list[dict] | None = None) -> dict:
    """Derive a reproducible context; no mutations, I/O, model calls or web fetches."""
    course = deepcopy(course)
    package, coverage = _evidence(course, fallback_sources)
    request = course.get("generation_request") or {}
    if course.get("subject_pedagogy_profile") or course.get("pedagogy_profile"):
        profile = coerce_persisted_profile(course)
        profile_origin = "persisted_course_profile"
    else:
        profile = resolve_pedagogy_profile(subject=str(course.get("course_name") or request.get("subject") or ""),
            requirements=str(request.get("requirements") or course.get("requirements") or ""),
            materials=[{"content": u.source_text} for u in package.units if u.factual_allowed],
            requested_mode=request.get("pedagogy_mode", "auto"),
            requested_secondary_mode=request.get("secondary_pedagogy_mode"))
        profile_origin = "declared_course_mode" if profile.user_locked else "inferred_suggestion"
    scope = _scope(course)
    evidence = package.model_dump(mode="json")
    evidence.pop("frozen_at", None)
    result = {"schema_version": SCHEMA, "course_id": course.get("course_id", ""),
        "course_title": course.get("course_name", ""),
        "course_information_revision": course.get("course_information_revision", 0),
        "generation_request_revision": course.get("generation_request_revision", 0),
        "source_document_revision": course.get("course_document_revision", ""),
        "generation_request": deepcopy(request), "course_profile": deepcopy(course.get("course_profile") or {}),
        "course_generation_brief": deepcopy(course.get("course_generation_brief") or {}),
        "requirements": course.get("requirements") or request.get("requirements", ""),
        "target_audience": course.get("target_audience") or request.get("target_audience", ""),
        "course_intent": deepcopy(course.get("course_intent") or request.get("course_intent") or {}),
        "difficulty": course.get("difficulty") or request.get("difficulty", ""),
        "learner_starting_profile": deepcopy(course.get("learner_starting_profile") or request.get("learner_starting_profile") or {}),
        "difficulty_profile": deepcopy(course.get("difficulty_profile") or {}),
        "subject_pedagogy_profile": profile.to_dict(), "profile_origin": profile_origin,
        "teaching_modules": [{"id": mid, "label": MODULES[mid].label,
            "frequency": MODULES[mid].frequency.value, "output_contract": MODULES[mid].output_contract,
            "instruction": MODULES[mid].prompt_instruction} for mid in profile.enabled_module_ids if mid in MODULES],
        "scope_contract": scope, "evidence_package": evidence, "material_coverage": coverage,
        "input_material_revision": course.get("knowledge_input_material_revision", ""),
        "knowledge_revision": (course.get("course_knowledge_base") or {}).get("revision_id", ""),
        "terminology_revision": (course.get("course_knowledge_base") or {}).get("terminology_revision", ""),
        "policy": {"web_retrieval_enabled": False, "evidence_ids_are_provenance_not_truth": True,
            "style_material_is_not_factual_evidence": True, "scope_limited_to_supplied_material": True,
            "conditional_modules_are_not_mandatory": True, "not_a_semantic_validation_receipt": True}}
    aliases: dict[str, list[str]] = {}
    for unit in package.units:
        for block_id in unit.block_ids:
            aliases.setdefault(block_id, []).append(unit.evidence_id)
    result["source_reference_aliases"] = aliases
    result["policy"]["output_source_refs"] = "沿用输入材料短键；本映射将短键连接到冻结证据ID，不自行创造来源。"
    result["revision_id"] = stable_hash(result, prefix="kgctx_")
    return result


def knowledge_context_prompt(context: dict, scope_id: str | None = None, *, compact_evidence: bool = False) -> dict:
    """A read-only prompt view of the frozen snapshot, with traceable evidence."""
    result = deepcopy(context)
    if scope_id:
        result["requested_scope_id"] = scope_id
        units = result["evidence_package"]["units"]
        selected = [u for u in units if scope_id in u.get("locator", {}).get("section_path", [])]
        # No silent empty slice: arbitrary course documents may be cross-cutting.
        if selected:
            result["evidence_package"]["units"] = selected
            result["evidence_selection"] = {"mode": "scope_slice", "selected_count": len(selected), "total_count": len(units)}
    if compact_evidence:
        package = result["evidence_package"]
        result["evidence_package"] = {
            "package_revision_id": package["package_revision_id"], "course_id": package["course_id"],
            "units": [{"evidence_id": u["evidence_id"], "source_short_keys": u["block_ids"],
                "source_text": u["source_text"], "locator": u["locator"],
                "factual_allowed": u["factual_allowed"], "purpose": u["purpose"]} for u in package["units"]]}
        result.pop("source_reference_aliases", None)
        # The full per-file inventory (hashes, parser metadata and counts) lives
        # in the frozen job snapshot. Repeating it beside every evidence unit
        # can exhaust the request budget before any model call. Preserve gaps
        # and all source text; this is a view, not input truncation.
        coverage = result.get("material_coverage") or {}
        inventory = coverage.pop("inventory", [])
        coverage["inventory_count"] = len(inventory)
        coverage["inventory_issues"] = [
            {"asset_id": item.get("asset_id"), "parse_status": item.get("parse_status")}
            for item in inventory if item.get("parse_status") != "parsed"
        ]
        result["material_coverage"] = coverage
        result["audit_snapshot_ref"] = "request_snapshot.knowledge_generation_context"
        result["policy"]["output_source_refs"] = "沿用每个证据单元的source_short_keys；完整来源、哈希及映射保存在同一任务快照。"
    return result
