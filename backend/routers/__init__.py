"""Production API router package."""

from routers import (
    ai_teacher,
    assistant,
    block_regeneration,
    code_execution,
    course_acceptance,
    course_versions,
    courses,
    diagnostics,
    diagrams,
    learner_model,
    learning_assets,
    learning_continuation,
    learning_progress,
    learning_records,
    learning_runtime,
    learning_snapshots,
    llm_profiles,
    markdown_import,
    materials,
    nodes,
    practice,
    presentations,
    review,
    tasks,
)

__all__ = [name for name in globals() if not name.startswith("_")]
