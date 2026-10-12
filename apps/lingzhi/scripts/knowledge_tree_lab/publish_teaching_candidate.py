"""Explicitly stage a frozen evaluation candidate in the existing job store.

No adoption, no body writes, no model calls. Back up and verify the two exact
course files before a narrowly scoped, source-checked candidate write.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import shutil
import sys

from .pipeline import read, save, digest


def publish(root):
    app = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(app / "backend"))
    from storage import storage
    from course_repository import CourseDocumentRepository
    from teacher_content_projection import authoring_repository
    from knowledge_first import TREE_JOB, ACTIVE, require
    manifest = read(root / "manifest.json")
    for name, expected in manifest["input_hashes"].items():
        require(hashlib.sha256((root/name).read_bytes()).hexdigest() == expected, "冻结输入已变化")
    cid = manifest["source_course_id"]
    repo = CourseDocumentRepository(storage)
    authoring = authoring_repository(storage)
    candidate = read(root / "teaching-candidate-tree.json")
    require(candidate["source_knowledge_revision"] == manifest["source_knowledge_revision"], "候选来源不匹配")
    raw = repo.load_raw(cid)
    require(candidate["knowledge_points"] == raw["course_knowledge_base"]["knowledge_points"], "禁止替换既有知识事实和身份")
    token = "teaching-eval-" + digest(candidate)[:20]
    with authoring._course_lock(cid):
        state = authoring.load(cid)
        prior = next((j for j in state["jobs"].values() if j.get("request_id") == token), None)
        if prior:
            print("Candidate already staged:", prior["id"])
            return
        require(not any(j.get("status") in ACTIVE for j in state["jobs"].values()), "课程有运行任务")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = root / ("backup-" + stamp)
        backup.mkdir()
        sources = [Path(storage._courses_dir) / (cid + ".json"), authoring.root / (cid + ".json")]
        receipts = []
        for i, source in enumerate(sources):
            target = backup / (str(i) + "-" + source.name)
            shutil.copy2(source, target)
            original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            require(hashlib.sha256(target.read_bytes()).hexdigest() == original_hash, "备份校验失败")
            receipts.append({"source": str(source), "backup": str(target), "sha256": original_hash})
        save(backup / "manifest.json", receipts)
        baseline_hash = digest(raw["course_knowledge_base"])
        body_hash = digest(state["lessons"])
        created = {}
        def commit(fresh):
            require(fresh["course_document_revision"] == manifest["source_document_revision"] and
                    fresh["course_knowledge_base"]["revision_id"] == manifest["source_knowledge_revision"], "课程来源发生变化")
            job = authoring.create_job(cid, "tree", job_type=TREE_JOB, request_id=token)
            created.update(authoring.update_job(cid, job["id"], status="completed", phase="candidate_review_required", progress=100,
                source_knowledge_revision=manifest["source_knowledge_revision"], source_document_revision=manifest["source_document_revision"],
                actor=fresh["owner_id"], model="qwen3.8-27b", model_calls=15, generation_source="explicit_frozen_evaluation_import",
                message="教学框架候选已保存；核验未通过，不能采用", checkpoint={"candidate": candidate}, stream_complete=True))
            return fresh
        storage.update_course_data(cid, commit)
        require(digest(repo.load_raw(cid)["course_knowledge_base"]) == baseline_hash, "正式知识树发生意外改变")
        require(digest(authoring.load(cid)["lessons"]) == body_hash, "讲义发生意外改变")
        save(root / "website-candidate-receipt.json", {"course_id": cid, "job_id": created["id"], "candidate_revision": candidate["revision_id"],
             "adopted": False, "baseline_unchanged": True, "handouts_unchanged": True, "backup": str(backup)})
        print("Staged review-only candidate", created["id"], "baseline/body unchanged")


if __name__ == "__main__":
    p=argparse.ArgumentParser();p.add_argument("root",type=Path);a=p.parse_args();publish(a.root)
