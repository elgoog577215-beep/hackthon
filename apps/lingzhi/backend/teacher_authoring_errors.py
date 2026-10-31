"""Shared authoring error contract, without the authoring service."""
from typing import Any
class TeacherLessonAuthoringError(RuntimeError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}
