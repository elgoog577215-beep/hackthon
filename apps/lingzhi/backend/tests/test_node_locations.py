"""生成进度的位置推导：教师看到的必须是"第几章第几节"。"""

from jobs.manager import build_node_locations


def _nodes(*specs):
    return [
        {"node_id": nid, "node_level": level, "node_name": name}
        for nid, level, name in specs
    ]


def test_章节序号按顺序推导且跨章重新计数():
    locations = build_node_locations(_nodes(
        ("c1", 1, "力学"),
        ("c1s1", 2, "速度"),
        ("c1s2", 2, "加速度"),
        ("c2", 1, "热学"),
        ("c2s1", 2, "内能"),
    ))

    assert locations["c1s2"]["label"] == "第1章第2节 · 加速度"
    # 第二章的第一节必须回到 1，而不是接着上一章数成第 3 节
    assert locations["c2s1"]["label"] == "第2章第1节 · 内能"
    assert locations["c2s1"]["chapter_number"] == 2
    assert locations["c2s1"]["section_number"] == 1
    assert locations["c2s1"]["chapter_name"] == "热学"


def test_章节点自身也有位置():
    locations = build_node_locations(_nodes(("c1", 1, "力学")))
    assert locations["c1"]["label"] == "第1章 · 力学"
    assert locations["c1"]["section_number"] is None


def test_没有章的平铺课程退化成只报节号():
    # 早期课程与部分导入课程只有平铺小节，这时不能显示"第0章"
    locations = build_node_locations(_nodes(
        ("s1", 2, "开篇"),
        ("s2", 2, "收束"),
    ))
    assert locations["s1"]["label"] == "第1节 · 开篇"
    assert locations["s2"]["label"] == "第2节 · 收束"
    assert locations["s1"]["chapter_number"] is None


def test_小节重名时位置仍能区分():
    # 只报小节名说不清进度走到整门课的什么位置——这正是要加位置的原因
    locations = build_node_locations(_nodes(
        ("c1", 1, "第一部分"), ("c1s1", 2, "练习"),
        ("c2", 1, "第二部分"), ("c2s1", 2, "练习"),
    ))
    assert locations["c1s1"]["label"] != locations["c2s1"]["label"]


def test_缺名字与缺id的节点不会产出半截标签():
    locations = build_node_locations([
        {"node_id": "c1", "node_level": 1, "node_name": ""},
        {"node_id": "", "node_level": 2, "node_name": "无 id 会被跳过"},
        {"node_id": "c1s1", "node_level": 2, "node_name": ""},
    ])
    assert locations["c1"]["label"] == "第1章"
    assert locations["c1s1"]["label"] == "第1章第1节"
    assert "" not in locations
