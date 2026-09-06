"""
课程上下文管理器
解决两阶段生成流程中的信息丢失问题
- 追踪已生成内容的摘要
- 维护节点间的关联关系
- 提供上下文感知的内容生成支持
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import json
from course_pedagogy import PedagogyMode, parse_mode


@dataclass
class NodeSummary:
    """节点摘要信息"""
    node_id: str
    title: str
    level: int
    content_summary: str
    key_concepts: List[str]
    learning_objective: str = ""
    prerequisites: List[str] = field(default_factory=list)
    misconceptions: List[str] = field(default_factory=list)
    assessment: List[str] = field(default_factory=list)
    scope_boundary: str = ""
    generated_at: datetime = field(default_factory=datetime.now)


@dataclass
class CourseContext:
    """课程上下文"""
    course_id: str
    topic: str
    pedagogy_mode: PedagogyMode
    target_audience: str
    depth: str
    node_summaries: Dict[str, NodeSummary] = field(default_factory=dict)
    concept_index: Dict[str, List[str]] = field(default_factory=dict)
    generation_history: List[Dict[str, Any]] = field(default_factory=list)
    learning_objectives: List[str] = field(default_factory=list)
    prerequisites: List[str] = field(default_factory=list)
    
    def add_node_summary(self, summary: NodeSummary):
        """添加节点摘要"""
        self.node_summaries[summary.node_id] = summary
        
        for concept in summary.key_concepts:
            if concept not in self.concept_index:
                self.concept_index[concept] = []
            if summary.node_id not in self.concept_index[concept]:
                self.concept_index[concept].append(summary.node_id)
    
    def get_sibling_context(self, node_id: str) -> str:
        """获取同级节点上下文"""
        parts = node_id.split("-")
        if len(parts) < 2:
            return ""
        
        prefix = "-".join(parts[:-1])
        siblings = []
        
        for nid, summary in self.node_summaries.items():
            if nid.startswith(prefix) and nid != node_id:
                siblings.append(f"- {summary.title}: {summary.content_summary[:100]}...")
        
        return chr(10).join(siblings[:3])
    
    def get_parent_context(self, node_id: str) -> str:
        """获取父节点上下文"""
        parts = node_id.split("-")
        if len(parts) < 3:
            return ""
        
        parent_id = "-".join(parts[:-1])
        if parent_id in self.node_summaries:
            parent = self.node_summaries[parent_id]
            return f"{parent.title}: {parent.content_summary[:200]}..."
        return ""
    
    def get_previous_content(self, node_id: str) -> str:
        """获取前一节点内容"""
        sorted_ids = sorted(self.node_summaries.keys())
        
        try:
            current_idx = sorted_ids.index(node_id)
            if current_idx > 0:
                prev_id = sorted_ids[current_idx - 1]
                return self.node_summaries[prev_id].content_summary
        except ValueError:
            pass
        
        return ""
    
    def check_concept_coverage(self, concept: str) -> List[str]:
        """检查概念覆盖情况"""
        return self.concept_index.get(concept, [])

    def get_ledger_context(self, node_id: str, max_items: int = 6) -> str:
        """获取用于生成的课程上下文账本片段"""
        parts = [
            "## 课程上下文账本",
            f"- 课程主题：{self.topic}",
            f"- 教学结构模式：{self.pedagogy_mode.value}",
            f"- 目标受众：{self.target_audience}",
            f"- 难度：{self.depth}",
        ]
        if self.learning_objectives:
            parts.append("- 课程目标：" + "；".join(self.learning_objectives[:4]))
        if self.prerequisites:
            parts.append("- 课程前置知识：" + "；".join(self.prerequisites[:4]))

        current = self.node_summaries.get(node_id)
        if current:
            parts.extend([
                "",
                "## 本节生成契约",
                f"- 学习目标：{current.learning_objective or '按本节标题和关键点确定'}",
                f"- 范围边界：{current.scope_boundary or '只讲本节必要内容'}",
            ])
            if current.prerequisites:
                parts.append("- 前置依赖节点：" + "、".join(current.prerequisites))
            if current.misconceptions:
                parts.append("- 需要澄清的误区：" + "；".join(current.misconceptions[:3]))
            if current.assessment:
                parts.append("- 验收标准：" + "；".join(current.assessment[:3]))

        prerequisite_summaries = []
        for prereq_id in (current.prerequisites if current else []):
            summary = self.node_summaries.get(prereq_id)
            if summary and summary.content_summary:
                prerequisite_summaries.append(f"- {summary.title}: {summary.content_summary[:220]}")
        if prerequisite_summaries:
            parts.extend(["", "## 已完成前置内容（可引用，勿重复展开）", *prerequisite_summaries[:max_items]])

        previous = self.get_previous_content(node_id)
        if previous:
            parts.extend(["", "## 前一节摘要", previous[:260]])

        known_concepts = list(self.concept_index)[:max_items]
        if known_concepts:
            parts.extend(["", "## 已出现概念（首次定义后只引用）", "- " + "、".join(known_concepts)])

        return "\n".join(parts)
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "course_id": self.course_id,
            "topic": self.topic,
            "pedagogy_mode": self.pedagogy_mode.value,
            "target_audience": self.target_audience,
            "depth": self.depth,
            "node_summaries": {
                k: {
                    "node_id": v.node_id,
                    "title": v.title,
                    "level": v.level,
                    "content_summary": v.content_summary,
                    "key_concepts": v.key_concepts,
                    "learning_objective": v.learning_objective,
                    "prerequisites": v.prerequisites,
                    "misconceptions": v.misconceptions,
                    "assessment": v.assessment,
                    "scope_boundary": v.scope_boundary,
                    "generated_at": v.generated_at.isoformat()
                }
                for k, v in self.node_summaries.items()
            },
            "concept_index": self.concept_index,
            "generation_history": self.generation_history,
            "learning_objectives": self.learning_objectives,
            "prerequisites": self.prerequisites,
        }


class CourseContextManager:
    """课程上下文管理器"""
    
    def __init__(self):
        self._contexts: Dict[str, CourseContext] = {}
    
    def create_context(
        self,
        course_id: str,
        topic: str,
        pedagogy_mode: PedagogyMode | str,
        target_audience: str = "大学生",
        depth: str = "中级"
    ) -> CourseContext:
        """创建新的课程上下文"""
        context = CourseContext(
            course_id=course_id,
            topic=topic,
            pedagogy_mode=parse_mode(pedagogy_mode) or PedagogyMode.GENERAL,
            target_audience=target_audience,
            depth=depth
        )
        self._contexts[course_id] = context
        return context

    def create_from_plan(
        self,
        course_id: str,
        plan: Dict[str, Any],
        pedagogy_mode: PedagogyMode | str,
        target_audience: str = "大学生",
        depth: str = "中级"
    ) -> CourseContext:
        """从课程蓝图创建上下文账本"""
        context = self.create_context(
            course_id=course_id,
            topic=plan.get("course_title", ""),
            pedagogy_mode=pedagogy_mode,
            target_audience=target_audience,
            depth=depth,
        )
        context.learning_objectives = plan.get("learning_objectives", []) or []
        context.prerequisites = plan.get("prerequisites", []) or []

        for chapter in plan.get("chapters", []):
            chapter_num = chapter.get("chapter_number", 1)
            chapter_id = f"L1-{chapter_num}"
            context.add_node_summary(NodeSummary(
                node_id=chapter_id,
                title=f"第{chapter_num}章 {chapter.get('title', '')}",
                level=1,
                content_summary=chapter.get("learning_focus", ""),
                key_concepts=[],
                learning_objective=chapter.get("learning_focus", ""),
            ))
            for section in chapter.get("sections", []):
                section_num = section.get("section_number", f"{chapter_num}.1")
                node_id = f"L2-{section_num.replace('.', '-')}"
                context.add_node_summary(NodeSummary(
                    node_id=node_id,
                    title=f"{section_num} {section.get('title', '')}",
                    level=2,
                    content_summary="",
                    key_concepts=section.get("key_points", []) or [],
                    learning_objective=section.get("learning_objective", ""),
                    prerequisites=section.get("prerequisite_node_ids", []) or [],
                    misconceptions=section.get("misconceptions", []) or [],
                    assessment=section.get("assessment", []) or [],
                    scope_boundary=section.get("scope_boundary", ""),
                ))

        return context
    
    def get_context(self, course_id: str) -> Optional[CourseContext]:
        """获取课程上下文"""
        return self._contexts.get(course_id)

    def ensure_context_from_nodes(
        self,
        course_id: str,
        course_name: str,
        nodes: List[Dict[str, Any]],
        pedagogy_mode: PedagogyMode | str,
        target_audience: str = "大学生",
        depth: str = "中级"
    ) -> CourseContext:
        """从已有课程节点兜底创建账本"""
        context = self.get_context(course_id)
        if context:
            return context

        context = self.create_context(course_id, course_name, pedagogy_mode, target_audience, depth)
        for node in nodes:
            context.add_node_summary(NodeSummary(
                node_id=node.get("node_id", ""),
                title=node.get("node_name", ""),
                level=node.get("node_level", 1),
                content_summary=self._extract_summary(node.get("node_content", "")),
                key_concepts=node.get("key_points", []) or self._extract_concepts(node.get("node_content", "")),
                learning_objective=node.get("learning_objective", ""),
                prerequisites=node.get("prerequisite_node_ids", []) or [],
                misconceptions=node.get("misconceptions", []) or [],
                assessment=node.get("assessment", []) or [],
                scope_boundary=node.get("scope_boundary", ""),
            ))
        return context
    
    def update_node(
        self,
        course_id: str,
        node_id: str,
        title: str,
        level: int,
        content: str,
        key_concepts: Optional[List[str]] = None
    ) -> bool:
        """更新节点信息"""
        context = self.get_context(course_id)
        if not context:
            return False
        
        existing = context.node_summaries.get(node_id)
        summary = NodeSummary(
            node_id=node_id,
            title=title,
            level=level,
            content_summary=self._extract_summary(content),
            key_concepts=key_concepts or self._extract_concepts(content),
            learning_objective=existing.learning_objective if existing else "",
            prerequisites=existing.prerequisites if existing else [],
            misconceptions=existing.misconceptions if existing else [],
            assessment=existing.assessment if existing else [],
            scope_boundary=existing.scope_boundary if existing else "",
        )
        
        context.add_node_summary(summary)
        context.generation_history.append({
            "node_id": node_id,
            "action": "content_generated",
            "timestamp": datetime.now().isoformat()
        })
        
        return True
    
    def get_generation_context(
        self,
        course_id: str,
        node_id: str
    ) -> Dict[str, str]:
        """获取生成上下文"""
        context = self.get_context(course_id)
        if not context:
            return {}
        
        return {
            "sibling_context": context.get_sibling_context(node_id),
            "parent_context": context.get_parent_context(node_id),
            "previous_content": context.get_previous_content(node_id),
            "ledger_context": context.get_ledger_context(node_id),
            "course_topic": context.topic,
            "pedagogy_mode": context.pedagogy_mode.value
        }
    
    def _extract_summary(self, content: str, max_length: int = 300) -> str:
        """提取内容摘要"""
        if not content:
            return ""
        
        lines = content.split("\n")
        text_lines = [l.strip() for l in lines if l.strip() and not l.startswith("#")]
        
        summary = " ".join(text_lines[:5])
        if len(summary) > max_length:
            summary = summary[:max_length] + "..."
        
        return summary
    
    def _extract_concepts(self, content: str) -> List[str]:
        """提取关键概念"""
        concepts = []
        
        import re
        
        bold_pattern = r'\*\*([^*]+)\*\*'
        bold_matches = re.findall(bold_pattern, content)
        concepts.extend(bold_matches[:5])
        
        header_pattern = r'^#{2,3}\s+(.+)$'
        header_matches = re.findall(header_pattern, content, re.MULTILINE)
        concepts.extend(header_matches[:3])
        
        return list(set(concepts))[:8]
    
    def save_context(self, course_id: str, file_path: str) -> bool:
        """保存上下文到文件"""
        context = self.get_context(course_id)
        if not context:
            return False
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(context.to_dict(), f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False
    
    def load_context(self, file_path: str) -> Optional[CourseContext]:
        """从文件加载上下文"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            context = CourseContext(
                course_id=data["course_id"],
                topic=data["topic"],
                pedagogy_mode=parse_mode(
                    data.get("pedagogy_mode") or data.get("discipline")
                ) or PedagogyMode.GENERAL,
                target_audience=data["target_audience"],
                depth=data["depth"],
                learning_objectives=data.get("learning_objectives", []),
                prerequisites=data.get("prerequisites", []),
            )
            
            for nid, ns in data["node_summaries"].items():
                summary = NodeSummary(
                    node_id=ns["node_id"],
                    title=ns["title"],
                    level=ns["level"],
                    content_summary=ns["content_summary"],
                    key_concepts=ns["key_concepts"],
                    learning_objective=ns.get("learning_objective", ""),
                    prerequisites=ns.get("prerequisites", []),
                    misconceptions=ns.get("misconceptions", []),
                    assessment=ns.get("assessment", []),
                    scope_boundary=ns.get("scope_boundary", ""),
                    generated_at=datetime.fromisoformat(ns["generated_at"])
                )
                context.node_summaries[nid] = summary
            
            context.concept_index = data.get("concept_index", {})
            context.generation_history = data.get("generation_history", [])
            
            self._contexts[context.course_id] = context
            return context
            
        except Exception:
            return None
    
    def clear_context(self, course_id: str) -> bool:
        """清除课程上下文"""
        if course_id in self._contexts:
            del self._contexts[course_id]
            return True
        return False


_context_manager: Optional[CourseContextManager] = None


def get_context_manager() -> CourseContextManager:
    """获取全局上下文管理器"""
    global _context_manager
    if _context_manager is None:
        _context_manager = CourseContextManager()
    return _context_manager
