"""Mechanical completeness gate over separately recorded semantic reviews.

This gate verifies review coverage and revision binding; it cannot itself prove
that a reviewer understood C or that a misconception exists in real learners.
"""
from .pipeline import digest


def sample_gate(topics, reviews, coverage_ids):
    problems=[]
    if set(topics)!={"types","if","for"} or set(reviews)!=set(topics):
        return {"passed":False,"problems":["topic_set_mismatch"]}
    for name,doc in topics.items():
        review=reviews[name]
        points={p["id"]:p for p in doc["core"]["points"]}
        checks={c["point_id"]:c for c in doc["primary_checks"]}
        relations={r["id"]:r for r in doc["relations"]}
        categories={c["id"]:c for c in doc["core"]["categories"]}
        roots=[c["id"] for c in categories.values() if c["parent_id"] is None]
        if roots!=[doc["core"]["root_id"]] or len(categories)!=len(doc["core"]["categories"]) or len(points)!=len(doc["core"]["points"]):
            problems.append(name+":tree_identity")
        for cid in categories:
            current=cid;seen=set()
            while current is not None:
                if current in seen or current not in categories:
                    problems.append(name+":tree_parent_or_cycle");break
                seen.add(current);current=categories[current]["parent_id"]
        if any(p["parent_id"] not in categories for p in points.values()):problems.append(name+":point_parent")
        if any(r["source_id"] not in points or r["target_id"] not in points for r in relations.values()):problems.append(name+":relation_endpoint")
        if any(not set(a["knowledge_ids"])<=set(points) for a in doc["core"].get("applications",[])):problems.append(name+":application_refs")
        if not points or set(points)!=set(checks) or len(checks)!=len(doc["primary_checks"]):
            problems.append(name+":check_coverage")
        for collection,actual in (("points",points),("checks",checks),("relations",relations)):
            recorded=review.get(collection,{})
            if set(recorded)!=set(actual):problems.append(name+":"+collection+"_review_coverage")
            for eid,entity in actual.items():
                item=recorded.get(eid,{})
                if item.get("status")!="accepted" or item.get("hash")!=digest(entity):
                    problems.append(name+":"+collection+":unreviewed_or_stale:"+eid)
        valid_refs=set(points)|{a["id"] for a in doc["core"].get("applications",[])}
        if set(review.get("coverage",{}))!=set(coverage_ids[name]):problems.append(name+":coverage_review_missing")
        for cid,item in review.get("coverage",{}).items():
            if item.get("status")!="covered" or not item.get("refs") or not set(item["refs"])<=valid_refs:
                problems.append(name+":coverage:"+cid)
        if not review.get("source_facts") or any(not f.get("refs") or not set(f["refs"])<=valid_refs or f.get("status")!="covered" for f in review["source_facts"]):
            problems.append(name+":source_fact_gap")
        if not doc["diagnostic"]["grade"]["numeric_contract_passed"] or review.get("diagnostic_plan_hash")!=digest(doc["diagnostic"]["plan"]) or not review.get("diagnostic_semantics_accepted"):
            problems.append(name+":diagnostic")
        if doc.get("check_intake_errors") or doc.get("repair_unresolved"):
            problems.append(name+":unresolved")
    return {"passed":not problems,"problems":problems,
        "level":"reviewed_three_topic_sample_only","teacher_adopted":False,"production_ready":False}
