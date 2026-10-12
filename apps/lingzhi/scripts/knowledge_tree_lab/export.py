"""Export the experimental candidate and its separate, nonblind review together."""
import argparse
from collections import defaultdict
from copy import deepcopy
import json
from pathlib import Path
from .pipeline import read, save, digest


def export(root, destination):
    review = read(root / "assessment.json")
    course_id = "course_c17_lab_20261011_v3"
    result = {"schema": "knowledge_tree_lab_collection_v3", "course_id": course_id,
              "title": "C17 三组知识树实验候选", "state": "candidate", "adoptable": False,
              "model": read(root / "manifest.json")["model"],
              "notice": "千问自动生成原文，包含已知错误；评语由Codex非盲复核。不是教师审定教材，不可导入正式课程或直接生成讲义。",
              "categories": [{"id": course_id, "parent_id": None, "name": "C17 三组样板"}],
              "points": [], "checks": [], "relations": [], "misconceptions": [], "topic_receipts": [],
              "review": review, "sources": read(root / "fixtures.json")}
    for topic in ("types", "if", "for"):
        doc = deepcopy(read(root / topic / "final.json"))
        next(c for c in doc["categories"] if c["id"] == doc["root_id"])["parent_id"] = course_id
        for collection in ("categories", "points", "checks", "relations", "misconceptions"):
            result[collection].extend(doc[collection])
        result["topic_receipts"].append({"topic": topic, "root_id": doc["root_id"],
            "final_hash": digest(read(root / topic / "final.json")),
            "atomic_revision": read(root / topic / "atomize.receipt.json"),
            "pending_checks": doc["pending_checks"],
            "structure_rejections": read(root / topic / "final-feedback.json")["structure"]})
    ids = [e["id"] for k in ("categories", "points", "checks", "relations", "misconceptions") for e in result[k]]
    assert len(ids) == len(set(ids))
    category_ids = {c["id"] for c in result["categories"]}
    point_ids = {p["id"] for p in result["points"]}
    check_ids = {c["id"] for c in result["checks"]}
    assert sum(c["parent_id"] is None for c in result["categories"]) == 1
    assert all(c["parent_id"] is None or c["parent_id"] in category_ids for c in result["categories"])
    assert all(p["parent_id"] in category_ids for p in result["points"])
    assert all(set(c["knowledge_ids"]) <= point_ids for c in result["checks"])
    assert all(r["source_id"] in point_ids and r["target_id"] in point_ids for r in result["relations"])
    assert all(m[k] in check_ids for m in result["misconceptions"] for k in ("symptom_check_id", "diagnostic_check_id", "retest_check_id"))
    destination.mkdir(parents=True, exist_ok=True)
    save(destination / "C语言三组知识树千问候选.json", result)
    reviews = {p["point_id"]: p for t in review["topics"].values() for p in t["point_reviews"]}
    summary = review["summary"]
    lines = ["# C语言三组知识树千问候选", "", result["notice"], "",
             f"{summary['points']} 个候选点；{summary['granularity_needs_revision']} 个需细分/重分类；"
             f"范围清单中 {summary['coverage_covered']} 项明确覆盖、{summary['coverage_partial']} 项部分覆盖。每点的核对意见附在原文后，未人工替换千问答案。", "",
             "[完整 JSON](C语言三组知识树千问候选.json)", ""]
    children = defaultdict(list)
    leaves = defaultdict(list)
    for c in result["categories"]:
        children[c["parent_id"]].append(c)
    for p in result["points"]:
        leaves[p["parent_id"]].append(p)
    def tree(cid, depth):
        for category in children[cid]:
            lines.append("  " * depth + "- " + category["name"])
            tree(category["id"], depth + 1)
        for point in leaves[cid]:
            lines.append("  " * depth + "- " + point["name"] + " → " + point["id"])
    lines += ["## 树形目录", "", "```text"]
    tree(course_id, 0)
    lines += ["```", "", "## 元知识候选与核对", ""]
    for p in result["points"]:
        r = reviews[p["id"]]
        checks = [c for c in result["checks"] if p["id"] in c["knowledge_ids"]]
        lines += ["### " + p["name"], "", "ID：`" + p["id"] + "`", "",
                  "**模型命题：** " + p["statement"], "", "**条件：** " + "；".join(p["conditions"]), "",
                  "**元问题：** " + p["question"], "", "**模型回答（待审）：** " + p["answer"], "",
                  "**颗粒度核对：** " + r["granularity_reason"], "",
                  "**内容核对：** " + (r["content_issue"] or "本次复核未发现明显命题错误；不等于教师已审定。"), "",
                  "**来源：** " + ", ".join(p["source_refs"]), "",
                  "**教学检查：** " + (", ".join(c["key"] for c in checks) if checks else "尚未生成独立教学检查"), ""]
    lines += ["## 教学检查", ""]
    for c in result["checks"]:
        lines += ["### " + c["key"], "", c["question"], ""]
        if c["kind"] == "runtime":
            lines += ["```c", c["code"], "```", "", "模型预测：`" + repr(c["predicted_stdout"]) + "`", "",
                      "实测答案：`" + repr(c.get("verified_answer", {}).get("value")) + "`", "",
                      "状态：" + c["evidence_status"] + "；仅证明该样例在本机执行结果。", ""]
        else:
            lines += ["静态检查，未执行，回答待审。", ""]
        lines += ["模型解释（待审）：" + c["explanation"], ""]
    lines += ["## 易错候选", ""]
    for m in result["misconceptions"]:
        lines += ["### " + m["id"], "", "- 错因 A：" + m["hypothesis_a"], "- 错因 B：" + m["hypothesis_b"],
                  "- 程序阻断原因：" + ", ".join(m["gate_problems"]), "",
                  "三题答案引用同一个代码回执，不能把本条作为已验证的学生诊断。", ""]
    (destination / "C语言三组知识树千问候选.md").write_text("\n".join(lines), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    data = export(args.root, args.destination)
    print(json.dumps({"points": len(data["points"]), "adoptable": data["adoptable"]}))
