"""
课程生成服务 V5 - 智能混合架构

核心创新：
1. 智能模式选择：根据内容复杂度选择生成策略
2. 并行生成：独立章节并行处理
3. 缓存复用：相似内容结构复用
4. 增量修正：只修正问题部分，非全量重写
5. 全局一致性：课程级知识图谱
6. 质量预测：预测内容质量，跳过低质量审查
7. 专业提示词：难度适配、受众适配、智能篇幅
"""

import uuid
import json
import asyncio
import logging
import hashlib
import time
from typing import List, Dict, Optional, Set, Tuple, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

from ai_base import AIBase
from discipline_config import DisciplineType, get_discipline_config, detect_discipline_type
from prompt_engine_v5 import (
    PromptEngineV5, 
    DifficultyLevel, 
    TargetAudience, 
    ContentGuidelines,
    get_prompt_engine
)

logger = logging.getLogger(__name__)


from knowledge_graph import GlobalKnowledgeGraph  # noqa: E402
from quality_predictor import GenerationMode, QualityPredictor  # noqa: E402


@dataclass
class ContentCache:
    """内容缓存 - 复用相似结构"""
    structure_templates: Dict[str, Dict] = field(default_factory=dict)
    section_patterns: Dict[str, str] = field(default_factory=dict)
    
    def get_similar_template(self, section_title: str, discipline: DisciplineType) -> Optional[Dict]:
        """获取相似模板"""
        key = f"{discipline.value}:{section_title[:20]}"
        return self.structure_templates.get(key)
    
    def cache_template(self, section_title: str, discipline: DisciplineType, template: Dict):
        """缓存模板"""
        key = f"{discipline.value}:{section_title[:20]}"
        self.structure_templates[key] = template


class IncrementalEditor:
    """增量编辑器 - 只修正问题部分"""
    
    @staticmethod
    def apply_fixes(content: str, issues: List[Dict]) -> str:
        """应用增量修正"""
        if not issues:
            return content
        
        lines = content.split("\n")
        
        for issue in issues:
            location = issue.get("location", "")
            fix = issue.get("fix", "")
            
            if not fix:
                continue
            
            if "第" in location and "段" in location:
                try:
                    para_num = int("".join(filter(str.isdigit, location)))
                    para_count = 0
                    for i, line in enumerate(lines):
                        if line.strip() and (i == 0 or not lines[i-1].strip()):
                            para_count += 1
                            if para_count == para_num:
                                lines[i] = fix
                                break
                except:
                    pass
        
        return "\n".join(lines)


class AICourseServiceV5(AIBase):
    """课程生成服务 V5 - 智能混合架构"""

    def __init__(self):
        super().__init__()
        self._knowledge_graphs: Dict[str, GlobalKnowledgeGraph] = {}
        self._content_cache = ContentCache()
        self._quality_predictor = QualityPredictor()
        self._course_plans: Dict[str, Dict] = {}
        self._generation_stats: Dict[str, Dict] = {}
        self._prompt_engine = get_prompt_engine()
        self._course_settings: Dict[str, Dict] = {}

    def _parse_difficulty(self, depth: str) -> DifficultyLevel:
        """解析难度级别"""
        mapping = {
            "入门": DifficultyLevel.BEGINNER,
            "初级": DifficultyLevel.BEGINNER,
            "beginner": DifficultyLevel.BEGINNER,
            "中级": DifficultyLevel.INTERMEDIATE,
            "intermediate": DifficultyLevel.INTERMEDIATE,
            "高级": DifficultyLevel.ADVANCED,
            "advanced": DifficultyLevel.ADVANCED
        }
        return mapping.get(depth.lower(), DifficultyLevel.INTERMEDIATE)
    
    def _parse_audience(self, audience: str) -> TargetAudience:
        """解析目标受众"""
        mapping = {
            "高中生": TargetAudience.HIGH_SCHOOL,
            "大学生": TargetAudience.UNDERGRADUATE,
            "研究生": TargetAudience.GRADUATE,
            "从业者": TargetAudience.PROFESSIONAL,
            "专业人员": TargetAudience.PROFESSIONAL
        }
        return mapping.get(audience, TargetAudience.UNDERGRADUATE)

    async def generate_course(
        self,
        topic: str,
        discipline: Optional[DisciplineType] = None,
        target_audience: str = "大学生",
        depth: str = "中级",
        mode: GenerationMode = GenerationMode.BALANCED,
        **kwargs
    ) -> Dict:
        """生成课程大纲"""
        if discipline is None:
            discipline = detect_discipline_type(topic)
        
        course_id = str(uuid.uuid4())
        
        difficulty = self._parse_difficulty(depth)
        audience = self._parse_audience(target_audience)
        
        self._course_settings[course_id] = {
            "difficulty": difficulty,
            "audience": audience,
            "discipline": discipline
        }
        
        self._knowledge_graphs[course_id] = GlobalKnowledgeGraph()
        self._generation_stats[course_id] = {
            "api_calls": 0,
            "cache_hits": 0,
            "mode_usage": defaultdict(int),
            "start_time": time.time()
        }
        
        plan = await self._generate_course_plan(topic, discipline, difficulty, audience)
        self._course_plans[course_id] = plan
        
        nodes = self._convert_plan_to_nodes(plan, course_id)
        
        return {
            "course_id": course_id,
            "course_name": plan.get("course_title", topic),
            "discipline": discipline.value,
            "nodes": nodes,
            "learning_objectives": plan.get("learning_objectives", []),
            "prerequisites": plan.get("prerequisites", []),
            "target_audience": target_audience,
            "depth": depth,
            "generation_mode": mode.value
        }

    async def _generate_course_plan(
        self,
        topic: str,
        discipline: DisciplineType,
        difficulty: DifficultyLevel,
        audience: TargetAudience
    ) -> Dict:
        """生成课程规划（使用专业提示词引擎）"""
        config = get_discipline_config(discipline)
        
        prompt = self._prompt_engine.build_outline_prompt(
            topic=topic,
            discipline=discipline,
            difficulty=difficulty,
            audience=audience,
            config=config
        )
        
        response = await self._call_llm(
            f"请为「{topic}」设计课程大纲。",
            prompt
        )
        
        if response:
            data = self._extract_json(response)
            if data:
                return data
        
        return self._create_fallback_plan(topic)

    def _create_fallback_plan(self, topic: str) -> Dict:
        """创建兜底计划"""
        return {
            "course_title": topic,
            "learning_objectives": [f"掌握{topic}基本概念", f"理解{topic}核心原理"],
            "chapters": [
                {"chapter_number": 1, "title": "概述", "learning_focus": "基本概念", "sections": [
                    {"section_number": "1.1", "title": "基本概念", "key_points": ["定义", "特点"], "complexity": "simple"},
                    {"section_number": "1.2", "title": "发展历程", "key_points": ["起源", "发展"], "complexity": "simple"}
                ]},
                {"chapter_number": 2, "title": "核心内容", "learning_focus": "核心原理", "sections": [
                    {"section_number": "2.1", "title": "核心原理", "key_points": ["原理", "机制"], "complexity": "medium"},
                    {"section_number": "2.2", "title": "基本方法", "key_points": ["方法", "步骤"], "complexity": "medium"}
                ]}
            ]
        }

    def _convert_plan_to_nodes(self, plan: Dict, course_id: str) -> List[Dict]:
        """转换规划为节点"""
        nodes = []
        
        for chapter in plan.get("chapters", []):
            chapter_num = chapter.get("chapter_number", len(nodes) + 1)
            
            nodes.append({
                "node_id": f"L1-{chapter_num}",
                "node_name": f"第{chapter_num}章 {chapter.get('title', '')}",
                "node_level": 1,
                "node_content": "",
                "node_type": "original",
                "learning_focus": chapter.get("learning_focus", "")
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
                    "complexity": section.get("complexity", "medium")
                })
        
        return nodes

    async def generate_node_content(
        self,
        node_id: str,
        node_name: str,
        course_id: str,
        discipline: Optional[DisciplineType] = None,
        mode: Optional[GenerationMode] = None,
        **kwargs
    ) -> str:
        """生成节点内容（智能模式选择）"""
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
            course_id=course_id
        )
        
        self._update_knowledge_graph(knowledge_graph, content, node_id)
        
        consistency_issues = knowledge_graph.check_consistency(node_id, content)
        if consistency_issues:
            content = await self._fix_consistency_issues(content, consistency_issues, discipline)
        
        return content

    async def _generate_with_mode(
        self,
        mode: GenerationMode,
        section_info: Dict,
        context: str,
        discipline: DisciplineType,
        course_topic: str,
        knowledge_graph: GlobalKnowledgeGraph,
        course_id: str = ""
    ) -> str:
        """根据模式生成内容（使用专业提示词引擎）"""
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
            section_complexity=complexity
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
            config=config
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

    def _quick_quality_check(self, content: str, guidelines: ContentGuidelines = None) -> float:
        """快速质量检查"""
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
        audience: TargetAudience = TargetAudience.UNDERGRADUATE
    ) -> str:
        """快速修复（使用专业提示词）"""
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
        guidelines: ContentGuidelines = None
    ) -> List[Dict]:
        """审查内容（使用专业提示词引擎）"""
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
            guidelines=guidelines
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
        issues: List[Dict], 
        title: str, 
        discipline: DisciplineType,
        difficulty: DifficultyLevel = DifficultyLevel.INTERMEDIATE,
        audience: TargetAudience = TargetAudience.UNDERGRADUATE
    ) -> str:
        """修复内容（使用专业提示词引擎）"""
        if not issues:
            return content
        
        prompt = self._prompt_engine.build_fix_prompt(
            content=content,
            issues=issues,
            section_title=title,
            discipline=discipline,
            difficulty=difficulty,
            audience=audience
        )
        
        response = await self._call_llm("请修正内容。", prompt)
        return response if response else content

    async def _fix_consistency_issues(self, content: str, issues: List[Dict], discipline: DisciplineType) -> str:
        """修复一致性问题"""
        if not issues:
            return content
        
        for issue in issues[:2]:
            concept = issue.get("concept", "")
            existing = issue.get("existing", "")
            
            import re
            pattern = rf'\*\*{re.escape(concept)}\*\*[：:]\s*([^。\n]+)'
            content = re.sub(pattern, f'**{concept}**：{existing}', content)
        
        return content

    def _update_knowledge_graph(self, graph: GlobalKnowledgeGraph, content: str, node_id: str):
        """更新知识图谱"""
        import re
        
        bold_matches = re.findall(r'\*\*([^*]{2,20})\*\*[：:]\s*([^。\n]{10,100})', content)
        for name, definition in bold_matches:
            graph.register_concept(name, definition.strip(), node_id, "")
        
        example_patterns = [r'例如[：:，]?\s*([^。\n]{10,80})', r'案例[：:]\s*([^。\n]{10,80})']
        for pattern in example_patterns:
            matches = re.findall(pattern, content)
            for ex in matches:
                graph.register_example(title=ex.strip(), summary=ex.strip(), node_id=node_id)
        
        formula_matches = re.findall(r'\$([^$]{5,100})\$', content)
        for f in formula_matches:
            graph.register_formula(f.strip(), "", node_id)

    def _find_section_info(self, plan: Dict, node_id: str, node_name: str) -> Dict:
        """查找小节信息"""
        for chapter in plan.get("chapters", []):
            for section in chapter.get("sections", []):
                section_num = section.get("section_number", "")
                if section_num in node_id or section_num in node_name:
                    return section
        return {"title": node_name, "section_number": "", "key_points": [], "complexity": "medium"}

    async def generate_sub_nodes(
        self,
        node_name: str,
        node_level: int,
        node_id: str,
        course_name: str = "",
        **kwargs
    ) -> List[Dict]:
        """生成子节点"""
        discipline = detect_discipline_type(course_name)
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
                result = []
                items = data if isinstance(data, list) else [data]
                for item in items:
                    section = item.get("section_number", f"{chapter_num}.{len(result)+1}")
                    result.append({
                        "node_id": str(uuid.uuid4()),
                        "parent_node_id": node_id,
                        "node_name": f"{section} {item.get('title', '小节')}",
                        "node_level": node_level + 1,
                        "node_content": "",
                        "node_type": "custom",
                        "key_points": item.get("key_points", []),
                        "complexity": item.get("complexity", "medium")
                    })
                return result
        
        return [
            {"node_id": str(uuid.uuid4()), "parent_node_id": node_id, "node_name": f"{chapter_num}.1 基础概念", "node_level": node_level + 1, "node_content": "", "node_type": "custom", "complexity": "simple"},
            {"node_id": str(uuid.uuid4()), "parent_node_id": node_id, "node_name": f"{chapter_num}.2 核心原理", "node_level": node_level + 1, "node_content": "", "node_type": "custom", "complexity": "medium"},
            {"node_id": str(uuid.uuid4()), "parent_node_id": node_id, "node_name": f"{chapter_num}.3 实践应用", "node_level": node_level + 1, "node_content": "", "node_type": "custom", "complexity": "medium"}
        ]

    async def generate_content_batch(
        self,
        course_id: str,
        node_ids: List[str],
        node_names: List[str],
        max_concurrent: int = 3
    ) -> Dict[str, str]:
        """批量并行生成内容"""
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def generate_with_limit(node_id: str, node_name: str) -> Tuple[str, str]:
            async with semaphore:
                content = await self.generate_node_content(node_id, node_name, course_id)
                return node_id, content
        
        tasks = [
            generate_with_limit(node_id, node_name)
            for node_id, node_name in zip(node_ids, node_names)
        ]
        
        results = await asyncio.gather(*tasks)
        
        return {node_id: content for node_id, content in results}


_course_service_v5: Optional[AICourseServiceV5] = None


def get_course_service_v5() -> AICourseServiceV5:
    """获取课程服务V5实例"""
    global _course_service_v5
    if _course_service_v5 is None:
        _course_service_v5 = AICourseServiceV5()
    return _course_service_v5
