from subject_ontology import resolve_subject_identity


def test_newton_second_law_resolves_to_classical_mechanics():
    identity = resolve_subject_identity({
        "course_name": "牛顿第二定律与受力分析",
        "generation_request": {
            "subject": "牛顿第二定律与受力分析",
        },
    })

    assert identity["subject_id"] == "physics.classical_mechanics"
    assert identity["root_name"] == "物理学"
