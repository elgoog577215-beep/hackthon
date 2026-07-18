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
    knowledge_libraries,
    learning_assets,
    learning_continuation,
    learning_progress,
    learning_records,
    learning_runtime,
    learning_snapshots,
    markdown_import,
    materials,
    nodes,
    practice,
    question_bank,
    review,
    tasks,
)

__all__ = [name for name in globals() if not name.startswith("_")]
