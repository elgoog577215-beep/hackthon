"""Read only the requested course/lecture registry identities, not their content."""
import hashlib
import json
from pathlib import Path

course = "afb29754-6842-437b-af1b-5866bfb53b41"
scope = "teacher-lesson-" + hashlib.sha256(f"{course}:L1-1".encode()).hexdigest()[:20]
root = Path("/opt/lingzhi/state/backend-data/teaching_representations")
for label, key in (("canonical", course), ("lecture", scope)):
    digest = hashlib.sha256(json.dumps({"course_id": key}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:24]
    path = root / f"course_{digest}.json"
    value = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    print(json.dumps({"event": "registry_identity", "scope": label, "exists": path.exists(),
        "source_identity_matches": value.get("course_id") == course,
        "legacy_identity_matches": value.get("course_id") == scope,
        "representations": len(value.get("representations", [])), "specs": len(value.get("specs", []))}))
