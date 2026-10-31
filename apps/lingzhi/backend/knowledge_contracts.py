"""Knowledge value contracts and parsing without orchestration."""
import json
import re
from pathlib import Path
from datetime import datetime,timezone
from course_errors import CourseDocumentConflict

WORKFLOW="knowledge_first_c17_v1"
GENERIC_WORKFLOW="knowledge_first_generic_v1"
WORKFLOWS={WORKFLOW,GENERIC_WORKFLOW}
TREE_JOB="course_knowledge_tree_generation"
HANDOUT_JOB="knowledge_first_handout_generation"
JOB_TYPES={TREE_JOB,HANDOUT_JOB}
ACTIVE={"pending","running"}

def material():
    return json.loads((Path(__file__).parent / "resources/knowledge_first/c17.json").read_text(encoding="utf-8"))


def now():
    return datetime.now(timezone.utc).isoformat()


def parse_response(text, *, handout_sources=False):
    """Accept a single surrounding JSON fence, never extract partial objects."""
    clean = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*\n([\s\S]*?)\n```", clean)
    class SourceKeys(list):
        pass
    normalizations = []
    def unique_object(pairs):
        if handout_sources and len(pairs) > 1 and all(k == "key" and isinstance(v, str) and re.fullmatch(r"S[1-9][0-9]*", v) for k, v in pairs):
            return SourceKeys(v for _, v in pairs)
        obj = {}
        for key, value in pairs:
            require(key not in obj, "模型 JSON 含重复字段")
            obj[key] = value
        return obj
    value = json.loads(fenced.group(1) if fenced else clean, object_pairs_hook=unique_object)
    if not handout_sources:
        return value
    def normalize(item):
        require(not isinstance(item, SourceKeys), "模型 JSON 含重复字段")
        if isinstance(item, list):
            return [normalize(v) for v in item]
        if not isinstance(item, dict):
            return item
        result = {}
        for key, nested in item.items():
            if key == "sources" and isinstance(nested, list) and not isinstance(nested, SourceKeys):
                refs = []
                for ref in nested:
                    if isinstance(ref, SourceKeys):
                        refs.extend({"key": v} for v in ref)
                        normalizations.append("expanded_repeated_source_keys")
                    elif isinstance(ref, str):
                        refs.append({"key": ref})
                    else:
                        refs.append(normalize(ref))
                result[key] = refs
            else:
                result[key] = normalize(nested)
        return result
    value = normalize(value)
    if isinstance(value, dict):
        value["_format_normalizations"] = sorted(set(normalizations))
    return value


def require(condition, message):
    if not condition:
        raise CourseDocumentConflict(message)


def knowledge_revision(raw):
    return str((raw.get("course_knowledge_base") or {}).get("revision_id") or "")
