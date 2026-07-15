#!/usr/bin/env python3
"""Run the 8.4 standard-course learning chain through public HTTP APIs only."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_COURSE_ID = "4dcfe257-0955-49bb-ade4-dc6ed915bbfb"
DEFAULT_BASE_URL = "http://127.0.0.1:8010"


class AcceptanceFailure(RuntimeError):
    pass


class ApiClient:
    def __init__(self, base_url: str, user_id: str):
        self.base_url = base_url.rstrip("/")
        self.user_id = user_id

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        query: dict[str, Any] | None = None,
        expected: set[int] | None = None,
        device_id: str = "",
    ) -> tuple[int, dict[str, Any]]:
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{urlencode(query)}"
        headers = {"X-User-Id": self.user_id, "Accept": "application/json"}
        if device_id:
            headers["X-Device-Id"] = device_id
        body = None
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(url, data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=180) as response:
                status = response.status
                raw = response.read().decode("utf-8")
        except HTTPError as error:
            status = error.code
            raw = error.read().decode("utf-8")
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            data = {"raw": raw}
        allowed = expected or {200}
        if status not in allowed:
            raise AcceptanceFailure(f"{method} {path} returned {status}: {data}")
        return status, data

    def sse(self, path: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        url = f"{self.base_url}{path}"
        request = Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "X-User-Id": self.user_id,
                "Accept": "text/event-stream",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=240) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as error:
            raise AcceptanceFailure(
                f"POST {path} returned {error.code}: {error.read().decode('utf-8')}"
            ) from error
        events: list[dict[str, Any]] = []
        for block in raw.replace("\r\n", "\n").split("\n\n"):
            event_name = ""
            data_lines: list[str] = []
            for line in block.splitlines():
                if line.startswith("event:"):
                    event_name = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    data_lines.append(line.split(":", 1)[1].lstrip())
            if not event_name or not data_lines:
                continue
            try:
                event_data = json.loads("\n".join(data_lines))
            except json.JSONDecodeError:
                event_data = {"raw": "\n".join(data_lines)}
            events.append({"event": event_name, "data": event_data})
        return events


class MainChainAcceptance:
    def __init__(self, client: ApiClient, course_id: str, run_id: str):
        self.client = client
        self.course_id = course_id
        self.run_id = run_id
        self.path = f"/api/courses/{course_id}"
        self.evidence: list[dict[str, Any]] = []
        self.course: dict[str, Any] = {}
        self.nodes: list[dict[str, Any]] = []
        self.questions: list[dict[str, Any]] = []
        self.first_node: dict[str, Any] = {}
        self.second_node: dict[str, Any] = {}
        self.anchor: dict[str, Any] = {}
        self.failed_attempt_ids: list[str] = []

    def run(self) -> dict[str, Any]:
        self._baseline()
        self._progress_and_snapshot()
        self._records()
        workflow = self._practice_failures()
        workflow = self._diagnosis(workflow)
        self._remediation(workflow)
        self._chapter_completion()
        self._ai_teacher()
        _, preflight = self.client.request("GET", f"{self.path}/acceptance-preflight")
        self._require(preflight.get("status") == "ready", "strict preflight changed after learning chain")
        self._record("FINAL", {
            "preflight_status": preflight.get("status"),
            "blocking_count": len(preflight.get("blocking_issues") or []),
            "warning_count": len(preflight.get("warnings") or []),
        })
        return {
            "schema_version": "course_main_chain_acceptance_v1",
            "status": "passed",
            "run_id": self.run_id,
            "user_id": self.client.user_id,
            "course_id": self.course_id,
            "completed_at": _now(),
            "stages": self.evidence,
        }

    def _baseline(self) -> None:
        _, preflight = self.client.request("GET", f"{self.path}/acceptance-preflight")
        self._require(preflight.get("status") == "ready", "standard course is not strict ready")
        _, self.course = self.client.request("GET", self.path)
        self._require(self.course.get("current_course_version_id"), "current course version is missing")
        self.nodes = [
            node for node in self.course.get("nodes") or []
            if node.get("objective_revision_id") and node.get("content_blocks")
        ]
        self._require(len(self.nodes) >= 2, "at least two objective nodes are required")
        self.first_node, self.second_node = self.nodes[:2]
        source_block = next(
            (block for block in self.first_node.get("content_blocks") or [] if str(block.get("content") or "").strip()),
            None,
        )
        self._require(bool(source_block), "first objective has no non-empty content block")
        self.anchor = {
            "block_id": source_block.get("block_id"),
            "block_revision_id": source_block.get("block_revision_id"),
            "content_fingerprint": source_block.get("content_fingerprint"),
            "block_type": source_block.get("type") or "content",
            "title": source_block.get("title") or self.first_node.get("node_name"),
            "progress": 0.42,
            "text_quote": str(source_block.get("content") or "")[:240],
        }
        _, practice = self.client.request("GET", f"{self.path}/practice", query={"scope": "all"})
        self.questions = practice.get("questions") or []
        _, runtime = self.client.request("GET", f"{self.path}/learning-runtime")
        continuation = runtime.get("continuation") or {}
        action = continuation.get("primary_action") or {}
        context = runtime.get("context") or {}
        self._require(context.get("course_version_id") == self.course.get("current_course_version_id"), "runtime version mismatch")
        self._require(context.get("node_id") == self.first_node.get("node_id"), "first entry points to wrong node")
        self._require(action.get("action_type") == "start_objective", "first entry has wrong primary action")
        self._record("ENT", {
            "course_version_id": context.get("course_version_id"),
            "chapter_id": context.get("chapter_id"),
            "node_id": context.get("node_id"),
            "objective_revision_id": context.get("objective_revision_id"),
            "primary_action": action.get("action_type"),
            "runtime_revision_id": runtime.get("runtime_revision_id"),
        })

    def _progress_and_snapshot(self) -> None:
        node_id = str(self.first_node.get("node_id"))
        self.client.request("POST", f"{self.path}/learning-progress/nodes/{node_id}", {"action": "start"})
        _, completed = self.client.request(
            "POST", f"{self.path}/learning-progress/nodes/{node_id}", {"action": "complete_reading"}
        )
        progress_node = self._progress_node(completed.get("projection") or {}, node_id)
        self._require(progress_node.get("reading_status") == "learned", "explicit reading completion was not projected")
        self._require(progress_node.get("mastery_status") != "mastered", "reading completion incorrectly granted mastery")

        snapshot_payload = {
            "expected_revision": 0,
            "course_version_id": self.course.get("current_course_version_id"),
            "node_id": node_id,
            "node_name": self.first_node.get("node_name") or "",
            "content_anchor": self.anchor,
            "session": {
                "session_id": f"{self.run_id}-session",
                "device_id": "acceptance-main-device-a",
                "started_at": _now(),
            },
            "task_state": {
                "kind": "reading",
                "object_id": self.first_node.get("objective_revision_id"),
                "task_revision_id": self.first_node.get("objective_revision_id"),
                "status": "active",
                "return_node_id": node_id,
            },
            "interaction_state": {},
            "fallback_scroll_top": 360,
            "activity_at": _now(),
            "source": "live",
        }
        _, saved = self.client.request(
            "PUT", f"{self.path}/learning-snapshot", snapshot_payload,
            device_id="acceptance-main-device-a",
        )
        snapshot = saved.get("snapshot") or {}
        self._require(snapshot.get("revision") == 1, "initial snapshot revision is not 1")
        _, restored = self.client.request(
            "GET", f"{self.path}/learning-snapshot", device_id="acceptance-main-device-b"
        )
        restored_snapshot = restored.get("snapshot") or {}
        self._require(restored_snapshot.get("snapshot_id") == snapshot.get("snapshot_id"), "device B did not restore device A snapshot")
        self._require((restored.get("resolution") or {}).get("status") == "exact", "semantic anchor did not resolve exactly")
        conflict_status, conflict = self.client.request(
            "PUT", f"{self.path}/learning-snapshot", snapshot_payload,
            expected={409}, device_id="acceptance-main-device-b",
        )
        self._require(conflict_status == 409, "stale snapshot revision did not conflict")
        self._record("PRG", {
            "node_id": node_id,
            "reading_status": progress_node.get("reading_status"),
            "mastery_status": progress_node.get("mastery_status"),
        })
        self._record("SNP", {
            "snapshot_id": snapshot.get("snapshot_id"),
            "snapshot_revision": snapshot.get("revision"),
            "saved_device": (snapshot.get("session") or {}).get("device_id"),
            "restored_on": "acceptance-main-device-b",
            "anchor_resolution": (restored.get("resolution") or {}).get("status"),
            "stale_write_status": conflict_status,
            "conflict_code": ((conflict.get("detail") or {}).get("code")),
        })

    def _records(self) -> None:
        node_id = str(self.first_node.get("node_id"))
        prefix = self.run_id[:40]
        common = {
            "node_id": node_id,
            "node_name": self.first_node.get("node_name") or "",
            "anchor": self.anchor,
            "origin": "acceptance_8_4",
        }
        created: dict[str, dict[str, Any]] = {}
        payloads = {
            "note": {"record_id": f"{prefix}-note", "record_type": "note", "title": "向量关系笔记", "content": "线性相关需要存在不全为零的系数使线性组合为零。"},
            "issue": {"record_id": f"{prefix}-issue", "record_type": "issue", "title": "待澄清：几何与代数判据", "content": "需要核对秩判据和几何解释的关系。"},
            "review_task": {"record_id": f"{prefix}-review", "record_type": "review_task", "title": "复查线性相关判据", "content": "完成本章后复查。"},
            "bookmark": {"record_id": f"{prefix}-bookmark", "record_type": "bookmark", "title": "线性相关定义", "content": "返回定义位置。"},
        }
        for kind, payload in payloads.items():
            _, created[kind] = self.client.request("POST", f"{self.path}/learning-records", {**common, **payload})

        _, note_updated = self.client.request(
            "PATCH", f"{self.path}/learning-records/{created['note']['record_id']}",
            {"expected_revision": 1, "title": "向量关系笔记（已核对）"},
        )
        conflict_status, _ = self.client.request(
            "PATCH", f"{self.path}/learning-records/{created['note']['record_id']}",
            {"expected_revision": 1, "title": "过期客户端覆盖"}, expected={409},
        )
        self.client.request(
            "POST", f"{self.path}/learning-records/{created['note']['record_id']}/archive",
            {"expected_revision": note_updated.get("revision")},
        )
        _, issue = self.client.request(
            "PATCH", f"{self.path}/learning-records/{created['issue']['record_id']}",
            {"expected_revision": 1, "status": "resolved"},
        )
        _, review = self.client.request(
            "PATCH", f"{self.path}/learning-records/{created['review_task']['record_id']}",
            {"expected_revision": 1, "status": "completed"},
        )
        _, runtime = self.client.request("GET", f"{self.path}/learning-runtime")
        records = runtime.get("records") or {}
        self._require(not records.get("open_issue_ids"), "resolved issue remains open in runtime")
        self._record("REC", {
            "record_ids": {key: value.get("record_id") for key, value in created.items()},
            "note_archived": True,
            "issue_status": issue.get("status"),
            "review_status": review.get("status"),
            "stale_update_status": conflict_status,
            "runtime_record_summary": records,
            "runtime_revision_id": runtime.get("runtime_revision_id"),
        })

    def _practice_failures(self) -> dict[str, Any]:
        task = self._mastery_task(str(self.first_node.get("node_id")))
        first = self._create_attempt(task)
        _, saved = self.client.request(
            "PATCH", f"{self.path}/practice/attempts/{first['attempt_id']}/draft",
            {"expected_revision": first.get("revision"), "answer_payload": {"text": _wrong_answer()}, "active_seconds": 18},
            device_id="acceptance-main-device-a",
        )
        first = saved.get("attempt") or {}
        _, active = self.client.request(
            "GET", f"{self.path}/practice/attempts/active",
            query={"task_revision_id": task.get("revision_id")}, device_id="acceptance-main-device-b",
        )
        self._require((active.get("attempt") or {}).get("attempt_id") == first.get("attempt_id"), "draft did not restore across devices")
        _, hinted = self.client.request(
            "POST", f"{self.path}/practice/attempts/{first['attempt_id']}/hints/1",
            {"expected_revision": first.get("revision")},
        )
        first = hinted.get("attempt") or {}
        first_submission = self._submit_attempt(first, _wrong_answer(), "fail-1")
        self._require((first_submission.get("result") or {}).get("passed") is False, "first intended failure was not graded false")
        self._require((first_submission.get("workflow") or {}).get("phase") == "practice", "single failure opened diagnosis")

        second = self._create_attempt(task)
        second_payload = self._submission_payload(second, _wrong_answer(), "fail-2")
        _, second_submission = self.client.request(
            "POST", f"{self.path}/practice/attempts/{second['attempt_id']}/submit", second_payload
        )
        result = second_submission.get("result") or {}
        workflow = second_submission.get("workflow") or {}
        self._require(result.get("passed") is False, "second intended failure was not graded false")
        self._require(workflow.get("phase") == "diagnostic", "second reliable failure did not open diagnosis")
        _, repeated = self.client.request(
            "POST", f"{self.path}/practice/attempts/{second['attempt_id']}/submit", second_payload
        )
        self._require(repeated.get("status") == "already_submitted", "repeated submit was not idempotent")
        locked_status, _ = self.client.request(
            "PATCH", f"{self.path}/practice/attempts/{second['attempt_id']}/draft",
            {"expected_revision": (second_submission.get("attempt") or {}).get("revision"), "answer_payload": {"text": "覆盖历史"}},
            expected={409},
        )
        self.failed_attempt_ids = [
            (first_submission.get("attempt") or {}).get("attempt_id"),
            (second_submission.get("attempt") or {}).get("attempt_id"),
        ]
        self._record("PRA", {
            "task_revision_id": task.get("revision_id"),
            "failed_attempt_ids": self.failed_attempt_ids,
            "first_support_level": (first_submission.get("result") or {}).get("support_level"),
            "second_support_level": result.get("support_level"),
            "idempotent_status": repeated.get("status"),
            "submitted_history_write_status": locked_status,
            "diagnostic_case_id": (workflow.get("case") or {}).get("diagnostic_case_id"),
        })
        return workflow

    def _diagnosis(self, workflow: dict[str, Any]) -> dict[str, Any]:
        task = workflow.get("current_task") or {}
        self._require(task.get("task_revision_id"), "diagnostic task is missing")
        attempt = self._create_attempt(task)
        submitted = self._submit_attempt(attempt, _wrong_answer(), "diagnostic")
        next_workflow = submitted.get("workflow") or {}
        self._require((submitted.get("result") or {}).get("passed") is False, "diagnostic probe did not provide evidence for hypothesis")
        self._require(next_workflow.get("phase") == "remediation", "confirmed diagnostic did not start remediation")
        case = next_workflow.get("case") or {}
        hypotheses = case.get("hypotheses") or []
        self._require(any(item.get("status") == "confirmed" for item in hypotheses), "no diagnostic hypothesis was confirmed")
        self._record("DIA", {
            "diagnostic_case_id": case.get("diagnostic_case_id"),
            "probe_attempt_id": (submitted.get("attempt") or {}).get("attempt_id"),
            "hypothesis_count": len(hypotheses),
            "confirmed_hypothesis_id": case.get("confirmed_hypothesis_id"),
            "case_status": case.get("status"),
            "phase": next_workflow.get("phase"),
        })
        return next_workflow

    def _remediation(self, workflow: dict[str, Any]) -> None:
        guided_task = workflow.get("current_task") or {}
        guided_attempt = self._create_attempt(guided_task)
        guided_submission = self._submit_attempt(guided_attempt, _strong_answer(guided_task), "guided")
        guided_workflow = guided_submission.get("workflow") or {}
        self._require((guided_submission.get("result") or {}).get("passed") is True, "guided remediation was not graded as passed")
        self._require(guided_workflow.get("phase") == "validation", "guided remediation incorrectly closed or failed to reach validation")
        validation_task = guided_workflow.get("current_task") or {}
        validation_attempt = self._create_attempt(validation_task)
        validation_submission = self._submit_attempt(
            validation_attempt, _strong_answer(validation_task), "validation"
        )
        resolved = validation_submission.get("workflow") or {}
        self._require((validation_submission.get("result") or {}).get("passed") is True, "independent validation was not graded as passed")
        self._require(resolved.get("phase") == "resolved", "independent validation did not resolve remediation")
        self._require((resolved.get("case") or {}).get("status") == "resolved", "diagnostic case is not resolved")
        self._record("REM", {
            "remediation_session_id": (resolved.get("session") or {}).get("remediation_session_id"),
            "guided_attempt_id": (guided_submission.get("attempt") or {}).get("attempt_id"),
            "guided_phase_after_grade": guided_workflow.get("phase"),
            "validation_attempt_id": (validation_submission.get("attempt") or {}).get("attempt_id"),
            "validation_support_level": (validation_submission.get("result") or {}).get("support_level"),
            "final_phase": resolved.get("phase"),
            "case_status": (resolved.get("case") or {}).get("status"),
            "session_status": (resolved.get("session") or {}).get("status"),
        })

    def _chapter_completion(self) -> None:
        second_node_id = str(self.second_node.get("node_id"))
        self.client.request("POST", f"{self.path}/learning-progress/nodes/{second_node_id}", {"action": "start"})
        self.client.request("POST", f"{self.path}/learning-progress/nodes/{second_node_id}", {"action": "complete_reading"})
        task = self._mastery_task(second_node_id)
        attempt = self._create_attempt(task)
        submission = self._submit_attempt(attempt, _strong_answer(task), "chapter-mastery")
        self._require((submission.get("result") or {}).get("mastery_eligible") is True, "second objective did not produce mastery evidence")
        _, continuation = self.client.request("GET", f"{self.path}/learning-continuation")
        chapter_result = continuation.get("chapter_result") or {}
        action = continuation.get("primary_action") or {}
        self._require(chapter_result.get("state") == "verified", "first chapter did not reach verified state")
        self._require(action.get("action_type") == "start_next_chapter", "chapter completion did not produce the unique next-chapter action")
        self._record("CON", {
            "chapter_id": chapter_result.get("chapter_id"),
            "chapter_state": chapter_result.get("state"),
            "objective_results": [
                {
                    "objective_revision_id": item.get("objective_revision_id"),
                    "reading_status": item.get("reading_status"),
                    "mastery_status": item.get("mastery_status"),
                    "evidence_strength": item.get("evidence_strength"),
                }
                for item in chapter_result.get("objectives") or []
            ],
            "residuals": chapter_result.get("residuals"),
            "primary_action": action.get("action_type"),
            "primary_target": action.get("target_id"),
            "secondary_notice_count": len(continuation.get("secondary_notices") or []),
        })

    def _ai_teacher(self) -> None:
        conversation_id = f"{self.run_id}-conversation"[:150]
        context_ref = {
            "course_version_id": self.course.get("current_course_version_id"),
            "node_id": self.first_node.get("node_id"),
            "objective_revision_id": self.first_node.get("objective_revision_id"),
            "content_anchor": self.anchor,
        }
        requests = [
            {
                "entrypoint": "selection",
                "question": "结合当前课程片段，解释线性相关判断为什么需要检查不全为零的系数。",
                "selection": self.anchor.get("text_quote") or "",
                "task_ref": {},
            },
            {
                "entrypoint": "practice",
                "question": "这道正式练习应该从哪一步开始？不要直接替我提交答案。",
                "selection": "",
                "task_ref": {"kind": "practice", "object_id": "forged-unsubmitted-task", "status": "graded"},
            },
            {
                "entrypoint": "continuity",
                "question": "请解释系统为什么把进入下一章作为现在唯一的下一步。",
                "selection": "",
                "task_ref": {},
            },
        ]
        answer_lengths: list[int] = []
        source_counts: list[int] = []
        disclosure_reasons: list[str] = []
        for index, item in enumerate(requests):
            events = self.client.sse("/api/ask_events", {
                "course_id": self.course_id,
                "conversation_id": conversation_id,
                "entrypoint": item["entrypoint"],
                "node_id": self.first_node.get("node_id"),
                "node_name": self.first_node.get("node_name") or "",
                "question": item["question"],
                "selection": item["selection"],
                "context_ref": context_ref,
                "task_ref": item["task_ref"],
            })
            names = [event.get("event") for event in events]
            self._require("error" not in names, f"AI teacher entry {item['entrypoint']} returned an error")
            self._require("context" in names and "sources" in names and "final_answer" in names and "done" in names, f"AI teacher entry {item['entrypoint']} missed required SSE events")
            context_event = next(event["data"] for event in events if event.get("event") == "context")
            self._require(context_event.get("conversation_id") == conversation_id, "AI teacher did not keep one conversation")
            sources = next(event["data"] for event in events if event.get("event") == "sources").get("sources") or []
            final = next(event["data"] for event in events if event.get("event") == "final_answer")
            answer = str(final.get("answer") or "")
            self._require(bool(answer.strip()), f"AI teacher entry {item['entrypoint']} returned an empty answer")
            self._require(bool(sources), f"AI teacher entry {item['entrypoint']} returned no course source")
            answer_lengths.append(len(answer))
            source_counts.append(len(sources))
            disclosure_reasons.append(str((context_event.get("answer_disclosure") or {}).get("reason") or ""))
            if index == 1:
                self._require(
                    (context_event.get("answer_disclosure") or {}).get("reference_answer_in_context") is False,
                    "client-forged practice status unlocked a reference answer",
                )

        _, proposal = self.client.request("POST", "/api/ai-teacher/proposals", {
            "course_id": self.course_id,
            "conversation_id": conversation_id,
            "action_type": "create_note",
            "target_ref": context_ref,
            "payload": {
                "node_id": self.first_node.get("node_id"),
                "title": "AI 老师主链验收笔记",
                "content": "线性相关判断必须检查不全为零的系数。",
                "anchor": self.anchor,
            },
            "reason": "验证可确认动作协议",
            "confirmation_mode": "explicit",
            "origin": "assistant",
        })
        proposal_id = str(proposal.get("proposal_id") or "")
        self._require(bool(proposal_id), "AI teacher proposal was not created")
        confirm_payload = {"course_id": self.course_id, "idempotency_key": f"{self.run_id}-confirm-note"}
        _, receipt = self.client.request(
            "POST", f"/api/ai-teacher/proposals/{proposal_id}/confirm", confirm_payload
        )
        _, repeated = self.client.request(
            "POST", f"/api/ai-teacher/proposals/{proposal_id}/confirm", confirm_payload
        )
        self._require(receipt.get("receipt_id") == repeated.get("receipt_id"), "AI teacher confirmation was not idempotent")
        _, undone = self.client.request(
            "POST", f"/api/ai-teacher/receipts/{receipt.get('receipt_id')}/undo",
            {"course_id": self.course_id, "idempotency_key": f"{self.run_id}-undo-note"},
        )
        self._require(undone.get("status") == "succeeded", "AI teacher receipt undo failed")
        self._record("AIT", {
            "conversation_id": conversation_id,
            "entrypoints": [item["entrypoint"] for item in requests],
            "answer_lengths": answer_lengths,
            "source_counts": source_counts,
            "answer_disclosure_reasons": disclosure_reasons,
            "proposal_id": proposal_id,
            "receipt_id": receipt.get("receipt_id"),
            "idempotent_receipt": receipt.get("receipt_id") == repeated.get("receipt_id"),
            "undo_status": undone.get("status"),
        })

    def _create_attempt(self, task: dict[str, Any]) -> dict[str, Any]:
        revision_id = str(task.get("task_revision_id") or task.get("revision_id") or "")
        self._require(bool(revision_id), "assessment task revision is missing")
        _, response = self.client.request(
            "POST", f"{self.path}/practice/attempts", {"task_revision_id": revision_id}
        )
        attempt = response.get("attempt") or {}
        self._require(attempt.get("status") == "in_progress", "attempt was not created in progress")
        return attempt

    def _submit_attempt(self, attempt: dict[str, Any], answer: str, suffix: str) -> dict[str, Any]:
        payload = self._submission_payload(attempt, answer, suffix)
        _, response = self.client.request(
            "POST", f"{self.path}/practice/attempts/{attempt['attempt_id']}/submit", payload
        )
        result = response.get("result") or {}
        self._require(result.get("status") == "graded", f"{suffix} grading is not conclusive: {result}")
        return response

    def _submission_payload(self, attempt: dict[str, Any], answer: str, suffix: str) -> dict[str, Any]:
        return {
            "expected_revision": attempt.get("revision"),
            "answer_payload": {"text": answer},
            "active_seconds": 30,
            "request_id": f"{self.run_id}-{suffix}-submit",
        }

    def _mastery_task(self, node_id: str) -> dict[str, Any]:
        task = next(
            (
                item for item in self.questions
                if str(item.get("node_id") or "") == node_id
                and item.get("practice_level") == "mastery_check"
            ),
            None,
        )
        self._require(bool(task), f"mastery task missing for {node_id}")
        return task or {}

    @staticmethod
    def _progress_node(projection: dict[str, Any], node_id: str) -> dict[str, Any]:
        return next((item for item in projection.get("nodes") or [] if item.get("node_id") == node_id), {})

    def _record(self, stage: str, details: dict[str, Any]) -> None:
        self.evidence.append({"stage": stage, "status": "passed", "checked_at": _now(), **details})
        print(f"[{stage}] passed", flush=True)

    @staticmethod
    def _require(condition: Any, message: str) -> None:
        if not condition:
            raise AcceptanceFailure(message)


def _wrong_answer() -> str:
    return "线性相关就是所有向量方向完全相同，不需要检查系数、秩、边界条件或具体例子。"


def _strong_answer(task: dict[str, Any]) -> str:
    spec = task.get("answer_spec") or {}
    criteria = "；".join(str(item) for item in spec.get("criteria") or [])
    concepts = "、".join(str(item) for item in spec.get("expected_keywords") or [])
    task_text = f"{task.get('prompt') or ''} {criteria} {concepts}"
    vector_task = any(marker in task_text for marker in ("二维向量", "线性相关", "线性组合"))
    if not vector_task and any(marker in task_text for marker in ("矩阵", "AB", "BA", "列空间")):
        example = (
            "必要条件：矩阵乘法要求左矩阵列数等于右矩阵行数，可逆矩阵必须是方阵且满秩。"
            "关键步骤：取 A=[[1,1],[0,1]]、B=[[1,0],[1,1]]，逐项相乘得到 "
            "AB=[[2,1],[1,1]]，BA=[[1,1],[1,2]]，二者不相等；"
            "矩阵乘法表示线性映射的复合，交换顺序会改变先后作用，所以通常不满足交换律。"
            "再取三阶对角矩阵 D=diag(1,2,3)，对增广矩阵 [D|I] 做初等行变换可得 "
            "D^{-1}=diag(1,1/2,1/3)，并验证 DD^{-1}=I。"
            "对于 C=[[1,2,3],[2,4,6]]，第二行是第一行的2倍，行简化只有一个主元，"
            "所以 rank(C)=1，列空间维数也是1，可取第一列作为一组基。"
            "结果检查：重新计算 AB 的(1,1)元为2而 BA 的(1,1)元为1；"
            "同时 D 与 D^{-1} 对应对角元相乘均为1，C 的所有列也确实都是第一列的倍数。"
        )
    else:
        example = (
            "必要条件：线性相关是指存在一组不全为零的系数，使这些向量的线性组合等于零向量。"
            "关键步骤：取二维向量 v1=(1,0)、v2=(0,1)、v3=(1,1)。"
            "令 a v1+b v2+c v3=0，得到 a+c=0、b+c=0，存在不全为零的解，"
            "并且 v3=v1+v2，所以三者线性相关；矩阵列秩为2，小于向量个数3。"
            "若集合包含零向量，令零向量的系数为1而其余为0，也得到非平凡线性组合为零。"
            "结果检查：取(a,b,c)=(-1,-1,1)，代回得到 -v1-v2+v3=(0,0)，"
            "并且直接计算 v3-v1-v2=(1,1)-(1,0)-(0,1)=(0,0)，结论与秩判据一致。"
        )
    return (
        "先写明定义和必要条件，再计算并检查边界。"
        f"{example}"
        "这说明判断必须同时检查线性组合的系数条件、秩以及适用边界，不能只看方向。"
        f"相关概念包括：{concepts}。需要满足并逐项核对：{criteria}。"
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="验收标准课程主学习链")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--course-id", default=DEFAULT_COURSE_ID)
    parser.add_argument("--user-id", required=True, help="必须使用全新的隔离验收用户")
    parser.add_argument("--run-id", default="acceptance-8-4")
    parser.add_argument("--output", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        report = MainChainAcceptance(
            ApiClient(args.base_url, args.user_id), args.course_id, args.run_id,
        ).run()
    except (AcceptanceFailure, TimeoutError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
