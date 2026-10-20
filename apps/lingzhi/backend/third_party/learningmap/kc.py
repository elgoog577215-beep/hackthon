# Vendored from ai-for-edu/LearningMAP @ bb17f6a7e8c105248d80126b2bf07ff07209b83f
# Apache-2.0; selected definitions unchanged. See UPSTREAM.md.
from collections import defaultdict
from pydantic import BaseModel, Field


def group_questions_by_route(questions: dict) -> dict[str, list[dict]]:
    """Invert questions dict so each KC full-route maps to its questions.

    Each output item is the original question dict enriched with an "id" key
    so downstream logging can record which source questions were sampled.
    """
    groups: dict[str, list[dict]] = defaultdict(list)
    for qid, q in questions.items():
        item = dict(q)
        item["id"] = qid
        for route in q.get("kc_routes", []):
            groups[route].append(item)
    # preserve insertion order when iterated
    return dict(groups)


def sample_questions(items: list[dict], cap: int = 12) -> list[dict]:
    """Deterministic stratified sample by `type`.

    Rules:
    - if len(items) <= cap: return sorted by id (all items)
    - else: allocate cap slots across types proportionally (floor),
      distribute the remainder to the largest groups (ties broken by type
      name for determinism), then within each group take a uniform-step
      slice of the id-sorted items.
    """

    def sort_key(item: dict) -> tuple:
        """Sort by id, trying numeric sort first, falling back to string."""
        item_id = item["id"]
        try:
            return (0, int(item_id))
        except ValueError:
            return (1, item_id)

    if len(items) <= cap:
        return sorted(items, key=sort_key)

    # bucket by type, sort each bucket by id for determinism
    buckets: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        buckets[item["type"]].append(item)
    for t in buckets:
        buckets[t].sort(key=sort_key)

    total = len(items)
    # floor quota per type
    quotas: dict[str, int] = {t: (cap * len(buckets[t])) // total for t in buckets}
    assigned = sum(quotas.values())
    remainder = cap - assigned
    # distribute remainder to largest buckets (tie-break by type name ascending)
    order = sorted(buckets.keys(), key=lambda t: (-len(buckets[t]), t))
    for t in order:
        if remainder == 0:
            break
        quotas[t] += 1
        remainder -= 1

    # uniform-step pick from each bucket
    picked: list[dict] = []
    for t in sorted(buckets.keys()):  # deterministic iteration
        q = quotas[t]
        if q == 0:
            continue
        bucket = buckets[t]
        step = len(bucket) // q
        picked.extend(bucket[i * step] for i in range(q))

    return sorted(picked, key=sort_key)


class KCSkill(BaseModel):
    """LLM-generated, question-bank-grounded context for one knowledge component.

    The ``description`` field mirrors the ``description`` frontmatter of
    ``skills/*/SKILL.md`` — a one-line index string a consuming model can
    read to decide how / when this skill applies. The other four fields
    are the subject-matter payload.
    """

    description: str = Field(
        ...,
        description=(
            "One-sentence index + applicable scenario (40-100 chars, in English). "
            "Must state both 'what this skill covers' and 'when to invoke it'. "
            "Example: 'Use when a student confuses step-by-step counting with "
            "classification counting in multi-step problems. Grounded in the "
            "multiplication principle.'"
        ),
    )
    assessment_focus: str = Field(..., description="Core concepts / sub-skills / thinking points, 80-150 chars")
    assessment_format: str = Field(
        ..., description="Question-type distribution + common stem patterns + scenario conventions, 80-150 chars"
    )
    common_mistakes: str = Field(..., description="High-frequency errors inferred from analysis, 50-120 chars")
    difficulty_cues: str = Field(..., description="Numeric magnitude / nesting depth / multi-step complexity, 50-100 chars")
