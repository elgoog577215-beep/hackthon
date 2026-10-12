"""Generate explicitly synthetic, read-only UI snapshots using the production projector."""
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from knowledge_mastery import build_knowledge_profile  # noqa: E402


def generate():
    names = [
        ("types", "整数除法会截去小数部分", "整数相除时，结果取整数部分；之后赋给浮点变量不能恢复已丢失的小数。"),
        ("types", "初始化发生在变量创建时", "区分变量首次创建时的初始化与之后替换当前值的赋值操作。"),
        ("types", "中间结果也要在类型范围内", "最终变量足够大，不代表表达式的中间运算不会溢出。"),
        ("condition", "零值与非零值决定分支选择", "C 语言条件表达式中，零表示假，非零表示真。"),
        ("condition", "比较相等使用 ==", "区分赋值运算与相等比较在条件中的含义。"),
        ("condition", "else 与最近的可匹配 if 配对", "根据语法结构判断分支归属，不仅凭缩进判断。"),
        ("condition", "区间端点应有明确归属", "设计条件时检查相邻区间的边界是否遗漏或重复。"),
        ("loops", "初始化在进入循环时执行一次", "区分循环的初始化、条件检查、循环体与迭代更新。"),
        ("loops", "条件在每次循环体执行前检查", "初始条件不成立时，for 循环体可能一次也不执行。"),
        ("loops", "迭代更新发生在循环体之后", "跟踪每次循环结束后的变量变化，再判断下一轮条件。"),
    ]
    base = {"lifecycle_status": "active", "revision_id": "demo-baseline-1", "concept_groups": [
        {"concept_group_id": "types", "name": "变量与类型"}, {"concept_group_id": "condition", "name": "条件分支"}, {"concept_group_id": "loops", "name": "循环控制"}],
        "knowledge_points": [{"knowledge_id": f"demo-k{i}", "revision_id": f"demo-r{i}", "name": name, "statement": statement,
                              "primary_concept_group_id": group, "granularity_status": "atomic", "status": "active", "section_refs": []}
                             for i, (group, name, statement) in enumerate(names, 1)]}
    attempts, events, cases = [], [], []

    def snapshot(label, en, note, note_en):
        cases.append({"label": label, "label_en": en, "note": note, "note_en": note_en,
                      "profile": build_knowledge_profile(base, course_id="demo-c", course_version_id="demo-v1", user_id="demo-u", attempts=attempts, events=events)})

    def answer(kid, passed=True, assisted=False, qid=None):
        number = len(attempts) + 1
        attempts.append({"attempt_id": f"demo-a{number}", "user_id": "demo-u", "course_id": "demo-c", "course_version_id": "demo-v1",
                         "task_revision_id": qid or f"demo-q{number}", "concept_ids": [f"demo-k{kid}"], "knowledge_revision_refs": {f"demo-k{kid}": f"demo-r{kid}"},
                         "status": "graded", "updated_at": f"2026-10-11T10:{number:02}:00+08:00", "result": {"passed": passed, "grading_confidence": .95, "support_level": 2 if assisted else 0}})

    snapshot("初次进入", "Start", "10 个元知识点都未评估。进度为 0%，不代表学生完全不会。", "All 10 points are unassessed. Zero verified progress does not mean zero ability.")
    events.append({"event_id": "demo-note", "event_type": "learning_record_created", "user_id": "demo-u", "course_id": "demo-c", "course_version_id": "demo-v1", "concept_ids": ["demo-k1"]})
    snapshot("保存笔记", "Save a note", "保存了一条关于整数除法的笔记。活动被记录，掌握分不自动增加。", "A note on integer division is recorded. Saving it does not automatically increase mastery.")
    events.append({"event_id": "demo-question", "event_type": "assistant_question_submitted", "user_id": "demo-u", "course_id": "demo-c", "course_version_id": "demo-v1", "concept_ids": ["demo-k1"]})
    snapshot("向 AI 提问", "Ask AI", "主动提问不扣分。需要通过自己的解释或作答验证理解。", "Asking for help does not lower mastery. A checked explanation or answer provides evidence.")
    answer(1)
    snapshot("独立答对", "Pass independently", "一次独立检查通过：整数除法参考值 66.7%，证据仍有限。", "One independent pass: integer division reaches 66.7%, with limited evidence.")
    answer(1, qid="demo-q1")
    snapshot("重复同题", "Repeat the item", "同一道题采用最新结果，重复作答没有再加分。", "The latest result replaces the earlier result for the same item; no extra credit.")
    answer(1)
    answer(1)
    snapshot("通过变式", "Pass new variants", "三道不同检查独立通过，参考值升至 80%，开始有较充分的掌握证据。", "Three distinct independent checks raise the estimate to 80%, with stronger evidence.")
    answer(1, False)
    snapshot("新题未通过", "Fail a new check", "新的独立检查未通过，参考值降为 66.7%。保留已有通过证据，不直接贴上薄弱标签。", "A new failed check lowers the estimate to 66.7%. Previous passes remain; one failure is not a stable weakness.")
    answer(2, assisted=True)
    snapshot("提示后完成", "Pass with help", "初始化知识点在提示下通过：记录正向证据，但权重较低，也不标为独立掌握。", "A supported pass provides lower-weight evidence and does not establish independent mastery.")
    for kid in [4, 5, 8]:
        for _ in range(3): answer(kid)
    answer(7, False)
    answer(7, False)
    snapshot("学习一段时间后", "After more learning", "不同分支出现差异。点击知识点圆球查看依据；尚未评估的点仍保持未知。", "Branches now differ. Select a knowledge point to inspect its evidence; unassessed points remain unknown.")
    return {"synthetic": True, "title": "C 语言程序设计", "title_en": "C programming", "cases": deepcopy(cases)}


if __name__ == "__main__":
    output = ROOT / "frontend/src/demo/knowledge-profile.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(generate(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)
