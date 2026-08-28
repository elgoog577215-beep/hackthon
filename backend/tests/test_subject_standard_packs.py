from teaching_design.standards import (
    SUBJECT_ARTIFACT_LANGUAGE,
    SUBJECT_STANDARD_PACKS,
    resolve_subject_standard_pack,
    validate_subject_standard_registry,
)


def test_registry_is_complete_and_profile_ids_are_unique():
    assert set(SUBJECT_STANDARD_PACKS) == {
        "general", "math_formal", "programming_engineering", "natural_science",
        "life_medical", "humanities_social", "language_learning", "business_career",
    }
    assert validate_subject_standard_registry() == []
    assert set(SUBJECT_ARTIFACT_LANGUAGE) == set(SUBJECT_STANDARD_PACKS)
    assert all(
        set(language) == {"outline", "lesson_plan", "script", "question_bank", "ppt"}
        for language in SUBJECT_ARTIFACT_LANGUAGE.values()
    )


def test_profiles_cover_representative_college_courses():
    cases = {
        "微积分": ("math_formal", "higher_mathematics"),
        "机器学习": ("programming_engineering", "data_ai"),
        "大学物理实验": ("natural_science", "physics"),
        "护理评估": ("life_medical", "nursing"),
        "中国古代史": ("humanities_social", "history_textual"),
        "学术英语写作": ("language_learning", "academic_language"),
        "公司财务管理": ("business_career", "finance_accounting"),
    }
    for hint, expected in cases.items():
        pack = resolve_subject_standard_pack("auto", discipline_hint=hint)
        assert (pack["subject_type"], pack["discipline_profile_id"]) == expected
        assert pack["professional_actions"]
        assert pack["canonical_artifacts"]
        assert set(pack["artifact_language"]) == {
            "outline", "lesson_plan", "script", "question_bank", "ppt",
        }


def test_explicit_family_limits_profile_resolution():
    pack = resolve_subject_standard_pack(
        "humanities_social",
        discipline_hint="人工智能时代的传播学",
    )
    assert pack["subject_type"] == "humanities_social"
    assert pack["discipline_profile_id"] == "social_science"


def test_each_subject_family_has_its_own_teacher_visible_language():
    scripts = {
        family_id: resolve_subject_standard_pack(family_id)["artifact_language"]["script"]
        for family_id in SUBJECT_STANDARD_PACKS
    }

    assert len(set(scripts.values())) == len(SUBJECT_STANDARD_PACKS)
    assert "逐步推导" in scripts["math_formal"]
    assert "边运行边解释" in scripts["programming_engineering"]
    assert "观察" in scripts["natural_science"] and "推断" in scripts["natural_science"]
    assert "史实、材料、观点和解释" in scripts["humanities_social"]
