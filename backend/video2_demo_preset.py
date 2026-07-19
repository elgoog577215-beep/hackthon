"""视频二“个体化生长”的确定性课程与录制状态预设。

这个模块只服务本地演示准备：

1. 手工构造一门内容完整、结构稳定的《矩阵与线性变换》课程；
2. 清理这门专用课程在上一次预演中产生的个人学习状态；
3. 写入一条与“复合变换顺序”直接对应的正式练习；
4. 不调用任何外部模型或远程服务。

运行入口见 ``scripts/prepare_video_2_demo.py``。
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any

from course_document import (
    COURSE_DOCUMENT_SCHEMA,
    CourseBlock,
    CourseDocument,
    CourseSection,
    refresh_document_revision,
)
from course_revisions import revision_vector_for_document
from learning_asset_storage import LearningAssetRepository
from storage import Storage


COURSE_ID = "demo-matrix-growth-v2"
COURSE_TITLE = "矩阵与线性变换"
TARGET_SECTION_ID = "v2-sec-1-2"
TARGET_BLOCK_ID = "v2-b-1-2-orientation"
DEMO_USER_ID = "video2-demo-student"
FIXED_PROMPT = (
    "矩阵乘法计算我会，但我一直不理解为什么复合变换要先右后左。"
    "请在本节和后面相关内容中，先用几何动画解释，再让我进行计算。"
)

_CREATED_AT = "2026-07-19T08:00:00+00:00"


def build_video2_course_document() -> CourseDocument:
    """构造录屏专用的 canonical course document。"""
    sections = [
        _chapter(
            "v2-ch-1",
            "第1章 从向量到线性变换",
            0,
            "建立向量、矩阵与连续线性变换之间的统一几何语言。",
        ),
        _lesson(
            "v2-sec-1-1",
            "v2-ch-1",
            "1.1 向量：位置、方向与坐标",
            1,
            "从几何箭头与坐标表示两个角度理解向量，并能用基向量分解二维向量。",
            key_points=["向量的几何意义", "基向量分解", "坐标表示"],
            knowledge_structure=_knowledge_structure(
                "向量的两种语言",
                [
                    _knowledge_point(
                        "向量的几何意义",
                        "向量同时描述方向与大小，坐标是它在选定基底下的表示。",
                        capability="在图形与坐标之间转换同一个向量",
                        mastery="给定二维向量，画出几何箭头并写成基向量线性组合",
                    ),
                    _knowledge_point(
                        "基向量分解",
                        "任意二维向量都可写成两个基向量的线性组合。",
                        capability="把向量分解为标准基方向上的分量",
                        mastery="准确写出 v = x e₁ + y e₂ 并解释两个系数",
                        relations=[{
                            "target_name": "矩阵的列向量语义",
                            "relation_type": "prerequisite",
                            "reason": "理解基向量分解后，才能看懂矩阵两列如何决定整个变换。",
                        }],
                    ),
                ],
            ),
        ),
        _lesson(
            TARGET_SECTION_ID,
            "v2-ch-1",
            "1.2 矩阵：线性映射与矩阵运算",
            2,
            "把矩阵看成作用于向量的线性变换，能完成矩阵乘法，并区分计算规则与变换含义。",
            key_points=["矩阵的列向量语义", "矩阵乘法", "不交换性"],
            knowledge_structure=_knowledge_structure(
                "矩阵的几何语义",
                [
                    _knowledge_point(
                        "矩阵的列向量语义",
                        "二维矩阵的两列分别是两个标准基向量变换后的结果。",
                        capability="根据矩阵两列判断基向量和单位方格如何变化",
                        mastery="不依赖行列口诀解释 Av 的几何含义",
                    ),
                    _knowledge_point(
                        "矩阵复合含义",
                        "矩阵乘法既是坐标计算，也是连续线性变换的复合表示。",
                        capability="解释复合变换的先后顺序",
                        mastery="给定两个变换，能用中间状态解释最终矩阵表达式",
                        misconception={
                            "name": "把矩阵乘法只理解为行乘列",
                            "observable_error_pattern": "能够算出乘积，却无法说明乘法顺序对应的几何动作。",
                            "discrimination": "要求同时标出输入、中间状态和最终状态。",
                            "repair_strategy": "用连续作用在同一图形上的三个关键帧重建乘法语义。",
                        },
                        relations=[
                            {
                                "target_name": "复合变换顺序",
                                "relation_type": "prerequisite",
                                "reason": "矩阵乘法的几何语义是理解复合顺序的前提。",
                            },
                            {
                                "target_name": "基变换链",
                                "relation_type": "applies_to",
                                "reason": "坐标系切换由多个矩阵按顺序复合完成。",
                            },
                            {
                                "target_name": "图形变换管线",
                                "relation_type": "applies_to",
                                "reason": "图形管线把多个局部变换组合为一个最终变换。",
                            },
                        ],
                    ),
                ],
            ),
        ),
        _lesson(
            "v2-sec-1-3",
            "v2-ch-1",
            "1.3 复合变换：从两次动作到一个矩阵",
            3,
            "用输入—中间状态—输出描述两个线性变换的复合，并判断不同顺序是否得到同一结果。",
            key_points=["复合变换顺序", "中间状态", "矩阵不交换"],
            knowledge_structure=_knowledge_structure(
                "连续动作的结构",
                [
                    _knowledge_point(
                        "复合变换顺序",
                        "连续变换必须围绕同一个输入追踪中间状态，再连接到最终输出。",
                        capability="逐步解释两个线性变换的复合顺序",
                        mastery="给定 A、B 与 v，写出中间状态并说明顺序改变后的差异",
                        misconception={
                            "name": "按矩阵书写方向机械猜执行顺序",
                            "observable_error_pattern": "直接朗读矩阵字母，却不追踪每一步的作用对象。",
                            "discrimination": "要求写出每个箭头的输入与输出。",
                            "repair_strategy": "先画状态链，再把状态链压缩成矩阵表达式。",
                        },
                        relations=[{
                            "target_name": "基变换链",
                            "relation_type": "prerequisite",
                            "reason": "基变换公式本质上是连续映射的复合。",
                        }],
                    ),
                ],
            ),
        ),
        _chapter(
            "v2-ch-2",
            "第2章 从表示到应用",
            4,
            "把线性变换的复合结构迁移到坐标切换、逆变换和图形系统。",
        ),
        _lesson(
            "v2-sec-2-1",
            "v2-ch-2",
            "2.1 基变换：同一向量的不同坐标",
            5,
            "理解向量本身不变而坐标会随基底改变，并能解释坐标变换链中的每一步。",
            key_points=["基变换链", "坐标与对象", "相似变换"],
            knowledge_structure=_knowledge_structure(
                "坐标系切换",
                [
                    _knowledge_point(
                        "基变换链",
                        "坐标切换先把新坐标还原到原空间，再执行变换，最后写回目标坐标系。",
                        capability="解释 P⁻¹AP 中每个矩阵的作用对象",
                        mastery="沿输入—还原—变换—重表示的顺序解释相似变换",
                        relations=[{
                            "target_name": "逆变换与还原",
                            "relation_type": "prerequisite",
                            "reason": "坐标还原需要理解逆矩阵撤销已有变换。",
                        }],
                    ),
                ],
            ),
        ),
        _lesson(
            "v2-sec-2-2",
            "v2-ch-2",
            "2.2 逆变换：还原与可逆性",
            6,
            "把逆矩阵理解为撤销原变换的过程，并能判断何时存在唯一还原。",
            key_points=["逆变换与还原", "可逆性", "行列式"],
            knowledge_structure=_knowledge_structure(
                "撤销一个变换",
                [
                    _knowledge_point(
                        "逆变换与还原",
                        "逆矩阵通过相反方向的映射把输出还原为原始输入。",
                        capability="用状态链解释 A⁻¹Av = v",
                        mastery="判断一个二维变换是否可逆，并说明还原顺序",
                        relations=[{
                            "target_name": "图形变换管线",
                            "relation_type": "applies_to",
                            "reason": "图形交互中的坐标还原需要逆向穿过变换管线。",
                        }],
                    ),
                ],
            ),
        ),
        _lesson(
            "v2-sec-2-3",
            "v2-ch-2",
            "2.3 图形管线：连续变换的实际应用",
            7,
            "把缩放、旋转、平移等连续操作组织成可检查的变换管线。",
            key_points=["图形变换管线", "局部坐标", "组合检查"],
            knowledge_structure=_knowledge_structure(
                "从数学到图形系统",
                [
                    _knowledge_point(
                        "图形变换管线",
                        "图形系统按对象坐标、场景坐标和观察坐标逐层组合变换。",
                        capability="根据目标画面设计并核对变换管线",
                        mastery="为一个二维图形任务画出完整状态链并验证最终坐标",
                    ),
                ],
            ),
        ),
    ]

    blocks = [
        *_blocks_1_1(),
        *_blocks_1_2(),
        *_blocks_1_3(),
        *_blocks_2_1(),
        *_blocks_2_2(),
        *_blocks_2_3(),
    ]
    return refresh_document_revision(CourseDocument(
        course_id=COURSE_ID,
        title=COURSE_TITLE,
        sections=sections,
        blocks=blocks,
    ))


def build_video2_course_envelope() -> dict[str, Any]:
    """构造可直接被课程库读取的 canonical 存储信封。"""
    document = build_video2_course_document()
    return {
        "course_id": COURSE_ID,
        "course_name": COURSE_TITLE,
        "course_description": (
            "从向量与矩阵的几何意义出发，理解线性变换、复合顺序、"
            "基变换与图形管线之间的统一结构。"
        ),
        "course_purpose": "systematic",
        "target_audience": "大学一年级学生",
        "difficulty": "intermediate",
        "style": "visual",
        "estimated_hours": 6,
        "generation_status": "passed",
        "generation_schema_version": "manual_video_demo_v1",
        "generation_source": "curated_local_preset",
        "course_schema_version": COURSE_DOCUMENT_SCHEMA,
        "course_document": document.model_dump(mode="json"),
        "course_document_revision": document.document_revision,
        "course_revision_vector": revision_vector_for_document(document).model_dump(mode="json"),
        "course_document_authoritative": True,
        "current_course_version_id": document.document_revision,
        "course_operation_log": [],
        "created_at": _CREATED_AT,
        "updated_at": _CREATED_AT,
        "demo_metadata": {
            "schema_version": "video_demo_preset_v1",
            "video": "个体化生长",
            "target_section_id": TARGET_SECTION_ID,
            "target_block_id": TARGET_BLOCK_ID,
            "fixed_prompt": FIXED_PROMPT,
            "external_model_required": False,
        },
    }


def build_video2_learning_asset_bundle() -> dict[str, Any]:
    """构造演示中“再让我进行计算”所需的正式课程内练习。"""
    question = {
        "asset_id": "v2-q-composition-order",
        "question_id": "v2-q-composition-order",
        "revision_id": "v2-q-composition-order-r1",
        "task_revision_id": "v2-q-composition-order-r1",
        "node_id": TARGET_SECTION_ID,
        "status": "active",
        "practice_level": "concept_check",
        "question_type": "worked_solution",
        "prompt": (
            "设 B 先将向量逆时针旋转 90°，A 再把横坐标放大 2 倍。"
            "对 v=(1,0)ᵀ：先写出中间状态 Bv，再写出最终状态 A(Bv)，"
            "最后解释矩阵表达式为什么写成 ABv。"
        ),
        "learning_objective": "用中间状态解释复合变换的执行顺序。",
        "rubric": [
            "写出并核对 Bv",
            "在 Bv 上继续应用 A",
            "用作用对象而不是字母位置解释顺序",
        ],
        "course_knowledge_refs": [],
        "course_skill_refs": [],
        "course_misconception_refs": [],
    }
    return {
        "schema_version": "learning_assets_v2",
        "course_id": COURSE_ID,
        "plan": {
            "schema_version": "learning_asset_plan_v1",
            "course_purpose": "systematic",
            "enabled_asset_types": ["overview", "questions", "validation_questions"],
        },
        "assets": {
            "overview": {
                "title": COURSE_TITLE,
                "summary": "从几何对象、坐标表示和连续变换三个层次理解矩阵。",
            },
            "questions": [deepcopy(question)],
            "validation_questions": [deepcopy(question)],
            "mastery_criteria": [{
                "node_id": TARGET_SECTION_ID,
                "criterion": "能够独立说明输入、中间状态与最终状态的对应关系。",
            }],
            "misconceptions": [{
                "node_id": TARGET_SECTION_ID,
                "name": "把矩阵乘法只理解为行乘列",
                "repair_strategy": "先画状态链，再回到矩阵表达式。",
            }],
            "checklist": [
                "我能说清每个矩阵作用于哪个状态",
                "我能先预测图形变化，再进行坐标计算",
                "我能检查交换顺序是否改变结果",
            ],
        },
    }


def prepare_video2_demo(data_dir: str | Path) -> dict[str, Any]:
    """把指定 data 目录重置为可直接录制视频二的起点。"""
    root = Path(data_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    _clear_previous_demo_state(root)

    course = build_video2_course_envelope()
    storage = Storage(str(root))
    storage.delete_course(COURSE_ID)
    storage.save_course_sync(COURSE_ID, course)

    asset_repository = LearningAssetRepository(root / "learning_assets")
    asset_repository.delete_course(COURSE_ID)
    stored_assets = asset_repository.save_bundle(
        COURSE_ID,
        build_video2_learning_asset_bundle(),
    )
    return {
        "course_id": COURSE_ID,
        "course_title": COURSE_TITLE,
        "target_section_id": TARGET_SECTION_ID,
        "target_block_id": TARGET_BLOCK_ID,
        "learner_id": DEMO_USER_ID,
        "fixed_prompt": FIXED_PROMPT,
        "course_revision": course["course_document_revision"],
        "learning_asset_bundle_revision": stored_assets["bundle_revision_id"],
        "course_file": str(root / "courses" / f"{COURSE_ID}.json"),
        "relative_url": f"/course/{COURSE_ID}/learn/{TARGET_SECTION_ID}",
        "external_model_required": False,
    }


def _clear_previous_demo_state(data_dir: Path) -> None:
    """只移除录屏专用课程及其派生状态，不触碰其他课程。"""
    courses_dir = data_dir / "courses"
    if courses_dir.exists():
        for path in courses_dir.glob(f"{COURSE_ID}*.json"):
            path.unlink()

    for directory_name in (
        "learning_assets",
        "question_banks",
        "course_versions",
        "teaching_representations",
        "generation_workspaces",
    ):
        directory = data_dir / directory_name / COURSE_ID
        if directory.exists():
            shutil.rmtree(directory)
        file_path = data_dir / directory_name / f"{COURSE_ID}.json"
        if file_path.exists():
            file_path.unlink()

    scoped_key = hashlib.sha256(
        f"{DEMO_USER_ID}\0{COURSE_ID}".encode("utf-8"),
    ).hexdigest()
    for directory_name in (
        "ai_teacher",
        "course_evolution",
        "diagnostic_workflows",
        "learning_records",
        "learning_snapshots",
        "practice_attempts",
    ):
        directory = data_dir / directory_name
        exact_path = directory / f"{scoped_key}.json"
        if exact_path.exists():
            exact_path.unlink()
        _remove_scoped_json_files(directory, COURSE_ID)

    _filter_learning_events(data_dir / "learning_events.json")


def _remove_scoped_json_files(directory: Path, course_id: str) -> None:
    """删除明确属于专用课程的分片文件；混合数据文件不会被删除。"""
    if not directory.exists():
        return
    for path in directory.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if _is_course_scoped_payload(payload, course_id):
            path.unlink()


def _is_course_scoped_payload(payload: Any, course_id: str) -> bool:
    if isinstance(payload, dict):
        if str(payload.get("course_id") or "") == course_id:
            return True
        scoped_rows: list[dict[str, Any]] = []
        for key in ("conversations", "proposals", "receipts", "suppressions"):
            rows = payload.get(key)
            if isinstance(rows, list):
                scoped_rows.extend(row for row in rows if isinstance(row, dict))
        return bool(scoped_rows) and all(
            str(row.get("course_id") or "") == course_id
            for row in scoped_rows
        )
    if isinstance(payload, list) and payload:
        return all(
            isinstance(row, dict)
            and str(row.get("course_id") or "") == course_id
            for row in payload
        )
    return False


def _filter_learning_events(path: Path) -> None:
    if not path.exists():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if isinstance(payload, list):
        filtered = [
            item for item in payload
            if not isinstance(item, dict)
            or str(item.get("course_id") or "") != COURSE_ID
        ]
        if filtered != payload:
            _write_json(path, filtered)
        return
    if isinstance(payload, dict) and isinstance(payload.get("events"), list):
        filtered = [
            item for item in payload["events"]
            if not isinstance(item, dict)
            or str(item.get("course_id") or "") != COURSE_ID
        ]
        if filtered != payload["events"]:
            payload["events"] = filtered
            _write_json(path, payload)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    try:
        temp.write_text(
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n",
            encoding="utf-8",
        )
        temp.replace(path)
    finally:
        if temp.exists():
            temp.unlink()


def _chapter(
    section_id: str,
    title: str,
    position: int,
    objective: str,
) -> CourseSection:
    return CourseSection(
        section_id=section_id,
        title=title,
        position=position,
        level=1,
        learning_objective=objective,
        attributes={"chapter_summary": objective},
    )


def _lesson(
    section_id: str,
    parent_section_id: str,
    title: str,
    position: int,
    objective: str,
    *,
    key_points: list[str],
    knowledge_structure: list[dict[str, Any]],
) -> CourseSection:
    objective_id = f"v2-obj-{section_id.removeprefix('v2-sec-')}"
    return CourseSection(
        section_id=section_id,
        parent_section_id=parent_section_id,
        title=title,
        position=position,
        level=2,
        learning_objective=objective,
        objective_id=objective_id,
        objective_revision_id=f"{objective_id}-r1",
        attributes={
            "key_points": key_points,
            "knowledge_structure": knowledge_structure,
            "estimated_minutes": 35,
            "difficulty": "intermediate",
        },
    )


def _knowledge_structure(
    concept_group: str,
    knowledge_points: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [{
        "concept_group": concept_group,
        "description": f"围绕“{concept_group}”建立可解释、可迁移、可检查的理解。",
        "knowledge_points": knowledge_points,
    }]


def _knowledge_point(
    name: str,
    statement: str,
    *,
    capability: str,
    mastery: str,
    misconception: dict[str, Any] | None = None,
    relations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    point = {
        "name": name,
        "statement": statement,
        "knowledge_type": "principle",
        "conditions": ["使用同一个输入对象追踪变换过程"],
        "boundaries": ["坐标计算不等于完整的几何解释"],
        "capability_points": [{
            "name": capability,
            "observable_behavior": capability,
        }],
        "mastery_criteria": [{
            "name": f"{name}达标",
            "observable_performance": mastery,
            "verification_method": "完成一道独立解释题并核对中间状态",
        }],
        "relations": relations or [],
    }
    if misconception:
        point["misconceptions"] = [misconception]
    return point


def _block(
    block_id: str,
    section_id: str,
    position: int,
    title: str,
    markdown: str,
    *,
    role: str,
    kind: str = "rich_text",
) -> CourseBlock:
    objective_id = f"v2-obj-{section_id.removeprefix('v2-sec-')}"
    return CourseBlock(
        block_id=block_id,
        section_id=section_id,
        position=position,
        kind=kind,
        role=role,
        payload={
            "title": title,
            "markdown": markdown.strip(),
            "summary": markdown.strip().split("\n", 1)[0],
        },
        objective_refs=[objective_id],
        status="final",
    )


def _blocks_1_1() -> list[CourseBlock]:
    section = "v2-sec-1-1"
    return [
        _block(
            "v2-b-1-1-orientation",
            section,
            0,
            "从箭头开始",
            """
在平面上，向量不是一个固定的点，而是“从哪里出发并不重要”的有向位移。
把箭头平移到任意位置，只要方向和长度不变，它仍表示同一个向量。
            """,
            role="orientation",
        ),
        _block(
            "v2-b-1-1-objective",
            section,
            1,
            "本节目标",
            r"""
- 在几何箭头与坐标列向量之间来回转换；
- 把 \(v=(x,y)^\mathsf{T}\) 写成 \(v=x e_1+y e_2\)；
- 区分“向量本身”与“向量在某组基下的坐标”。
            """,
            role="objective",
            kind="callout",
        ),
        _block(
            "v2-b-1-1-concept",
            section,
            2,
            "坐标是对两个基方向的回答",
            r"""
标准基向量为
\[
e_1=(1,0)^\mathsf{T},\qquad e_2=(0,1)^\mathsf{T}.
\]
因此 \(v=(3,2)^\mathsf{T}\) 的意思是：沿 \(e_1\) 走 3 份，再沿 \(e_2\) 走 2 份。
坐标 \((3,2)\) 记录的是这两个方向各占多少。
            """,
            role="concept",
        ),
        _block(
            "v2-b-1-1-example",
            section,
            3,
            "例：同一个箭头的两种读法",
            r"""
若箭头从原点指向 \((2,-1)\)，则
\[
v=(2,-1)^\mathsf{T}=2e_1-e_2.
\]
几何上，它向右 2 个单位、向下 1 个单位；代数上，两个系数就是坐标。
            """,
            role="example",
        ),
        _block(
            "v2-b-1-1-check",
            section,
            4,
            "理解检查",
            r"""
画出 \(v=(-1,2)^\mathsf{T}\)，再回答：如果更换一组倾斜的基向量，
箭头本身会不会改变？它的两个坐标系数会不会改变？
            """,
            role="checkpoint",
            kind="practice_ref",
        ),
    ]


def _blocks_1_2() -> list[CourseBlock]:
    section = TARGET_SECTION_ID
    return [
        _block(
            TARGET_BLOCK_ID,
            section,
            0,
            "从图形动作看矩阵",
            r"""
想象单位正方形画在一张透明胶片上。矩阵 \(A\) 不是一张数字表，
而是一台同时移动胶片上每个向量的机器：它可以缩放、旋转、剪切，
也可以把这些动作组合起来。
            """,
            role="orientation",
        ),
        _block(
            "v2-b-1-2-objective",
            section,
            1,
            "本节目标",
            r"""
- 根据矩阵的两列判断两个标准基向量去了哪里；
- 完成矩阵与向量、矩阵与矩阵的乘法；
- 通过计算比较 \(AB\) 与 \(BA\)，为后续理解复合变换做准备。
            """,
            role="objective",
            kind="callout",
        ),
        _block(
            "v2-b-1-2-concept",
            section,
            2,
            "矩阵的两列就是两张方向说明书",
            r"""
设矩阵 \(A\) 的四个元素为 \(a,b,c,d\)，它们的排列是：
\[
\begin{bmatrix}a&b\\ c&d\end{bmatrix}
\]
第一列 \(Ae_1=(a,c)^\mathsf{T}\) 告诉我们水平方向如何变化；
第二列 \(Ae_2=(b,d)^\mathsf{T}\) 告诉我们竖直方向如何变化。
只要知道这两个基方向的去向，整个平面上的线性变换就被确定了。
            """,
            role="concept",
        ),
        _block(
            "v2-b-1-2-reasoning",
            section,
            3,
            "为什么两列足以决定所有向量",
            r"""
因为任意向量都能写成 \(v=xe_1+ye_2\)，线性变换保持线性组合：
\[
Av=A(xe_1+ye_2)=xAe_1+yAe_2.
\]
这说明矩阵乘法的行列规则并非孤立口诀，它是在计算两个变换后基方向的线性组合。
            """,
            role="reasoning",
        ),
        _block(
            "v2-b-1-2-example",
            section,
            4,
            "例：先把计算做稳",
            r"""
取剪切矩阵 \(A\)：
\[
\begin{bmatrix}1&1\\ 0&1\end{bmatrix}
\]
再取逆时针旋转 90° 的矩阵 B：
\[
\begin{bmatrix}0&-1\\ 1&0\end{bmatrix}
\]
按行乘列可得
\[
\begin{bmatrix}1&-1\\ 1&0\end{bmatrix}
\]
这就是乘积矩阵 \(AB\)。它的第一列与第二列仍可分别读成：
两个基向量 \(e_1\)、\(e_2\) 被送到了哪里。
            """,
            role="example",
        ),
        _block(
            "v2-b-1-2-misconception",
            section,
            5,
            "别把“不交换”只背成一句话",
            r"""
继续计算会发现
\[
\begin{bmatrix}0&-1\\ 1&1\end{bmatrix}
\]
这是交换顺序后的乘积矩阵 \(BA\)，它与 \(AB\) 不相等。
本节先确认计算事实：交换两个矩阵通常会改变结果。
下一节将把这个差异还原成连续动作，解释它为什么发生。
            """,
            role="misconception",
            kind="callout",
        ),
        _block(
            "v2-b-1-2-check",
            section,
            6,
            "本节理解检查",
            r"""
1. 计算 \(AB(1,0)^\mathsf{T}\)；
2. 用乘积矩阵的第一列核对结果；
3. 再计算 \(BA(1,0)^\mathsf{T}\)，只描述两个结果哪里不同，暂不背诵顺序规则。
            """,
            role="checkpoint",
            kind="practice_ref",
        ),
    ]


def _blocks_1_3() -> list[CourseBlock]:
    section = "v2-sec-1-3"
    return [
        _block(
            "v2-b-1-3-orientation",
            section,
            0,
            "两次动作之间必须有中间状态",
            """
旋转之后再拉伸，和拉伸之后再旋转，得到的图形通常不同。
要读懂复合变换，不能只看两个矩阵字母，必须保留第一次动作产生的中间状态。
            """,
            role="orientation",
        ),
        _block(
            "v2-b-1-3-objective",
            section,
            1,
            "本节目标",
            r"""
- 把连续动作写成 \(v\mapsto Bv\mapsto A(Bv)\)；
- 比较调换动作顺序后的最终状态；
- 用输入输出关系解释矩阵乘积，而不是只复述行乘列。
            """,
            role="objective",
            kind="callout",
        ),
        _block(
            "v2-b-1-3-concept",
            section,
            2,
            "复合就是把前一步输出交给下一步",
            r"""
若 \(B\) 接收原始输入 \(v\)，输出中间状态 \(Bv\)；
随后 \(A\) 接收这个中间状态，输出 \(A(Bv)\)。
矩阵乘法把这条两步状态链压缩成一个乘积矩阵。
            """,
            role="concept",
        ),
        _block(
            "v2-b-1-3-example",
            section,
            3,
            "例：旋转与水平拉伸",
            r"""
令 \(B\) 表示逆时针旋转 \(90^\circ\)，\(A\) 表示横坐标放大 2 倍。
从 \(v=(1,0)^\mathsf{T}\) 出发，先逐步计算中间向量，再把每个结果画在同一坐标系中。
交换两个动作后重新作图，即可看到最终状态不同。
            """,
            role="example",
        ),
        _block(
            "v2-b-1-3-check",
            section,
            4,
            "理解检查",
            """
不要先写乘积。先画三格状态图：输入、第一次变化、第二次变化。
然后再用一个矩阵表达式压缩这三格图，并说明每个字母的作用对象。
            """,
            role="checkpoint",
            kind="practice_ref",
        ),
    ]


def _blocks_2_1() -> list[CourseBlock]:
    section = "v2-sec-2-1"
    return [
        _block(
            "v2-b-2-1-orientation",
            section,
            0,
            "向量没变，坐标为什么变了",
            """
同一条校园道路，可以用“向东、向北”描述，也可以用“沿主路、沿支路”描述。
对象没有变化，改变的是我们用来度量它的基底。
            """,
            role="orientation",
        ),
        _block(
            "v2-b-2-1-concept",
            section,
            1,
            "基矩阵连接两套坐标",
            r"""
把新基向量按列排成矩阵 \(P\)。新坐标 \([v]_{\text{new}}\)
经过 \(P\) 后还原成标准坐标 \(v\)：
\[
v=P[v]_{\text{new}}.
\]
反过来，\(P^{-1}\) 把标准坐标写回新基坐标。
            """,
            role="concept",
        ),
        _block(
            "v2-b-2-1-reasoning",
            section,
            2,
            "相似变换是一条完整状态链",
            r"""
在新基下表示线性变换 \(A\) 时，需要依次经历：
新坐标 \(\rightarrow\) 标准坐标 \(\rightarrow\) 执行 \(A\)
\(\rightarrow\) 写回新坐标。每一步都必须接收上一步的输出。
            """,
            role="reasoning",
        ),
        _block(
            "v2-b-2-1-check",
            section,
            3,
            "理解检查",
            """
为一条坐标变换公式标注四个状态：输入坐标、还原后的向量、
变换后的向量、目标坐标。若删去中间任一步，说明对象类型在哪里不匹配。
            """,
            role="checkpoint",
            kind="practice_ref",
        ),
    ]


def _blocks_2_2() -> list[CourseBlock]:
    section = "v2-sec-2-2"
    return [
        _block(
            "v2-b-2-2-orientation",
            section,
            0,
            "逆矩阵不是倒数，而是撤销动作",
            """
如果一个变换把每个输入都送到唯一输出，并且没有压扁任何方向，
我们就有机会沿相反路径找回原始输入。这个反向过程由逆矩阵表示。
            """,
            role="orientation",
        ),
        _block(
            "v2-b-2-2-concept",
            section,
            1,
            "可逆意味着信息没有丢失",
            r"""
当 \(\det(A)\neq0\) 时，\(A\) 不会把整个平面压到一条线或一个点，
因此存在 \(A^{-1}\)，并满足
\[
A^{-1}(Av)=v.
\]
            """,
            role="concept",
        ),
        _block(
            "v2-b-2-2-example",
            section,
            2,
            "例：撤销一次缩放与剪切",
            """
先选一个具体向量，执行缩放与剪切得到输出；再使用逆矩阵还原。
核对时不仅比较最终数字，还要检查逆向过程是否逐步撤销了原来的几何动作。
            """,
            role="example",
        ),
        _block(
            "v2-b-2-2-check",
            section,
            3,
            "理解检查",
            """
若一个矩阵把两个不同向量送到同一个输出，它还能有逆矩阵吗？
请从“能否唯一还原输入”解释，而不是只引用行列式公式。
            """,
            role="checkpoint",
            kind="practice_ref",
        ),
    ]


def _blocks_2_3() -> list[CourseBlock]:
    section = "v2-sec-2-3"
    return [
        _block(
            "v2-b-2-3-orientation",
            section,
            0,
            "一幅画面背后是一条变换管线",
            """
图形对象先在自己的局部坐标中建模，再放入场景，最后投射到观察画面。
屏幕上的一个点，往往经历了不止一次矩阵变换。
            """,
            role="orientation",
        ),
        _block(
            "v2-b-2-3-concept",
            section,
            1,
            "每一层只做一件事",
            """
对象变换负责形状与姿态，场景变换负责摆放位置，观察变换负责视角。
把职责拆开后，我们既能组合矩阵，也能在结果异常时定位是哪一层出了问题。
            """,
            role="concept",
        ),
        _block(
            "v2-b-2-3-application",
            section,
            2,
            "应用：让一个图标绕指定中心旋转",
            """
先把旋转中心移到原点，再执行旋转，最后移回原位置。
请先画出三个中间状态，再写出组合表达式；交换任意两步，观察图标轨迹如何改变。
            """,
            role="application",
        ),
        _block(
            "v2-b-2-3-summary",
            section,
            3,
            "课程小结",
            """
矩阵是一种变换语言：列向量说明基方向的去向，乘法连接连续动作，
逆矩阵撤销动作，基变换与图形管线则把同一结构迁移到更复杂的系统。
            """,
            role="summary",
            kind="callout",
        ),
    ]


__all__ = [
    "COURSE_ID",
    "COURSE_TITLE",
    "DEMO_USER_ID",
    "FIXED_PROMPT",
    "TARGET_BLOCK_ID",
    "TARGET_SECTION_ID",
    "build_video2_course_document",
    "build_video2_course_envelope",
    "build_video2_learning_asset_bundle",
    "prepare_video2_demo",
]
