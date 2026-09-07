"""Course review adapters for the teacher's current PPT manuscript."""
from copy import deepcopy
import json

from ppt_teaching_manuscript import revise_teaching_manuscript
from slide_deck_v6_models import PptManuscriptV1


def manuscript_fields(page):
    fields = {"title": str(page.get("title") or ""), "page_goal": str(page.get("page_goal") or "")}
    fields.update({f"element:{element['element_id']}": str(element.get("text") or "")
                   for element in (page.get("teaching") or {}).get("elements") or []
                   if element.get("kind") == "text"})
    return fields


async def generate_manuscript_candidate(*, course_id, lesson_id, plan, items, repository, course_service):
    state = repository.current_v6_ppt_manuscript(course_id, lesson_id) or {}
    if state.get("source_state") != "current" or not state.get("manuscript"):
        raise ValueError("PPT 内容稿来源已变化，请先同步后再审阅")
    manuscript = PptManuscriptV1.model_validate(state["manuscript"])
    updates = []
    for item in items:
        if list(item.base_revisions.values()) != [state["revision"]]:
            raise ValueError("PPT 内容稿版本冲突，请重新分析")
        page_id = item.metadata["unit_id"].split(":", 2)[-1]
        page = next(page for page in manuscript.pages if page.page_id == page_id)
        if page.teacher_locked:
            raise ValueError("所选 PPT 页面已锁定，请先解除锁定")
        original = manuscript_fields(page.model_dump(mode="json"))
        literal = item.metadata.get("literal_replacement") or {}
        if literal.get("before"):
            changed = {key: value.replace(literal["before"], literal.get("after", "")) for key, value in original.items()}
        else:
            text = json.dumps(original, ensure_ascii=False)
            response = await course_service.rewrite_selection(course_id=course_id,
                node={"node_id": lesson_id, "title": page.title}, selected_text=text, node_content=text,
                heading_path=[page.title], user_requirement=plan.request_text + "\n只返回相同键的 JSON 字符串映射；只修改展示文案，保留原意、公式、答案、数据和引用，不添加字段。",
                action_type="rewrite", course_context=page.speaker_notes.model_dump_json(), user_id=plan.user_id)
            changed = json.loads(response.get("replacement_text") or "")
        if not isinstance(changed, dict) or set(changed) != set(original) or any(not isinstance(value, str) for value in changed.values()):
            raise ValueError("PPT 修改建议格式不完整，原稿已保留")
        teaching = page.teaching.model_dump(mode="json")
        for element in teaching["elements"]:
            if f"element:{element['element_id']}" in changed:
                element["text"] = changed[f"element:{element['element_id']}"]
        updates.append({"page_id": page_id, "title": changed["title"], "page_goal": changed["page_goal"], "teaching": teaching})
        item.metadata.update(before_content="\n\n".join(original.values()), after_content="\n\n".join(changed.values()),
                             after_preview="\n".join(changed.values()), change_count=sum(original[key] != changed[key] for key in original))
    candidate = revise_teaching_manuscript(manuscript, updates)
    return {"action": "edit_manuscript", "lesson_unit_id": lesson_id, "base_revision_id": state["revision"],
            "source_script_revision_id": state["source_script_revision_id"], "previous_manuscript": deepcopy(state["manuscript"]),
            "candidate_manuscript": candidate.model_dump(mode="json"), "candidate_revision_id": candidate.manuscript_revision}


def apply_manuscript_candidate(repository, course_id, payload, *, undo=False):
    lesson_id = payload["lesson_unit_id"]
    expected = payload["candidate_revision_id"] if undo else payload["base_revision_id"]
    manuscript = payload["previous_manuscript"] if undo else payload["candidate_manuscript"]
    with repository._course_lock(course_id):
        lesson = repository.lesson(course_id, lesson_id)
        state = lesson.get("ppt_manuscript") or {}
        if lesson.get("working_script_revision_id") != payload["source_script_revision_id"] or state.get("source_state") != "current":
            raise ValueError("讲义来源已变化，PPT 修改未覆盖当前版本")
        if state.get("revision") == manuscript["manuscript_revision"]:
            return state["revision"]
        saved = repository.update_v6_ppt_manuscript_draft(course_id, lesson_id,
            expected_manuscript_revision=expected, manuscript=manuscript)
        return saved["revision"]
