"""Shared knowledge-workflow identifiers and conflict validation."""
from course_errors import CourseDocumentConflict

WORKFLOW = "knowledge_first_c17_v1"
GENERIC_WORKFLOW = "knowledge_first_generic_v1"
ACTIVE = {"pending", "running"}

def require(condition, message):
    if not condition:
        raise CourseDocumentConflict(message)
