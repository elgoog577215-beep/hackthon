"""Versioned publication references and feedback transport between Lingzhi nodes.

The publisher alone owns course bodies and private assessment contracts. The
consumer holds immutable reading representations, never another course writer.
Learning attempts stay in the original learner repositories.
"""

from __future__ import annotations

from course_exchange_digest import digest

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import hmac
import os
import re
from urllib.parse import urlparse
from uuid import uuid4
from contextvars import ContextVar
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import HTTPException, Request
import requests
import file_lock

SCHEMA = "lingzhi_course_exchange_v1"
LEDGER = "course_exchange.json"
INTERNAL_PREFIX = "/api/exchange/internal/"
remote_course_context = ContextVar("remote_course_context", default=None)


@asynccontextmanager
async def publisher_grade_lock(storage, key):
    from fastapi.concurrency import run_in_threadpool

    root = Path(storage._data_dir) / "exchange_grade_locks"
    root.mkdir(parents=True, exist_ok=True)
    with (root / (key + ".lock")).open("a+b") as handle:
        await run_in_threadpool(file_lock.flock, handle, file_lock.LOCK_EX)
        try:
            yield
        finally:
            file_lock.flock(handle, file_lock.LOCK_UN)


def now():
    return datetime.now(timezone.utc).isoformat()




@dataclass(frozen=True)
class ExchangeConfig:
    role: str = ""
    node_id: str = ""
    peer_id: str = ""
    peer_url: str = ""
    token: str = ""

    @classmethod
    def environment(cls):
        return cls(
            *(
                os.getenv("LINGZHI_EXCHANGE_" + key, "").strip()
                for key in ("ROLE", "NODE_ID", "PEER_ID", "PEER_URL", "TOKEN")
            )
        )

    @property
    def enabled(self):
        return self.role in {"teacher", "student"} and bool(
            self.node_id and self.peer_id and self.peer_url and len(self.token) >= 32
        )

    def validate(self):
        parsed = urlparse(self.peer_url)
        if (
            not self.enabled
            or self.node_id == self.peer_id
            or not all(re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", value) for value in (self.node_id, self.peer_id))
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
            or not parsed.hostname
            or (
                parsed.scheme != "https"
                and not (parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"})
            )
        ):
            raise HTTPException(503, "师生互通尚未配置或配置无效")
        return self


class ExchangeClient:
    def __init__(self, config=None):
        self.config = config or ExchangeConfig.environment()

    def call(self, method, path, body=None, *, binary=False):
        config = self.config.validate()
        if not path.startswith(INTERNAL_PREFIX):
            raise ValueError("exchange_path_outside_internal_domain")
        try:
            response = requests.request(
                method,
                config.peer_url.rstrip("/") + path,
                json=body,
                headers={"Authorization": "Bearer " + config.token, "X-Lingzhi-Node": config.node_id},
                timeout=(3, 120 if path.endswith("/grade") else 12),
                allow_redirects=False,
            )
        except requests.RequestException:
            raise HTTPException(503, "另一端暂不可达，已有内容和学习记录已保留") from None
        if response.status_code in {401, 403, 404, 409, 422}:
            raise HTTPException(response.status_code, "来源授权、发布版本或同步请求已不可用")
        if response.status_code != 200:
            raise HTTPException(503, "另一端暂不能处理请求，已有记录已保留")
        if binary:
            if response.headers.get("X-Lingzhi-Node") != config.peer_id:
                raise HTTPException(503, "来源服务身份不匹配")
            return response.content
        try:
            value = response.json()
        except ValueError:
            raise HTTPException(503, "另一端返回了无效数据") from None
        if not isinstance(value, dict) or value.get("node_id") != config.peer_id:
            raise HTTPException(503, "来源服务身份不匹配")
        return value


def require_peer(request: Request):
    config = ExchangeConfig.environment().validate()
    supplied = request.headers.get("Authorization", "")
    if request.headers.get("X-Lingzhi-Node") != config.peer_id or not hmac.compare_digest(
        supplied.encode(), ("Bearer " + config.token).encode()
    ):
        raise HTTPException(401, "服务身份验证失败")
    return config


class ExchangeRepository:
    def __init__(self, storage, config=None):
        self.storage = storage
        self.config = config or ExchangeConfig.environment()

    def ledger(self):
        return self.storage.load_data(LEDGER) or {}

    def update(self, fn):
        return self.storage.update_data(LEDGER, lambda value: fn(value or {}))

    def publish(self, course, private_tasks, *, expected_revision, ppt_project_ids=()):
        from assessment_contracts import project_public_question
        from course_learning_projection import public_course
        from question_public_guard import assert_no_answer_leak

        disclosed = public_course(course)
        document = disclosed["course_document"]
        if document["document_revision"] != expected_revision:
            raise HTTPException(409, "课程已变化，请刷新后重新发布")
        if not document["blocks"]:
            raise HTTPException(422, "还没有可发布的完成讲义")
        visible_nodes = {n["node_id"] for n in disclosed["nodes"] if n.get("node_content")}
        tasks = [deepcopy(t) for t in private_tasks if t.get("node_id") in visible_nodes]
        public_tasks = [project_public_question(t) for t in tasks]
        for task in public_tasks:
            task["grading_authority"] = "publisher"
            task["task_purpose"] = "course_practice"
            task["task_source"] = "published_course"
        assets = {
            "questions": [t for t in public_tasks if t.get("practice_level") != "final_assessment"],
            "final_assessment": [t for t in public_tasks if t.get("practice_level") == "final_assessment"],
            "mastery_criteria": [],
            "checklist": [],
        }
        # Criteria are observable requirements, not private answers/rubrics.
        for criterion in (course.get("learning_assets") or {}).get("mastery_criteria") or []:
            if criterion.get("node_id") in visible_nodes:
                assets["mastery_criteria"].append(
                    {
                        key: deepcopy(criterion[key])
                        for key in (
                            "criterion_id",
                            "revision_id",
                            "node_id",
                            "observable_performance",
                            "assessment_bindings",
                            "objective_id",
                            "objective_revision_id",
                            "concept_ids",
                        )
                        if key in criterion
                    }
                )
        disclosed.update(
            learning_assets=assets,
            authoring_surface="exchange",
            is_published=True,
            course_creation_intent="standard_learning" if tasks else "material_organization",
        )
        disclosed["course_knowledge_base"] = public_knowledge_tree(course, document)
        if disclosed["course_knowledge_base"].get("knowledge_points"):
            from course_knowledge_base import build_course_knowledge_library_view
            from course_knowledge_map import compile_course_knowledge_map

            # Freeze the same public read model consumed by the student graph.
            # The consumer must not reconstruct it from a later teacher draft.
            assets["knowledge_library"] = [build_course_knowledge_library_view(
                disclosed["course_knowledge_base"],
                compile_course_knowledge_map(disclosed),
                assets,
                disclosed,
            )]
        from course_exchange_ppt import freeze_published_ppts

        disclosed["published_ppts"] = freeze_published_ppts(self.storage, course, document, ppt_project_ids)
        assert_no_answer_leak(assets)
        fingerprint = digest({"public": disclosed, "private_tasks": tasks})
        result = {}

        def save(value):
            publications = value.setdefault("publications", {})
            current = publications.get(course["course_id"], {"releases": {}})
            previous = current["releases"].get(current.get("current_release_id"), {})
            if (
                previous.get("fingerprint") == fingerprint
                and current.get("status") == "published"
                and current.get("owner_id") == course["owner_id"]
            ):
                result.update(previous["public"])
                return value
            release_id = "release_" + uuid4().hex
            public = {
                "schema_version": SCHEMA,
                "node_id": self.config.node_id,
                "source_course_id": course["course_id"],
                "release_id": release_id,
                "source_document_revision": document["document_revision"],
                "published_at": now(),
                "course": disclosed,
                "feedback_policy": {"formal_practice": "teacher_visible", "personal_materials": "private"},
            }
            current.update(owner_id=course["owner_id"], status="published", current_release_id=release_id)
            current["releases"][release_id] = {
                "public": public,
                "private_tasks": tasks,
                "fingerprint": fingerprint,
                "owner_id": course["owner_id"],
            }
            publications[course["course_id"]] = current
            result.update(public)
            return value

        self.update(save)
        return result

    def publication(self, course_id, actor, release_id=""):
        from course_learning_access import CourseLearningAccess

        raw = self.storage.load_course(course_id)
        publication = self.ledger().get("publications", {}).get(course_id) or {}
        if (
            not raw
            or publication.get("status") != "published"
            or publication.get("owner_id") != raw.get("owner_id")
            or not CourseLearningAccess(self.storage).active(raw, actor)
        ):
            raise HTTPException(404, "课程未发布或学习授权已撤销")
        release = publication.get("releases", {}).get(release_id or publication.get("current_release_id"))
        if not release or release.get("owner_id") != raw.get("owner_id"):
            raise HTTPException(404, "发布版本不存在")
        return deepcopy(release)

    def unpublish(self, course_id):
        def save(value):
            item = value.get("publications", {}).get(course_id)
            if item:
                item["status"] = "withdrawn"
            return value

        self.update(save)

    def references(self, actor):
        return deepcopy(self.ledger().get("references", {}).get(actor, {}))

    def reference(self, actor, local_course_id):
        item = self.references(actor).get(local_course_id)
        if not item:
            raise HTTPException(404, "课程来源不存在或不属于当前学生")
        return item

    def sync(self, actor, client=None):
        client = client or ExchangeClient(self.config)
        catalogue = client.call("POST", INTERNAL_PREFIX + "catalogue", {"actor_id": actor})
        imports = []
        for public in catalogue.get("publications") or []:
            if public.get("node_id") != self.config.peer_id or public.get("schema_version") != SCHEMA:
                raise HTTPException(503, "课程来源身份或合同不匹配")
            local_id = "exchange_" + digest([self.config.peer_id, public["source_course_id"]])[:32]
            imports.append((local_id, public))

        def save(value):
            references = value.setdefault("references", {}).setdefault(actor, {})
            for local_id, public in imports:
                ref = references.setdefault(
                    local_id,
                    {
                        "source_node_id": self.config.peer_id,
                        "source_course_id": public["source_course_id"],
                        "release_id": public["release_id"],
                        "releases": {},
                        "created_at": now(),
                    },
                )
                ref["latest_release_id"] = public["release_id"]
                frozen = ref["releases"].get(public["release_id"])
                if frozen and frozen != public:
                    raise HTTPException(409, "同一发布版本的内容已改变，不能覆盖已保存内容")
                ref["releases"][public["release_id"]] = deepcopy(public)
                ref.update(status="active", synced_at=now())
            active = {key for key, _ in imports}
            for local_id, ref in references.items():
                if ref["source_node_id"] == self.config.peer_id and local_id not in active:
                    ref["status"] = "unavailable"
            return value

        self.update(save)
        return self.references(actor)

    def read(self, actor, local_course_id, *, release_id="", client=None):
        ref = self.reference(actor, local_course_id)
        if ref.get("source_node_id") != self.config.peer_id:
            raise HTTPException(503, "课程来源配置已改变")
        target = release_id or ref["release_id"]
        public = (client or ExchangeClient(self.config)).call(
            "POST",
            INTERNAL_PREFIX + "read",
            {"actor_id": actor, "course_id": ref["source_course_id"], "release_id": target},
        )["publication"]
        if (
            public.get("release_id") != target
            or public.get("source_course_id") != ref["source_course_id"]
            or public.get("node_id") != ref["source_node_id"]
            or public.get("schema_version") != SCHEMA
        ):
            raise HTTPException(503, "发布版本身份不匹配")
        return self.projection(local_course_id, public)

    @staticmethod
    def projection(local_id, public):
        course = deepcopy(public["course"])
        course["course_id"] = local_id
        course["course_document"]["course_id"] = local_id
        course["current_course_version_id"] = public["release_id"]
        course["learning_assets"]["exchange_release_id"] = public["release_id"]
        if course.get("course_knowledge_base"):
            course["course_knowledge_base"]["course_id"] = local_id
        for library in course["learning_assets"].get("knowledge_library") or []:
            library["subject_id"] = local_id
        course["exchange_origin"] = {
            key: public[key] for key in ("node_id", "source_course_id", "release_id", "source_document_revision")
        }
        return course

    def adopt(self, actor, local_id, expected_release_id, client=None):
        self.sync(actor, client)
        ref = self.reference(actor, local_id)
        target = ref["latest_release_id"]
        self.read(actor, local_id, release_id=target, client=client)

        def save(value):
            current = value["references"][actor][local_id]
            if current["release_id"] != expected_release_id:
                raise HTTPException(409, "课程版本已变化，请刷新")
            current["release_id"] = target
            return value

        self.update(save)
        return self.reference(actor, local_id)

    def queue_feedback(self, actor, local_id, *, request_id, kind, payload, release_id=""):
        ref = self.reference(actor, local_id)
        item_id = "feedback_" + digest([self.config.node_id, actor, request_id])[:32]
        frozen = {
            "feedback_id": item_id,
            "actor_id": actor,
            "source_node_id": self.config.node_id,
            "course_id": ref["source_course_id"],
            "release_id": release_id or ref["release_id"],
            "kind": kind,
            "payload": deepcopy(payload),
        }

        def save(value):
            old = value.setdefault("outbox", {}).get(item_id)
            if old and old["fingerprint"] != digest(frozen):
                raise HTTPException(409, "这个反馈请求已使用，请刷新后提交")
            value["outbox"].setdefault(
                item_id,
                {
                    "envelope": frozen,
                    "fingerprint": digest(frozen),
                    "local_course_id": local_id,
                    "status": "pending",
                    "created_at": now(),
                },
            )
            return value

        self.update(save)
        return item_id

    def deliver(self, actor, feedback_id, client=None):
        item = self.ledger().get("outbox", {}).get(feedback_id)
        if not item or item["envelope"]["actor_id"] != actor:
            raise HTTPException(404, "反馈不存在")
        if item["status"] == "delivered":
            return deepcopy(item)
        try:
            receipt = (client or ExchangeClient(self.config)).call(
                "POST", INTERNAL_PREFIX + "feedback", item["envelope"]
            )
        except HTTPException as exc:
            if exc.status_code in {401, 403, 404, 409, 422}:
                raise
            return {**deepcopy(item), "status": "pending"}

        def save(value):
            value["outbox"][feedback_id].update(status="delivered", receipt=receipt, delivered_at=now())
            return value

        return self.update(save)["outbox"][feedback_id]

    def receive(self, envelope, peer_id):
        if envelope.get("source_node_id") != peer_id:
            raise HTTPException(403, "反馈来源不匹配")
        release = self.publication(envelope["course_id"], envelope["actor_id"], envelope["release_id"])
        key = envelope["feedback_id"]

        def save(value):
            received = value.setdefault("received", {})
            old = received.get(key)
            if old and old["fingerprint"] != digest(envelope):
                raise HTTPException(409, "重复反馈内容不一致")
            received.setdefault(
                key,
                {
                    "envelope": deepcopy(envelope),
                    "fingerprint": digest(envelope),
                    "received_at": now(),
                    "reply": "",
                    "revision": 1,
                    "owner_id": release["owner_id"],
                },
            )
            return value

        self.update(save)
        return {"node_id": self.config.node_id, "receipt_id": key, "status": "received"}


def is_remote_course(course_id):
    return bool(re.fullmatch(r"exchange_[0-9a-f]{32}", course_id))


def read_remote_course(storage, actor, course_id, *, release_id=""):
    return ExchangeRepository(storage).read(actor, course_id, release_id=release_id)


def remote_task_action(course, actor, action, payload):
    origin = course["exchange_origin"]
    body = {"actor_id": actor, "course_id": origin["source_course_id"], "release_id": origin["release_id"], **payload}
    return ExchangeClient().call("POST", INTERNAL_PREFIX + action, body)


def public_knowledge_tree(course, document):
    tree = course.get("course_knowledge_base") or {}
    if tree.get("tree_schema") in {"knowledge_first_c17_v1", "knowledge_first_generic_v1"}:
        from knowledge_first import knowledge_projection

        tree = knowledge_projection(tree)
    if tree.get("lifecycle_status") != "active":
        return {}
    if tree.get("source_mode") == "handouts":
        from handout_knowledge import visible_handout_tree

        tree = visible_handout_tree(tree, document, course.get("teacher_handouts") or {})
    result = {
        key: deepcopy(tree[key])
        for key in (
            "schema_version",
            "tree_schema",
            "status",
            "knowledge_base_id",
            "course_id",
            "revision_id",
            "terminology_revision",
            "lifecycle_status",
            "source_mode",
            "title",
        )
        if key in tree
    }
    fields = {
        "knowledge_points": (
            "knowledge_id",
            "revision_id",
            "name",
            "aliases",
            "statement",
            "definition",
            "conditions",
            "boundaries",
            "counterexamples",
            "knowledge_type",
            "primary_concept_group_id",
            "parent_id",
            "topic",
            "classification_id",
            "category_id",
            "status",
            "granularity_status",
            "scope_role",
            "lesson_unit_ids",
            "section_ids",
            "section_refs",
            "course_block_refs",
            "objective_refs",
            "order",
        ),
        "classifications": ("classification_id", "name", "parent_id", "parent_classification_id", "order", "status"),
        "concept_groups": (
            "id",
            "concept_group_id",
            "parent_group_id",
            "parent_id",
            "primary_section_ref",
            "revision_id",
            "name",
            "description",
            "order",
            "knowledge_ids",
            "section_refs",
        ),
        "relations": (
            "id",
            "source_id",
            "target_id",
            "type",
            "relation_id",
            "revision_id",
            "source_knowledge_id",
            "target_knowledge_id",
            "relation_type",
            "kind",
            "strength",
            "necessity",
            "priority",
            "conditions",
            "reason",
            "distinction",
            "derivation_steps",
            "status",
        ),
        "bindings": (
            "binding_id",
            "knowledge_ids",
            "skill_ids",
            "target_type",
            "target_id",
            "teaching_role",
            "importance",
            "binding_method",
        ),
        "skill_units": (
            "skill_unit_id",
            "skill_id",
            "revision_id",
            "name",
            "statement",
            "performance",
            "primary_knowledge_id",
            "knowledge_ids",
        ),
        "misconceptions": (
            "misconception_id",
            "revision_id",
            "name",
            "statement",
            "observable_error_pattern",
            "primary_knowledge_id",
            "skill_ids",
        ),
    }
    for kind, keys in fields.items():
        result[kind] = [
            {key: deepcopy(item[key]) for key in keys if key in item}
            for item in tree.get(kind) or []
            if isinstance(item, dict)
        ]
    # Generic trees retain their stable relation IDs and direction while also
    # exposing the canonical aliases expected by the student library.
    for relation in result["relations"]:
        for target, source in (
            ("relation_id", "id"),
            ("source_knowledge_id", "source_id"),
            ("target_knowledge_id", "target_id"),
            ("relation_type", "type"),
        ):
            if not relation.get(target) and relation.get(source):
                relation[target] = relation[source]
    for point in result["knowledge_points"]:
        if not point.get("primary_concept_group_id") and point.get("parent_id"):
            point["primary_concept_group_id"] = point["parent_id"]
    point_ids = {p["knowledge_id"] for p in result["knowledge_points"]}
    visible_blocks = {block["block_id"] for block in document.get("blocks") or []}
    result["bindings"] = [
        {**binding, "knowledge_ids": [kid for kid in binding.get("knowledge_ids") or [] if kid in point_ids]}
        for binding in result["bindings"]
        if any(kid in point_ids for kid in binding.get("knowledge_ids") or [])
        and (binding.get("target_type") != "course_block" or binding.get("target_id") in visible_blocks)
    ]
    result["categories"] = [
        {key: deepcopy(item[key]) for key in ("id", "parent_id", "name", "order") if key in item}
        for item in tree.get("categories") or [] if isinstance(item, dict)
    ]
    section_keys = (
        "knowledge_node_ids",
        "capability_point_ids",
        "mistake_point_ids",
        "mastery_criterion_ids",
        "improvement_point_ids",
    )
    result["section_bindings"] = {
        section: {key: deepcopy(item[key]) for key in section_keys if key in item}
        for section, item in (tree.get("section_bindings") or {}).items()
        if isinstance(item, dict) and section in {s["section_id"] for s in document["sections"]}
    }
    return result


def send_practice_feedback(storage, course, actor, attempt):
    receipt_id = (attempt.get("result") or {}).get("publisher_receipt_id")
    if not receipt_id:
        return {"status": "unavailable"}
    repo = ExchangeRepository(storage)
    key = repo.queue_feedback(
        actor,
        course["course_id"],
        request_id="attempt:" + attempt["attempt_id"],
        kind="practice_result",
        release_id=course["exchange_origin"]["release_id"],
        payload={
            "attempt_id": attempt["attempt_id"],
            "attempt_revision": attempt["revision"],
            "receipt_id": receipt_id,
        },
    )
    result = repo.deliver(actor, key)
    return {"feedback_id": key, "status": result["status"]}
