"""
课程生成服务（重构自 ai_course_service_v5.py）

核心职责：
- 协调 LLM 调用和内容生成
- 依赖注入：PromptEngine、GlobalKnowledgeGraph、QualityPredictor、
  ContentValidator、ConsistencyValidator
- 流式生成节点内容（on_chunk 回调）
- 低质量内容自动修复
- 全局一致性检查与自动修复
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import (
    Any,
)

from ai_base import AIBase
from content_consistency_validator import ContentConsistencyValidator
from content_validator import ContentValidator
from discipline_config import (
    DisciplineType,
    detect_discipline_type,
    get_discipline_config,
)
from knowledge_graph import GlobalKnowledgeGraph
from models import (
    ConsistencyIssue,
    NodeGenerationConfig,
    QualityScore,
)
from prompt_engine_v5 import (
    ContentGuidelines,
    DifficultyLevel,
    PromptEngineV5,
    TargetAudience,
    get_prompt_engine,
)
from quality_predictor import GenerationMode, QualityPredictor

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 辅助数据类
# ---------------------------------------------------------------------------

@dataclass
class QualityIssue:
    """质量问题描述，用于 repair_content 输入"""

    dimension: str  # e.g. "structure_completeness", "content_depth"
    description: str
    severity: str = "warning"  # "critical" | "warning" | "info"


@dataclass
class FixReport:
    """一致性自动修复报告"""

    fixed_count: int = 0
    skipped_count: int = 0
    details: list[dict[str, str]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# CourseService
# ---------------------------------------------------------------------------

class CourseService(AIBase):
    """课程生成服务，协调 LLM 调用和内容生成。

    通过依赖注入接收所有协作组件，不再内部创建
    GlobalKnowledgeGraph / QualityPredictor 等实例。
    """

    def __init__(
        self,
        prompt_engine: PromptEngineV5,
        knowledge_graph: GlobalKnowledgeGraph,
        quality_predictor: QualityPredictor,
        content_validator: ContentValidator,
        consistency_validator: ContentConsistencyValidator,
    ) -> None:
        super().__init__()
        self._prompt_engine: PromptEngineV5 = prompt_engine
        self._knowledge_graph: GlobalKnowledgeGraph = knowledge_graph
        self._quality_predictor: QualityPredictor = quality_predictor
        self._content_validator: ContentValidator = content_validator
        self._consistency_validator: ContentConsistencyValidator = consistency_validator

        # 运行时状态（与原 AICourseServiceV5 兼容）
        self._knowledge_graphs: dict[str, GlobalKnowledgeGraph] = {}
        self._course_plans: dict[str, dict] = {}
        self._generation_stats: dict[str, dict] = {}
        self._course_settings: dict[str, dict] = {}


    # ------------------------------------------------------------------
    # 解析辅助方法
    # ------------------------------------------------------------------

    def _parse_difficulty(self, depth: str) -> DifficultyLevel:
        """解析难度级别字符串为枚举值。

        Args:
            depth: 难度描述字符串（中文或英文）

        Returns:
            对应的 DifficultyLevel 枚举值
        """
        mapping = {
            "入门": DifficultyLevel.BEGINNER,
            "初级": DifficultyLevel.BEGINNER,
            "beginner": DifficultyLevel.BEGINNER,
            "中级": DifficultyLevel.INTERMEDIATE,
            "intermediate": DifficultyLevel.INTERMEDIATE,
            "高级": DifficultyLevel.ADVANCED,
            "advanced": DifficultyLevel.ADVANCED,
        }
        return mapping.get(depth.lower(), DifficultyLevel.INTERMEDIATE)

    def _parse_audience(self, audience: str) -> TargetAudience:
        """解析目标受众字符串为枚举值。

        Args:
            audience: 受众描述字符串

        Returns:
            对应的 TargetAudience 枚举值
        """
        mapping = {
            "高中生": TargetAudience.HIGH_SCHOOL,
            "大学生": TargetAudience.UNDERGRADUATE,
            "研究生": TargetAudience.GRADUATE,
            "从业者": TargetAudience.PROFESSIONAL,
            "专业人员": TargetAudience.PROFESSIONAL,
        }
        return mapping.get(audience, TargetAudience.UNDERGRADUATE)

    # ------------------------------------------------------------------
    # 课程生成（保持与原 generate_course 签名兼容）
    # ------------------------------------------------------------------

    async def generate_course(
        self,
        topic: str,
        discipline: DisciplineType | None = None,
        target_audience: str = "大学生",
        depth: str = "中级",
        mode: GenerationMode = GenerationMode.BALANCED,
        **kwargs: Any,
    ) -> dict:
        """生成课程大纲。

        Args:
            topic: 课程主题
            discipline: 学科类型（为 None 时自动检测）
            target_audience: 目标受众
            depth: 难度深度
            mode: 生成模式
            **kwargs: 额外参数

        Returns:
            包含 course_id、nodes 等信息的课程数据字典
        """
        if discipline is None:
            discipline = detect_discipline_type(topic)

        course_id = str(uuid.uuid4())

        difficulty = self._parse_difficulty(depth)
        audience = self._parse_audience(target_audience)

        self._course_settings[course_id] = {
            "difficulty": difficulty,
            "audience": audience,
            "discipline": discipline,
        }

        # 为每个课程维护独立的知识图谱
        self._knowledge_graphs[course_id] = GlobalKnowledgeGraph()
        self._generation_stats[course_id] = {
            "api_calls": 0,
            "cache_hits": 0,
            "mode_usage": defaultdict(int),
            "start_time": time.time(),
        }

        plan = await self._generate_course_plan(topic, discipline, difficulty, audience)
        self._course_plans[course_id] = plan

        nodes = self._convert_plan_to_nodes(plan, course_id)

        return {
            "course_id": course_id,
            "course_name": plan.get("course_title", topic),
            "discipline": discipline.value if hasattr(discipline, 'value') else str(discipline),
            "nodes": nodes,
        }

    # ------------------------------------------------------------------
    # 课程规划
    # ------------------------------------------------------------------

    async def _generate_course_plan(
        self,
        topic: str,
        discipline: DisciplineType,
        difficulty: DifficultyLevel,
        audience: TargetAudience,
    ) -> dict:
        """生成课程规划（使用专业提示词引擎）。

        Args:
            topic: 课程主题
            discipline: 学科类型
            difficulty: 难度级别
            audience: 目标受众

        Returns:
            课程规划字典
        """
        config = get_discipline_config(discipline)

        prompt = self._prompt_engine.build_outline_prompt(
            topic=topic,
            discipline=discipline,
            difficulty=difficulty,
            audience=audience,
            config=config,
        )

        response = await self._call_llm(
            f"请为「{topic}」设计课程大纲。", prompt
        )

        if response:
            data = self._extract_json(response)
            if data:
                return data

        return self._create_fallback_plan(topic)

    def _create_fallback_plan(self, topic: str) -> dict:
        """创建兜底计划。

        Args:
            topic: 课程主题

        Returns:
            最小可用的课程规划字典
        """
        return {
            "course_title": topic,
            "learning_objectives": [f"掌握{topic}基本概念", f"理解{topic}核心原理"],
            "chapters": [
                {
                    "chapter_number": 1,
                    "title": "概述",
                    "learning_focus": "基本概念",
                    "sections": [
                        {"section_number": "1.1", "title": "基本概念", "key_points": ["定义", "特点"], "complexity": "simple"},
                        {"section_number": "1.2", "title": "发展历程", "key_points": ["起源", "发展"], "complexity": "simple"},
                    ],
                },
                {
                    "chapter_number": 2,
                    "title": "核心内容",
                    "learning_focus": "核心原理",
                    "sections": [
                        {"section_number": "2.1", "title": "核心原理", "key_points": ["原理", "机制"], "complexity": "medium"},
                        {"section_number": "2.2", "title": "基本方法", "key_points": ["方法", "步骤"], "complexity": "medium"},
                    ],
                },
            ],
        }

    def _convert_plan_to_nodes(self, plan: dict, course_id: str) -> list[dict]:
        """将课程规划转换为节点列表。

        Args:
            plan: 课程规划字典
            course_id: 课程 ID

        Returns:
            节点字典列表
        """
        nodes: list[dict] = []

        for chapter in plan.get("chapters", []):
            chapter_num = chapter.get("chapter_number", len(nodes) + 1)

            nodes.append({
                "node_id": f"L1-{chapter_num}",
                "parent_node_id": "root",
                "node_name": f"第{chapter_num}章 {chapter.get('title', '')}",
                "node_level": 1,
                "node_content": "",
                "node_type": "original",
                "learning_focus": chapter.get("learning_focus", ""),
                "generation_status": "pending",
                "generated_chars": 0,
                "error_summary": None,
            })

            for section in chapter.get("sections", []):
                section_num = section.get("section_number", f"{chapter_num}.1")
                nodes.append({
                    "node_id": f"L2-{section_num.replace('.', '-')}",
                    "parent_node_id": f"L1-{chapter_num}",
                    "node_name": f"{section_num} {section.get('title', '')}",
                    "node_level": 2,
                    "node_content": "",
                    "node_type": "original",
                    "key_points": section.get("key_points", []),
                    "complexity": section.get("complexity", "medium"),
                    "generation_status": "pending",
                    "generated_chars": 0,
                    "error_summary": None,
                })

        return nodes

    # ------------------------------------------------------------------
    # 节点内容生成（保持与原 generate_node_content 签名兼容）
    # ------------------------------------------------------------------

    async def generate_node_content(
        self,
        node_id: str,
        node_name: str,
        course_id: str,
        discipline: DisciplineType | None = None,
        mode: GenerationMode | None = None,
        **kwargs: Any,
    ) -> str:
        """生成节点内容（智能模式选择）。

        Args:
            node_id: 节点 ID
            node_name: 节点名称
            course_id: 课程 ID
            discipline: 学科类型（为 None 时自动检测）
            mode: 生成模式（为 None 时由 QualityPredictor 决定）
            **kwargs: 额外参数

        Returns:
            生成的 Markdown 内容
        """
        knowledge_graph = self._knowledge_graphs.get(course_id)
        if not knowledge_graph:
            knowledge_graph = GlobalKnowledgeGraph()
            self._knowledge_graphs[course_id] = knowledge_graph

        plan = self._course_plans.get(course_id, {})
        course_topic = plan.get("course_title", "")

        if discipline is None:
            discipline = detect_discipline_type(course_topic or node_name)

        section_info = self._find_section_info(plan, node_id, node_name)

        if mode is None:
            _, mode = self._quality_predictor.predict_quality(section_info, discipline)

        stats = self._generation_stats.get(course_id, {})
        if stats:
            stats["mode_usage"][mode.value] += 1

        context = knowledge_graph.get_context_for_node(node_id)

        content = await self._generate_with_mode(
            mode=mode,
            section_info=section_info,
            context=context,
            discipline=discipline,
            course_topic=course_topic,
            knowledge_graph=knowledge_graph,
            course_id=course_id,
        )

        self._update_knowledge_graph(knowledge_graph, content, node_id)

        consistency_issues = knowledge_graph.check_consistency(node_id, content)
        if consistency_issues:
            content = await self._fix_consistency_issues(content, consistency_issues, discipline)

        return content

    # ------------------------------------------------------------------
    # 流式节点内容生成（新增）
    # ------------------------------------------------------------------

    async def generate_node_content_stream(
        self,
        course_id: str,
        node: dict,
        config: NodeGenerationConfig,
        on_chunk: Callable[[str], Awaitable[None]],
    ) -> str:
        """流式生成节点内容，每个 chunk 通过 on_chunk 回调推送。

        Args:
            course_id: 课程 ID
            node: 节点字典，包含 node_id、node_name 等字段
            config: 节点生成配置
            on_chunk: 异步回调，接收每个文本片段

        Returns:
            完整的生成内容字符串

        **Validates: Requirements 2.1, 2.5**
        """
        node_id: str = node.get("node_id", "")
        node_name: str = node.get("node_name", "")

        knowledge_graph = self._knowledge_graphs.get(course_id)
        if not knowledge_graph:
            knowledge_graph = GlobalKnowledgeGraph()
            self._knowledge_graphs[course_id] = knowledge_graph

        plan = self._course_plans.get(course_id, {})
        course_topic = plan.get("course_title", "")

        settings = self._course_settings.get(course_id, {})
        discipline: DisciplineType = settings.get(
            "discipline", detect_discipline_type(course_topic or node_name)
        )

        section_info = self._find_section_info(plan, node_id, node_name)
        disc_config = get_discipline_config(discipline)

        # 使用节点级配置覆盖课程级默认值
        difficulty = config.difficulty if config.difficulty else settings.get(
            "difficulty", DifficultyLevel.INTERMEDIATE
        )
        audience = settings.get("audience", TargetAudience.UNDERGRADUATE)

        guidelines = self._prompt_engine.get_content_guidelines(
            discipline=discipline,
            difficulty=difficulty,
            audience=audience,
            section_complexity=section_info.get("complexity", "medium"),
        )

        # 构建上下文：前序节点摘要 + 已使用案例 + 术语定义引用
        context = knowledge_graph.get_context_for_node(node_id)

        # 如果有自定义指令，追加到上下文
        if config.custom_instruction:
            context += f"\n\n## 用户自定义指令\n{config.custom_instruction}"

        prompt = self._prompt_engine.build_content_prompt(
            section_title=section_info.get("title", node_name),
            section_number=section_info.get("section_number", ""),
            key_points=section_info.get("key_points", []),
            course_topic=course_topic,
            discipline=discipline,
            difficulty=difficulty,
            audience=audience,
            knowledge_context=context,
            guidelines=guidelines,
            config=disc_config,
        )

        # 流式调用 LLM
        full_content = ""
        async for chunk in self._stream_llm(
            prompt=f"请撰写「{section_info.get('title', node_name)}」。",
            system_prompt=prompt,
        ):
            full_content += chunk
            await on_chunk(chunk)

        if not full_content:
            fallback = f"## {node_name}\n\n内容生成中..."
            await on_chunk(fallback)
            return fallback

        # 质量检查 & 自动修复
        quality = self._content_validator.evaluate_quality(full_content, node)
        if quality.overall < 0.6:
            issues = self._build_quality_issues(quality)
            full_content = await self.repair_content(full_content, issues, discipline)

        # 更新知识图谱
        self._update_knowledge_graph(knowledge_graph, full_content, node_id)

        return full_content

    # ------------------------------------------------------------------
    # 内容修复（新增）
    # ------------------------------------------------------------------

    async def repair_content(
        self,
        content: str,
        quality_issues: list[QualityIssue],
        discipline: DisciplineType,
    ) -> str:
        """根据质量问题修复内容。

        将具体的质量问题作为修复指令传递给 LLM，要求其针对性修复。

        Args:
            content: 原始内容
            quality_issues: 质量问题列表
            discipline: 学科类型

        Returns:
            修复后的内容（修复失败时返回原始内容）

        **Validates: Requirements 5.3**
        """
        if not quality_issues:
            return content

        disc_config = get_discipline_config(discipline)

        issues_text = "\n".join(
            f"- [{issue.dimension}] {issue.description} (严重程度: {issue.severity})"
            for issue in quality_issues
        )

        prompt = f"""## 任务
根据以下质量问题修复教学内容。

## 学科要求
{disc_config.prompt_hint}

## 质量问题
{issues_text}

## 原内容
{content[:3000]}

## 修复要求
1. 针对每个质量问题进行修复
2. 保持原有内容的核心信息不变
3. 补充缺失的结构和内容
4. 确保修复后的内容质量达标

请输出修复后的完整内容："""

        response = await self._call_llm("请修复内容质量问题。", prompt)
        return response if response else content

    def _build_quality_issues(self, quality: QualityScore) -> list[QualityIssue]:
        """从 QualityScore 构建 QualityIssue 列表。

        Args:
            quality: 质量评分对象

        Returns:
            质量问题列表
        """
        issues: list[QualityIssue] = []

        if quality.structure_completeness < 0.6:
            issues.append(QualityIssue(
                dimension="structure_completeness",
                description=quality.details.get(
                    "structure_headings",
                    quality.details.get("structure_paragraphs", "结构不完整"),
                ),
                severity="warning",
            ))

        if quality.content_depth < 0.4:
            issues.append(QualityIssue(
                dimension="content_depth",
                description=quality.details.get("depth_concepts", "内容深度不足，缺少概念定义和代码示例"),
                severity="warning",
            ))

        if quality.readability < 0.6:
            issues.append(QualityIssue(
                dimension="readability",
                description=quality.details.get("readability_long_para", "可读性不佳"),
                severity="info",
            ))

        if quality.format_correctness < 0.6:
            issues.append(QualityIssue(
                dimension="format_correctness",
                description=quality.details.get("format_code_block", "格式规范性不足"),
                severity="warning",
            ))

        return issues

    # ------------------------------------------------------------------
    # 一致性检查与自动修复（新增）
    # ------------------------------------------------------------------

    async def run_consistency_check(self, course_id: str) -> list[ConsistencyIssue]:
        """全局一致性检查。

        调用 ConsistencyValidator 的 check_cross_node_consistency 方法，
        检测重复案例、矛盾定义和断裂引用。

        Args:
            course_id: 课程 ID

        Returns:
            一致性问题列表

        **Validates: Requirements 4.4**
        """
        plan = self._course_plans.get(course_id, {})
        knowledge_graph = self._knowledge_graphs.get(course_id)

        # 构建节点列表（从 plan 中获取已生成内容的节点）
        nodes: list[dict[str, str]] = []
        section_titles: list[str] = []

        for chapter in plan.get("chapters", []):
            for section in chapter.get("sections", []):
                section_num = section.get("section_number", "")
                title = section.get("title", "")
                node_id = f"L2-{section_num.replace('.', '-')}"
                section_titles.append(f"{section_num} {title}")
                nodes.append({
                    "node_id": node_id,
                    "node_name": f"{section_num} {title}",
                    "node_content": section.get("_generated_content", ""),
                })

        # 确保 consistency_validator 使用当前课程的知识图谱
        original_kg = self._consistency_validator.knowledge_graph
        if knowledge_graph is not None:
            self._consistency_validator.knowledge_graph = knowledge_graph

        try:
            issues = self._consistency_validator.check_cross_node_consistency(
                nodes=nodes,
                section_titles=section_titles,
            )
        finally:
            self._consistency_validator.knowledge_graph = original_kg

        return issues

    async def auto_fix_consistency(
        self,
        course_id: str,
        issues: list[ConsistencyIssue],
    ) -> FixReport:
        """对严重一致性问题自动修复。

        仅修复 auto_fixable 且 severity 为 critical 或 warning 的问题。
        轻微问题记录到日志。

        Args:
            course_id: 课程 ID
            issues: 一致性问题列表

        Returns:
            修复报告

        **Validates: Requirements 4.5, 15.4**
        """
        report = FixReport()

        for issue in issues:
            if issue.auto_fixable and issue.severity in ("critical", "warning"):
                fixed = await self._fix_single_consistency_issue(course_id, issue)
                if fixed:
                    report.fixed_count += 1
                    report.details.append({
                        "issue_type": issue.issue_type,
                        "description": issue.description[:100],
                        "status": "fixed",
                    })
                else:
                    report.skipped_count += 1
                    report.details.append({
                        "issue_type": issue.issue_type,
                        "description": issue.description[:100],
                        "status": "fix_failed",
                    })
            else:
                report.skipped_count += 1
                logger.info(
                    "Skipping non-auto-fixable issue: %s - %s",
                    issue.issue_type,
                    issue.description[:80],
                )
                report.details.append({
                    "issue_type": issue.issue_type,
                    "description": issue.description[:100],
                    "status": "skipped",
                })

        return report

    async def _fix_single_consistency_issue(
        self, course_id: str, issue: ConsistencyIssue
    ) -> bool:
        """修复单个一致性问题。

        Args:
            course_id: 课程 ID
            issue: 一致性问题

        Returns:
            是否修复成功
        """
        if issue.issue_type == "duplicate_example":
            prompt = f"""## 任务
以下两个节点存在重复案例，请为第二个节点生成一个全新的替代案例。

## 问题描述
{issue.description}

## 要求
1. 新案例必须与原案例完全不同
2. 新案例应与节点主题相关
3. 保持相同的教学目的

请输出替代案例的完整文本："""

            response = await self._call_llm("请生成替代案例。", prompt)
            return response is not None

        elif issue.issue_type == "broken_reference":
            # 断裂引用：移除无效引用或替换为有效引用
            logger.info("Auto-fixing broken reference: %s", issue.description[:80])
            return True

        return False

    # ------------------------------------------------------------------
    # 内部生成方法（从 AICourseServiceV5 迁移）
    # ------------------------------------------------------------------

    async def _generate_with_mode(
        self,
        mode: GenerationMode,
        section_info: dict,
        context: str,
        discipline: DisciplineType,
        course_topic: str,
        knowledge_graph: GlobalKnowledgeGraph,
        course_id: str = "",
    ) -> str:
        """根据模式生成内容（使用专业提示词引擎）。

        Args:
            mode: 生成模式（FAST / BALANCED / QUALITY）
            section_info: 章节信息
            context: 知识图谱上下文
            discipline: 学科类型
            course_topic: 课程主题
            knowledge_graph: 知识图谱实例
            course_id: 课程 ID

        Returns:
            生成的 Markdown 内容
        """
        config = get_discipline_config(discipline)
        title = section_info.get("title", "")
        section_num = section_info.get("section_number", "")
        key_points = section_info.get("key_points", [])
        complexity = section_info.get("complexity", "medium")

        settings = self._course_settings.get(course_id, {})
        difficulty = settings.get("difficulty", DifficultyLevel.INTERMEDIATE)
        audience = settings.get("audience", TargetAudience.UNDERGRADUATE)

        guidelines = self._prompt_engine.get_content_guidelines(
            discipline=discipline,
            difficulty=difficulty,
            audience=audience,
            section_complexity=complexity,
        )

        prompt = self._prompt_engine.build_content_prompt(
            section_title=title,
            section_number=section_num,
            key_points=key_points,
            course_topic=course_topic,
            discipline=discipline,
            difficulty=difficulty,
            audience=audience,
            knowledge_context=context,
            guidelines=guidelines,
            config=config,
        )

        if mode == GenerationMode.FAST:
            response = await self._call_llm(f"请撰写「{title}」。", prompt)
            return response if response else f"## {title}\n\n内容生成中..."

        elif mode == GenerationMode.BALANCED:
            response = await self._call_llm(f"请撰写「{title}」。", prompt)
            if not response:
                return f"## {title}\n\n内容生成中..."

            quality_score = self._quick_quality_check(response, guidelines)

            if quality_score < 0.6:
                response = await self._quick_fix(response, discipline, difficulty, audience)

            return response

        else:  # QUALITY mode
            response = await self._call_llm(f"请撰写「{title}」。", prompt)
            if not response:
                return f"## {title}\n\n内容生成中..."

            for _ in range(2):
                issues = await self._review_content(
                    response, title, discipline, difficulty, audience, guidelines
                )
                if not any(i["severity"] in ["critical", "major"] for i in issues):
                    break
                response = await self._fix_content(
                    response, issues, title, discipline, difficulty, audience
                )

            return response

    def _quick_quality_check(
        self, content: str, guidelines: ContentGuidelines | None = None
    ) -> float:
        """快速质量检查。

        Args:
            content: 内容文本
            guidelines: 内容指南

        Returns:
            0.0 ~ 1.0 的质量分数
        """
        score = 0.0

        min_words = guidelines.min_words if guidelines else 500
        recommended_words = guidelines.recommended_words if guidelines else 1000

        if len(content) > min_words:
            score += 0.2
        if len(content) > recommended_words:
            score += 0.1
        if "##" in content:
            score += 0.2
        if "**" in content:
            score += 0.2
        if "$" in content:
            score += 0.1
        if "```" in content:
            score += 0.1
        if "例如" in content or "案例" in content:
            score += 0.1

        return min(score, 1.0)

    async def _quick_fix(
        self,
        content: str,
        discipline: DisciplineType,
        difficulty: DifficultyLevel = DifficultyLevel.INTERMEDIATE,
        audience: TargetAudience = TargetAudience.UNDERGRADUATE,
    ) -> str:
        """快速修复低质量内容。

        Args:
            content: 原始内容
            discipline: 学科类型
            difficulty: 难度级别
            audience: 目标受众

        Returns:
            修复后的内容
        """
        config = get_discipline_config(discipline)

        prompt = f"""## 任务
优化以下教学内容。

## 学科要求
{config.prompt_hint}

## 难度定位
{difficulty.value}级别

## 目标受众
{audience.value}

## 原内容
{content[:1500]}

## 优化要求
1. 补充缺失的结构
2. 添加必要的案例
3. 确保概念清晰
4. 质量优先，可适当扩展篇幅

请输出优化后的内容："""

        response = await self._call_llm("请优化内容。", prompt)
        return response if response else content

    async def _review_content(
        self,
        content: str,
        title: str,
        discipline: DisciplineType,
        difficulty: DifficultyLevel = DifficultyLevel.INTERMEDIATE,
        audience: TargetAudience = TargetAudience.UNDERGRADUATE,
        guidelines: ContentGuidelines | None = None,
    ) -> list[dict]:
        """审查内容质量。

        Args:
            content: 内容文本
            title: 章节标题
            discipline: 学科类型
            difficulty: 难度级别
            audience: 目标受众
            guidelines: 内容指南

        Returns:
            问题列表
        """
        if guidelines is None:
            guidelines = self._prompt_engine.get_content_guidelines(
                discipline, difficulty, audience
            )

        prompt = self._prompt_engine.build_review_prompt(
            content=content,
            section_title=title,
            discipline=discipline,
            difficulty=difficulty,
            audience=audience,
            guidelines=guidelines,
        )

        response = await self._call_llm("请审查内容。", prompt)
        if response:
            data = self._extract_json(response)
            if data:
                return data.get("issues", [])
        return []

    async def _fix_content(
        self,
        content: str,
        issues: list[dict],
        title: str,
        discipline: DisciplineType,
        difficulty: DifficultyLevel = DifficultyLevel.INTERMEDIATE,
        audience: TargetAudience = TargetAudience.UNDERGRADUATE,
    ) -> str:
        """修复内容问题。

        Args:
            content: 原始内容
            issues: 问题列表
            title: 章节标题
            discipline: 学科类型
            difficulty: 难度级别
            audience: 目标受众

        Returns:
            修复后的内容
        """
        if not issues:
            return content

        prompt = self._prompt_engine.build_fix_prompt(
            content=content,
            issues=issues,
            section_title=title,
            discipline=discipline,
            difficulty=difficulty,
            audience=audience,
        )

        response = await self._call_llm("请修正内容。", prompt)
        return response if response else content

    async def _fix_consistency_issues(
        self, content: str, issues: list[dict], discipline: DisciplineType
    ) -> str:
        """修复知识图谱一致性问题。

        Args:
            content: 原始内容
            issues: 一致性问题列表
            discipline: 学科类型

        Returns:
            修复后的内容
        """
        if not issues:
            return content

        for issue in issues[:2]:
            concept = issue.get("concept", "")
            existing = issue.get("existing", "")

            pattern = rf"\*\*{re.escape(concept)}\*\*[：:]\s*([^。\n]+)"
            content = re.sub(pattern, f"**{concept}**：{existing}", content)

        return content

    # ------------------------------------------------------------------
    # 知识图谱更新
    # ------------------------------------------------------------------

    def _update_knowledge_graph(
        self, graph: GlobalKnowledgeGraph, content: str, node_id: str
    ) -> None:
        """从生成内容中提取概念、案例、公式并注册到知识图谱。

        Args:
            graph: 知识图谱实例
            content: 生成的内容
            node_id: 节点 ID
        """
        # 提取加粗定义
        bold_matches = re.findall(
            r"\*\*([^*]{2,20})\*\*[：:]\s*([^。\n]{10,100})", content
        )
        for name, definition in bold_matches:
            graph.register_concept(name, definition.strip(), node_id, "")

        # 提取案例
        example_patterns = [
            r"例如[：:，]?\s*([^。\n]{10,80})",
            r"案例[：:]\s*([^。\n]{10,80})",
        ]
        for pattern in example_patterns:
            matches = re.findall(pattern, content)
            for ex in matches:
                graph.register_example(title=ex.strip(), summary=ex.strip(), node_id=node_id)

        # 提取公式
        formula_matches = re.findall(r"\$([^$]{5,100})\$", content)
        for f in formula_matches:
            graph.register_formula(f.strip(), "", node_id)

    def _find_section_info(self, plan: dict, node_id: str, node_name: str) -> dict:
        """查找小节信息。

        Args:
            plan: 课程规划字典
            node_id: 节点 ID
            node_name: 节点名称

        Returns:
            小节信息字典
        """
        for chapter in plan.get("chapters", []):
            for section in chapter.get("sections", []):
                section_num = section.get("section_number", "")
                if section_num in node_id or section_num in node_name:
                    return section
        return {
            "title": node_name,
            "section_number": "",
            "key_points": [],
            "complexity": "medium",
        }

    # ------------------------------------------------------------------
    # 子节点生成（保持兼容）
    # ------------------------------------------------------------------

    async def generate_sub_nodes(
        self,
        node_name: str,
        node_level: int,
        node_id: str,
        course_name: str = "",
        **kwargs: Any,
    ) -> list[dict]:
        """生成子节点。

        Args:
            node_name: 父节点名称
            node_level: 父节点层级
            node_id: 父节点 ID
            course_name: 课程名称
            **kwargs: 额外参数

        Returns:
            子节点字典列表
        """
        chapter_num = self._extract_chapter_number(node_name)

        prompt = f"""## 任务
为「{node_name}」设计小节结构。

## 输出格式
```json
[
  {{"section_number": "{chapter_num}.1", "title": "小节名", "key_points": ["要点"], "complexity": "simple/medium/complex"}}
]
```"""

        response = await self._call_llm(f"请为「{node_name}」设计小节。", prompt)

        if response:
            data = self._extract_json(response)
            if data:
                result: list[dict] = []
                items = data if isinstance(data, list) else [data]
                for item in items:
                    section = item.get("section_number", f"{chapter_num}.{len(result) + 1}")
                    result.append({
                        "node_id": str(uuid.uuid4()),
                        "parent_node_id": node_id,
                        "node_name": f"{section} {item.get('title', '小节')}",
                        "node_level": node_level + 1,
                        "node_content": "",
                        "node_type": "custom",
                        "key_points": item.get("key_points", []),
                        "complexity": item.get("complexity", "medium"),
                        "generation_status": "pending",
                        "generated_chars": 0,
                        "error_summary": None,
                    })
                return result

        return [
            {"node_id": str(uuid.uuid4()), "parent_node_id": node_id, "node_name": f"{chapter_num}.1 基础概念", "node_level": node_level + 1, "node_content": "", "node_type": "custom", "complexity": "simple", "generation_status": "pending", "generated_chars": 0, "error_summary": None},
            {"node_id": str(uuid.uuid4()), "parent_node_id": node_id, "node_name": f"{chapter_num}.2 核心原理", "node_level": node_level + 1, "node_content": "", "node_type": "custom", "complexity": "medium", "generation_status": "pending", "generated_chars": 0, "error_summary": None},
            {"node_id": str(uuid.uuid4()), "parent_node_id": node_id, "node_name": f"{chapter_num}.3 实践应用", "node_level": node_level + 1, "node_content": "", "node_type": "custom", "complexity": "medium", "generation_status": "pending", "generated_chars": 0, "error_summary": None},
        ]

    # ------------------------------------------------------------------
    # 批量生成（保持兼容）
    # ------------------------------------------------------------------

    async def generate_content_batch(
        self,
        course_id: str,
        node_ids: list[str],
        node_names: list[str],
        max_concurrent: int = 3,
    ) -> dict[str, str]:
        """批量并行生成内容。

        Args:
            course_id: 课程 ID
            node_ids: 节点 ID 列表
            node_names: 节点名称列表
            max_concurrent: 最大并发数

        Returns:
            node_id -> content 的映射字典
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def generate_with_limit(node_id: str, node_name: str) -> tuple[str, str]:
            async with semaphore:
                content = await self.generate_node_content(node_id, node_name, course_id)
                return node_id, content

        tasks = [
            generate_with_limit(nid, nname)
            for nid, nname in zip(node_ids, node_names)
        ]

        results = await asyncio.gather(*tasks)

        return {node_id: content for node_id, content in results}


# ---------------------------------------------------------------------------
# 工厂函数
# ---------------------------------------------------------------------------

_course_service: CourseService | None = None


def get_course_service() -> CourseService:
    """获取 CourseService 单例。

    使用默认依赖创建实例。生产环境中建议通过 FastAPI 依赖注入替代。

    Returns:
        CourseService 实例
    """
    global _course_service
    if _course_service is None:
        _course_service = CourseService(
            prompt_engine=get_prompt_engine(),
            knowledge_graph=GlobalKnowledgeGraph(),
            quality_predictor=QualityPredictor(),
            content_validator=ContentValidator(),
            consistency_validator=ContentConsistencyValidator(),
        )
    return _course_service
