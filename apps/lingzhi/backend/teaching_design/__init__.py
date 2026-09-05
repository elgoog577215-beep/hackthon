"""Public teaching-design compiler API.

Generation features consume this package instead of reading subject registries
or recreating teaching classifications in their own services.
"""

from .compiler import (
    BLOCK_ROLE_CONTRACTS,
    CLASSROOM_CONSTRAINT_CONTRACT,
    COURSE_TEACHING_TYPES,
    LEARNING_PURPOSES,
    LESSON_TYPE_CONTRACTS,
    LESSON_TYPE_LABELS,
    SCHEMA_VERSION,
    SUBJECT_TYPES,
    SUBJECT_TYPE_CONTRACTS,
    TEACHING_DEFINITION,
    UNIVERSAL_TEACHING_PRINCIPLES,
    compile_course_semantics,
    compile_lesson_semantics,
    compile_teaching_block_contract,
    lesson_phase,
    order_teaching_blocks,
    recommend_lesson_type,
    resolve_course_teaching_type,
    resolve_learning_purpose,
    resolve_subject_standard_pack,
)
from .guidance import (
    compile_overall_teaching_guidance,
    compile_section_teaching_guidance,
    format_generation_teaching_guidance,
)
from .lesson_arrangement import (
    LESSON_TYPES,
    apply_lesson_arrangement_to_plan,
    normalize_lesson_arrangement,
    recommend_lesson_arrangement,
    validate_lesson_arrangement,
)
from .course_planning import (
    COURSE_SCALE_FULL_TERM,
    COURSE_SCALE_MICRO,
    COURSE_SCALE_UNIT,
    COURSE_SCALES,
    COURSE_TYPE_CONTRACTS,
    COURSE_TYPES,
    COVERAGE_STATUS_COMPLETE,
    COVERAGE_STATUS_PARTIAL,
    COVERAGE_STATUS_UNDECIDABLE,
    ENABLED_COURSE_TYPES,
    apply_course_type_brief,
    compatible_course_purpose,
    compile_course_type_brief,
    course_purpose_for_type,
    default_composition_style,
    ensure_course_type_enabled,
    judge_course_coverage,
    resolve_course_scale,
    resolve_course_type,
    resolve_subject_scope_baseline,
)

__all__ = [
    "BLOCK_ROLE_CONTRACTS", "CLASSROOM_CONSTRAINT_CONTRACT",
    "COURSE_TEACHING_TYPES", "LEARNING_PURPOSES", "LESSON_TYPE_CONTRACTS",
    "LESSON_TYPE_LABELS", "SCHEMA_VERSION", "SUBJECT_TYPES",
    "SUBJECT_TYPE_CONTRACTS", "TEACHING_DEFINITION",
    "UNIVERSAL_TEACHING_PRINCIPLES", "compile_course_semantics",
    "compile_lesson_semantics", "compile_teaching_block_contract",
    "lesson_phase", "order_teaching_blocks", "recommend_lesson_type",
    "resolve_course_teaching_type", "resolve_learning_purpose",
    "resolve_subject_standard_pack", "compile_overall_teaching_guidance",
    "compile_section_teaching_guidance", "format_generation_teaching_guidance",
    "LESSON_TYPES", "apply_lesson_arrangement_to_plan", "normalize_lesson_arrangement",
    "recommend_lesson_arrangement", "validate_lesson_arrangement",
    "COURSE_SCALE_FULL_TERM", "COURSE_SCALE_MICRO", "COURSE_SCALE_UNIT",
    "COURSE_SCALES", "COURSE_TYPE_CONTRACTS", "COURSE_TYPES",
    "COVERAGE_STATUS_COMPLETE", "COVERAGE_STATUS_PARTIAL",
    "COVERAGE_STATUS_UNDECIDABLE", "ENABLED_COURSE_TYPES",
    "apply_course_type_brief", "compatible_course_purpose",
    "compile_course_type_brief", "course_purpose_for_type",
    "default_composition_style", "ensure_course_type_enabled",
    "judge_course_coverage", "resolve_course_scale", "resolve_course_type",
    "resolve_subject_scope_baseline",
]
