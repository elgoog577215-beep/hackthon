"""Versioned evidence projection over the unchanged, saved handout inputs."""
from copy import deepcopy

CONTRACT = 'complete_handout_blocks_v1'


def project_complete_blocks(raw,state,context,lesson_id):
    from handout_knowledge import handout_sources
    from course_knowledge_context import documents_from_text_sources
    from material_models import ParsedDocument,MaterialBinding
    from material_evidence import build_evidence_units
    from evidence_package import freeze_evidence_package
    from course_document import stable_hash
    _,sources=handout_sources(raw,state,lesson_id)
    documents,bindings=documents_from_text_sources(raw['course_id'],sources)
    by_asset={b['asset_id']:MaterialBinding.model_validate(b) for b in bindings}
    units=[u.model_dump(mode='json') for d in documents for u in build_evidence_units(
        ParsedDocument.model_validate(d),by_asset[d['asset_id']],preserve_blocks=True)]
    package=freeze_evidence_package(course_id=raw['course_id'],evidence=units,bindings=bindings,frozen_at='context-derived').model_dump(mode='json')
    package.pop('frozen_at',None)
    projected=deepcopy(context)
    projected.update(evidence_package=package,source_unit_contract=CONTRACT,
        source_projection_revision=stable_hash({'contract':CONTRACT,'package':package},prefix='kprojection_'))
    projected['material_coverage'].update(evidence_count=len(units),factual_evidence_count=sum(u['factual_allowed'] for u in units))
    # Input identity still binds the original saved bodies and revisions.
    # The derived projection has its own explicit contract and content hash.
    return projected
