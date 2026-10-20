"""Versioned point diagnostics shared by repair prompts, schemas and validation."""
from copy import deepcopy
import re

from course_repository import CourseDocumentConflict


class KnowledgePointValidationError(CourseDocumentConflict):
    def __init__(self, diagnostics):
        self.diagnostics = diagnostics
        super().__init__('；'.join(dict.fromkeys(d['message'] for d in diagnostics)))


def correction_plan(point, diagnostics):
    narrow = {'source_subject': ('subject', 'left_subject', 'right_subject', 'conditions'), 'undefined_quantity': ('conditions',)}
    codes = {d['code'] for d in diagnostics if d['code'] != 'invalid_short_statement'}
    expression_only = not codes and any(d['code'] == 'invalid_short_statement' for d in diagnostics)
    editable = sorted({field for code in codes for field in narrow.get(code, ()) if field in point})
    restricted = bool(codes) and codes <= narrow.keys()
    forms = ['definition'] if codes & {'joint_definition', 'incomplete_method'} else (
        ['fact', 'comparison'] if codes & {'cost_property', 'compound_property'} else [point.get('form')])
    return {'schema_version': 'knowledge_correction_plan_v1', 'diagnostics': deepcopy(diagnostics), 'expression_only': expression_only,
            'editable_fields': [] if expression_only else editable if restricted else sorted(point),
            'fixed_fields': {k: deepcopy(v) for k, v in point.items() if expression_only or restricted and k not in editable},
            'required_symbols': sorted({s for d in diagnostics for s in d.get('symbols', [])}),
            'allowed_forms': forms,
            'context_allowed': 'concrete_instance' in codes or bool(re.search(r'\b[nmd]\s*=\s*\d+', str(point.get('property', '')))),
            'source_issue_allowed': 'source_subject' in codes,
            'single_point': restricted}
