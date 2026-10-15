from types import SimpleNamespace

import pytest

from material_parser import parse_material_asset
from material_storage import MaterialRepository
from material_evidence import load_material_evidence
from routers import teacher_lesson_authoring as router
from teacher_lesson_authoring import TeacherLessonAuthoringError


@pytest.mark.asyncio
async def test_lesson_only_upload_consumes_its_parsed_body_without_outline_ingestion(tmp_path, monkeypatch):
    materials = MaterialRepository(tmp_path / 'materials')
    text = '# 设计思维\n\n来源：原 PDF 第92页。需求理解、问题定义、思维发散、原型设计、模型迭代、成果发布。'
    asset = await materials.create_text_asset(filename='lesson-source.md', content=text)
    await parse_material_asset(materials, asset)
    assert materials.load_evidence(asset.asset_id) == []
    monkeypatch.setattr(router, 'material_repository', materials)
    monkeypatch.setattr(router, 'teacher_course_space_repository', SimpleNamespace(
        list_owned=lambda actor, course: [{'package_id': 'owned'}],
        load_owned=lambda package, actor: {'assets': [{'material_asset_id': asset.asset_id}]},
    ))
    ids, evidence = router._course_material_evidence('course', 'teacher', [asset.asset_id])
    assert ids == [asset.asset_id]
    assert evidence and all(unit['source_kind'] == 'course_material' for unit in evidence)
    assert '模型迭代、成果发布' in '\n'.join(unit['source_text'] for unit in evidence)
    assert all(unit['asset_id'] == asset.asset_id and unit['content_hash'] for unit in evidence)
    assert router._course_material_evidence('course', 'teacher', ids) == (ids, evidence)
    assert materials.load_evidence(asset.asset_id) == []  # Pure projection; no source mutation.
    from routers import question_bank
    monkeypatch.setattr(question_bank, 'material_repository', materials)
    bank_evidence = question_bank._load_course_evidence([{'asset_id': asset.asset_id}])
    assert [u['source_text'] for u in bank_evidence] == [u['source_text'] for u in evidence]
    style = load_material_evidence(materials, asset.asset_id,
        {'purpose': 'style_reference', 'usage_policy': 'style_only', 'authority': 'context_only'})
    assert style and all(not unit['factual_allowed'] for unit in style)
    with pytest.raises(TeacherLessonAuthoringError, match='不属于当前课程'):
        router._course_material_evidence('course', 'teacher', ['another-teachers-source'])


@pytest.mark.asyncio
async def test_selected_source_without_body_never_silently_becomes_model_memory(tmp_path, monkeypatch):
    materials = MaterialRepository(tmp_path / 'materials')
    asset = await materials.create_text_asset(filename='title-only.md', content='# 只有标题')
    await parse_material_asset(materials, asset)
    monkeypatch.setattr(router, 'material_repository', materials)
    monkeypatch.setattr(router, 'teacher_course_space_repository', SimpleNamespace(
        list_owned=lambda *args: [{'package_id': 'owned'}],
        load_owned=lambda *args: {'assets': [{'material_asset_id': asset.asset_id}]},
    ))
    with pytest.raises(TeacherLessonAuthoringError) as raised:
        router._course_material_evidence('course', 'teacher', [asset.asset_id])
    assert raised.value.code == 'lesson_material_source_empty'
