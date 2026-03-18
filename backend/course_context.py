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
from discipline_config import DisciplineType, get_discipline_config


@dataclass
class NodeSummary:
    """节点摘要信息"""
    node_id: str
    title: str
    level: int
    content_summary: str
    key_concepts: List[str]
    generated_at: datetime = field(default_factory=datetime.now)


@dataclass
class CourseContext:
    """课程上下文"""
    course_id: str
    topic: str
    discipline: DisciplineType
    target_audience: str
    depth: str
    node_summaries: Dict[str, NodeSummary] = field(default_factory=dict)
    concept_index: Dict[str, List[str]] = field(default_factory=dict)
    generation_history: List[Dict[str, Any]] = field(default_factory=list)
    
    def add_node_summary(self, summary: NodeSummary):
        """添加节点摘要"""
        self.node_summaries[summary.node_id] = summary
        
        for concept in summary.key_concepts:
            if concept not in self.concept_index:
                self.concept_index[concept] = []
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
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "course_id": self.course_id,
            "topic": self.topic,
            "discipline": self.discipline.value,
            "target_audience": self.target_audience,
            "depth": self.depth,
            "node_summaries": {
                k: {
                    "node_id": v.node_id,
                    "title": v.title,
                    "level": v.level,
                    "content_summary": v.content_summary,
                    "key_concepts": v.key_concepts,
                    "generated_at": v.generated_at.isoformat()
                }
                for k, v in self.node_summaries.items()
            },
            "concept_index": self.concept_index,
            "generation_history": self.generation_history
        }


class CourseContextManager:
    """课程上下文管理器"""
    
    def __init__(self):
        self._contexts: Dict[str, CourseContext] = {}
    
    def create_context(
        self,
        course_id: str,
        topic: str,
        discipline: DisciplineType,
        target_audience: str = "大学生",
        depth: str = "中级"
    ) -> CourseContext:
        """创建新的课程上下文"""
        context = CourseContext(
            course_id=course_id,
            topic=topic,
            discipline=discipline,
            target_audience=target_audience,
            depth=depth
        )
        self._contexts[course_id] = context
        return context
    
    def get_context(self, course_id: str) -> Optional[CourseContext]:
        """获取课程上下文"""
        return self._contexts.get(course_id)
    
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
        
        summary = NodeSummary(
            node_id=node_id,
            title=title,
            level=level,
            content_summary=self._extract_summary(content),
            key_concepts=key_concepts or self._extract_concepts(content)
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
            "course_topic": context.topic,
            "discipline": context.discipline.value
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
                discipline=DisciplineType(data["discipline"]),
                target_audience=data["target_audience"],
                depth=data["depth"]
            )
            
            for nid, ns in data["node_summaries"].items():
                summary = NodeSummary(
                    node_id=ns["node_id"],
                    title=ns["title"],
                    level=ns["level"],
                    content_summary=ns["content_summary"],
                    key_concepts=ns["key_concepts"],
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
