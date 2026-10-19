"""Versioned point diagnostics shared by repair prompts, schemas and validation."""
from copy import deepcopy

from course_repository import CourseDocumentConflict


class KnowledgePointValidationError(CourseDocumentConflict):
    def __init__(self, diagnostics):
        self.diagnostics = diagnostics
        super().__init__('；'.join(dict.fromkeys(d['message'] for d in diagnostics)))


def correction_plan(point, diagnostics):
    narrow = {'source_subject': ('subject', 'left_subject', 'right_subject'), 'undefined_quantity': ('conditions',)}
    codes = {d['code'] for d in diagnostics}
    editable = sorted({field for code in codes for field in narrow.get(code, ()) if field in point})
    restricted = bool(codes) and codes <= narrow.keys()
    return {'schema_version': 'knowledge_correction_plan_v1', 'diagnostics': deepcopy(diagnostics),
            'editable_fields': editable if restricted else sorted(point),
            'fixed_fields': {k: deepcopy(v) for k, v in point.items() if restricted and k not in editable},
            'required_symbols': sorted({s for d in diagnostics for s in d.get('symbols', [])}),
            'single_point': restricted}
