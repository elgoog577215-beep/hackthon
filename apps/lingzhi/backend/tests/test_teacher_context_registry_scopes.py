"""Opening course changes must read canonical PPTs from their lecture storage scopes."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from backend.tests.test_teacher_course_change import document, representation_registry
from course_evolution.application import CourseEvolutionApplicationService
from teaching_representations import (
    RepresentationConflict, TeachingRepresentationRepository, TEACHING_REPRESENTATION_REGISTRY_SCHEMA,
)


def service_with_scoped_slides(tmp_path, source_ids):
    repository = TeachingRepresentationRepository(tmp_path / 'representations')
    authoring = {'lessons': {}}
    for index, source_id in enumerate(source_ids):
        scope = f'lecture-storage-{index}'
        payload = deepcopy(representation_registry())
        payload.update(course_id=source_id, schema_version=TEACHING_REPRESENTATION_REGISTRY_SCHEMA)
        page = payload['specs'][0]['payload']['content']['pages'][0]
        page.update(page_id=f'page-{index}', title=f'Lecture {index} slide', source_section_ids=[f'lesson-{index}'])
        repository._atomic_write(repository._path(scope), payload)
        authoring['lessons'][f'lesson-{index}'] = {'ppt_assets': [{
            'synthetic_course_id': scope, 'working_v6_revision_id': 'binding',
            'working_representation_id': f'representation-{index}',
            'v6_revisions': [{'revision_id': 'binding', 'spec_id': 'spec-1'}],
        }]}
    service = CourseEvolutionApplicationService(
        evolution_repository=None,
        document_repository=SimpleNamespace(load_document=lambda _: (document(), {})),
        authoring_repository=SimpleNamespace(load=lambda _: authoring),
        representation_repository=repository,
        question_bank_repository=SimpleNamespace(load_bundle=lambda _: None),
        course_service=None,
        task_manager=SimpleNamespace(get_generation_preview=lambda *a, **k: None),
    )
    return service, repository


@pytest.mark.parametrize('source_ids', [
    ['course-1', 'course-1'], ['lecture-storage-0', 'lecture-storage-1'], ['course-1', 'lecture-storage-1'],
])
def test_course_context_reads_each_lecture_without_rewriting_its_source_identity(tmp_path, source_ids):
    service, repository = service_with_scoped_slides(tmp_path, source_ids)
    before = {p.name: p.read_bytes() for p in repository.root_dir.glob('*.json')}
    context = service.teacher_context('course-1')
    assert context.ready
    slides = [unit for unit in context.units if unit.asset_type == 'ppt']
    assert {unit.unit_id for unit in slides} == {'ppt:lesson-0:page-0', 'ppt:lesson-1:page-1'}
    assert {unit.title for unit in slides} == {'Lecture 0 slide', 'Lecture 1 slide'}
    assert {p.name: p.read_bytes() for p in repository.root_dir.glob('*.json')} == before


def test_course_context_still_rejects_a_registry_owned_by_another_course(tmp_path):
    service, _ = service_with_scoped_slides(tmp_path, ['unrelated-course'])
    with pytest.raises(RepresentationConflict, match='another course'):
        service.teacher_context('course-1')
