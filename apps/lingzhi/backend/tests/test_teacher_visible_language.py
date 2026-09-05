from teacher_visible_language import has_unnatural_system_language


def test_blocks_system_design_phrases_from_teacher_visible_text():
    for value in (
        "冻结知识边界后开始教学",
        "形成职责闭环",
        "解决当前结构性阻力",
        "形成教学抓手",
        "拉通教学链路",
    ):
        assert has_unnatural_system_language(value)


def test_does_not_block_normal_subject_language():
    for value in (
        "判断整数集对加法是否满足闭合性",
        "观察冻结切片中的细胞结构",
        "代码围栏没有成对结束",
    ):
        assert not has_unnatural_system_language(value)
