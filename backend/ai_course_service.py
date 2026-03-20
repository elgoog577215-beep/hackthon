"""
AI 课程生成服务模块

负责课程大纲生成、子节点生成、节点内容生成、
内容重定义（流式/非流式）、内容拓展和内容总结。
"""

import uuid
import json
import asyncio
import logging
from typing import List, Dict

from ai_base import AIBase
from shared.prompt_config import DIFFICULTY_LEVELS, TEACHING_STYLES, DifficultyLevel, TeachingStyle
from prompts import (
    get_prompt, 
    get_difficulty_config, 
    get_style_config, 
    get_discipline_structure, 
    get_subnode_discipline_hints,
)

logger = logging.getLogger(__name__)


class AICourseService(AIBase):
    """课程生成相关的 AI 服务"""

    async def generate_course(
        self, 
        keyword: str, 
        difficulty: DifficultyLevel = DIFFICULTY_LEVELS["INTERMEDIATE"], 
        style: TeachingStyle = TEACHING_STYLES["ACADEMIC"], 
        requirements: str = ""
    ) -> Dict:
        discipline_type = self._detect_discipline_type(keyword)
        
        system_prompt = get_prompt("generate_course").format(
            keyword=keyword,
            difficulty=difficulty,
            style=style,
            requirements=requirements if requirements else "无",
            discipline_type=discipline_type
        )
        prompt = f"用户想要学习\"{keyword}\"，请生成一份专业且系统的课程大纲。学科类型已识别为：{discipline_type}。"
        response = await self._call_llm(prompt, system_prompt)
        if response:
            data = self._extract_json(response)
            if data and "nodes" in data:
                # Ensure unique UUIDs and process nested structure
                processed_nodes = []
                missing_sub_nodes_tasks = []
                
                # Create a simple outline for context if needed
                course_outline = json.dumps(data.get("nodes", []), ensure_ascii=False)

                for node in data["nodes"]:
                    # L1 Node
                    node_id = str(uuid.uuid4())
                    node["node_id"] = node_id
                    node["node_level"] = 1
                    
                    sub_nodes = node.pop("sub_nodes", [])
                    processed_nodes.append(node)
                    
                    if not sub_nodes:
                        # Schedule task to generate sub-nodes if missing
                        task = self.generate_sub_nodes(
                            node_name=node.get("node_name", "Unknown Chapter"),
                            node_level=1,
                            node_id=node_id,
                            course_name=keyword,
                            course_outline=course_outline,
                            difficulty=difficulty,
                            style=style
                        )
                        missing_sub_nodes_tasks.append(task)
                    else:
                        # L2 Nodes
                        for sub in sub_nodes:
                            sub["node_id"] = str(uuid.uuid4())
                            sub["parent_node_id"] = node_id
                            sub["node_level"] = 2
                            sub["node_type"] = "original"
                            if "node_content" not in sub:
                                sub["node_content"] = ""
                            processed_nodes.append(sub)
                
                # Execute fallback tasks in parallel
                if missing_sub_nodes_tasks:
                    logger.info(f"Generating missing sub-nodes for {len(missing_sub_nodes_tasks)} chapters...")
                    results = await asyncio.gather(*missing_sub_nodes_tasks)
                    for sub_node_list in results:
                        processed_nodes.extend(sub_node_list)
                
                # Sort nodes: L1 then its L2 children
                final_nodes = []
                l1_nodes = [n for n in processed_nodes if n.get("node_level") == 1]
                l2_nodes = [n for n in processed_nodes if n.get("node_level") == 2]
                
                # Create map of parent -> children
                l2_map = {}
                for n in l2_nodes:
                    pid = n.get("parent_node_id")
                    if pid not in l2_map:
                        l2_map[pid] = []
                    l2_map[pid].append(n)
                
                for l1 in l1_nodes:
                    final_nodes.append(l1)
                    if l1["node_id"] in l2_map:
                        final_nodes.extend(l2_map[l1["node_id"]])
                
                # Add any orphaned L2 nodes (just in case)
                orphaned = [n for n in l2_nodes if n.get("parent_node_id") not in [l1["node_id"] for l1 in l1_nodes]]
                final_nodes.extend(orphaned)
                
                data["nodes"] = final_nodes
            return data
        return {"course_name": keyword, "nodes": []}

    async def generate_sub_nodes(
        self,
        node_name: str,
        node_level: int,
        node_id: str,
        course_name: str = "",
        parent_context: str = "",
        course_outline: str = "",
        difficulty: DifficultyLevel = DIFFICULTY_LEVELS["INTERMEDIATE"],
        style: TeachingStyle = TEACHING_STYLES["ACADEMIC"],
        discipline_type: str = None,
        existing_nodes: List[Dict] = None
    ) -> List[Dict]:
        """
        生成子节点内容

        根据父节点信息生成下一层级的子节点列表，
        包含子节点名称和内容大纲。
        """
        chapter_number = self._extract_chapter_number(node_name)
        
        if discipline_type is None:
            discipline_type = self._detect_discipline_type(course_name, node_name)
        
        system_prompt = get_prompt("generate_sub_nodes").format(
            course_name=course_name if course_name else "未知课程",
            parent_context=parent_context if parent_context else f"当前章节：{node_name}",
            course_outline=course_outline if course_outline else "无",
            difficulty=difficulty,
            style=style,
            chapter_number=chapter_number,
            discipline_type=discipline_type,
            difficulty_config_text=get_difficulty_config(difficulty),
            style_config_text=get_style_config(style),
            subnode_hints=get_subnode_discipline_hints(discipline_type)
        )
        prompt = f"当前节点信息：名称={node_name}，层级={node_level}，章节编号={chapter_number}。请列出该章节下的所有子小节，确保编号以{chapter_number}.开头（如{chapter_number}.1、{chapter_number}.2...），结构完整且具备专业性。"
        
        response = await self._call_llm(prompt, system_prompt)
        new_level = node_level + 1
        
        if response:
            data = self._extract_json(response)
            if data:
                result = []
                for item in data.get("sub_nodes", []):
                    result.append({
                        "node_id": str(uuid.uuid4()),
                        "parent_node_id": node_id,
                        "node_name": item.get("node_name", "新节点"),
                        "node_level": new_level,
                        "node_content": item.get("node_content", ""),
                        "node_type": "custom"
                    })
                return result

        fallback_chapter = chapter_number if chapter_number else "1"
        return [
            {"node_id": str(uuid.uuid4()), "parent_node_id": node_id, "node_name": f"{fallback_chapter}.1 基础概念", "node_level": new_level, "node_content": "", "node_type": "custom"},
            {"node_id": str(uuid.uuid4()), "parent_node_id": node_id, "node_name": f"{fallback_chapter}.2 核心原理", "node_level": new_level, "node_content": "", "node_type": "custom"},
            {"node_id": str(uuid.uuid4()), "parent_node_id": node_id, "node_name": f"{fallback_chapter}.3 实践应用", "node_level": new_level, "node_content": "", "node_type": "custom"}
        ]

    async def generate_node_content(
        self,
        node_name: str,
        node_context: str = "",
        node_id: str = "",
        course_name: str = "",
        difficulty: DifficultyLevel = DIFFICULTY_LEVELS["ADVANCED"],
        style: TeachingStyle = TEACHING_STYLES["ACADEMIC"],
        discipline_type: str = None,
        previous_node_content: str = "",
        used_cases: List[str] = None,
        prerequisite_context: List[Dict] = None,  # P1 新增：前置知识上下文
        learner_weakness: List[str] = None  # P1 新增：学习者薄弱点
    ) -> str:
        """
        生成节点详细正文内容（P1 升级版：注入前置知识上下文和薄弱点）
        """
        if discipline_type is None:
            discipline_type = self._detect_discipline_type(course_name, node_name)
        
        if used_cases is None:
            used_cases = []
        if prerequisite_context is None:
            prerequisite_context = []
        if learner_weakness is None:
            learner_weakness = []
        
        used_cases_str = "、".join(used_cases) if used_cases else "暂无"
        
        # P1 新增：构建前置知识上下文字符串
        prerequisite_context_str = "无"
        if prerequisite_context:
            prerequisite_context_str = "\n".join([
                f"- {ctx['node_name']}: {ctx.get('key_concepts', '')[:200]}"
                for ctx in prerequisite_context
            ])
        
        # P1 新增：构建学习者薄弱点字符串
        learner_weakness_str = "无"
        if learner_weakness:
            learner_weakness_str = "、".join(learner_weakness)
        
        course_context = f"课程名称：{course_name}"
        if node_context:
            course_context += f"\n上下文线索：{node_context}"
        
        system_prompt = get_prompt("generate_content").format(
            node_name=node_name,
            node_level="2",
            course_context=course_context,
            difficulty=difficulty,
            style=style,
            discipline_type=discipline_type,
            previous_node_content=previous_node_content[:500] if previous_node_content else "无",
            used_cases=used_cases_str,
            difficulty_config_text=get_difficulty_config(difficulty),
            style_config_text=get_style_config(style),
            discipline_structure=get_discipline_structure(discipline_type),
            prerequisite_context=prerequisite_context_str,  # P1 新增：前置知识上下文
            learner_weakness=learner_weakness_str  # P1 新增：学习者薄弱点
        )
        
        prompt = f"""请为'{node_name}'生成完整的详细正文内容。

学科类型：{discipline_type}
已使用案例：{used_cases_str}
前置知识回顾：{prerequisite_context_str}
学习者薄弱点：{learner_weakness_str}

重要提醒：
1. **必须使用四拍认知节奏结构**（直观感知→抽象提炼→操作演练→迁移应用）
2. **必须包含决策口诀**（"看到 X 特征，就用 Y 方法"）
3. **必须包含反面案例**（常见错误及原因分析）
4. 可视化图解板块必须包含 Mermaid 图或表格，禁止留空
5. 案例必须使用新案例，禁止重复已使用的案例
6. 思考题只能涉及本节正文已介绍的概念
7. 如果存在前置知识或薄弱点，请在内容中重点讲解"""

        response = await self._call_llm(prompt, system_prompt)
        if response:
            return self.clean_response_text(response)

        return f"## {node_name}\n\n详细正文内容生成中...\n\n请稍后重试。"

    async def redefine_content(
        self,
        node_name: str,
        requirement: str,
        original_content: str = "",
        course_context: str = "",
        previous_context: str = "",
        difficulty: DifficultyLevel = DIFFICULTY_LEVELS["ADVANCED"],
        style: TeachingStyle = TEACHING_STYLES["ACADEMIC"]
    ) -> str:
        """
        重定义节点内容（非流式）
        """
        system_prompt = get_prompt("redefine_content").format(
            node_name=node_name,
            course_context=course_context if course_context else "无",
            previous_context=previous_context if previous_context else "无",
            original_content=original_content if original_content else "无",
            requirement=requirement if requirement else "无",
            difficulty=difficulty,
            style=style
        )

        prompt = "请开始撰写正文（请务必包含 <!-- BODY_START --> 分隔符）。"

        response = await self._call_llm(prompt, system_prompt)
        if response:
            return self.clean_response_text(response)

        return f"基于需求 '{requirement}' 重定义的 {node_name} 内容。\n\n1. 核心点一：...\n2. 核心点二：...\n(参考来源：权威资料)"

    async def redefine_node_content(
        self,
        node_name: str,
        original_content: str,
        requirement: str,
        course_context: str = "",
        previous_context: str = "",
        difficulty: DifficultyLevel = DIFFICULTY_LEVELS["ADVANCED"],
        style: TeachingStyle = TEACHING_STYLES["ACADEMIC"]
    ):
        """
        流式重定义节点内容 - 支持课程级上下文感知
        """
        system_prompt = get_prompt("redefine_content").format(
            node_name=node_name,
            course_context=course_context if course_context else "无",
            previous_context=previous_context if previous_context else "无",
            original_content=original_content if original_content else "无",
            requirement=requirement if requirement else "无",
            difficulty=difficulty,
            style=style
        )

        prompt = "请开始撰写正文（请务必包含 <!-- BODY_START --> 分隔符）。"
        async for chunk in self._stream_llm(prompt, system_prompt):
            yield chunk

    async def extend_content(self, node_name: str, requirement: str) -> str:
        """
        拓展节点内容
        """
        system_prompt = """
你是学术视野拓展专家，需为当前教科书章节补充具有深度的延伸阅读材料。
要求：
1. **受众定位**：面向大学生及专业人士，拒绝科普性质的浅层介绍。
2. **拓展方向**：重点补充学术界的前沿研究、工业界的工程陷阱、底层数学原理或跨学科的深度关联。
3. **内容风格**：专业、干练、逻辑严密。
4. **格式规范**：内容充实（300-500 字），可使用"延伸阅读"或"深度思考"作为标题。
5. **公式规范**：
   - 行内公式用 `$公式$`（**内部不要有空格**）。
   - 块级公式用 `$` 包裹。
   - 严禁裸写 LaTeX 命令。
6. **输出格式**：直接输出 **Markdown 格式的内容**，**不需要**包含在 JSON 对象中。
"""
        prompt = f"当前章节：{node_name}\n拓展方向：{requirement}"

        response = await self._call_llm(prompt, system_prompt)
        if response:
            return self.clean_response_text(response)

        return f"拓展知识点：\n关于 {node_name} 的延伸阅读... {requirement}"

    async def summarize_content(self, node_content: str, node_name: str = "", user_persona: str = None) -> str:
        """
        总结章节内容
        """
        persona_context = f"\n用户背景：{user_persona}" if user_persona else ""
        
        system_prompt = f"""你是知识总结专家，需要为学习材料生成清晰、结构化的总结。
要求：
1. **结构清晰**：使用标题、列表等Markdown格式组织内容
2. **重点突出**：提炼核心概念、关键公式、重要结论
3. **简洁明了**：避免冗余，每个要点控制在1-2句话
4. **实用导向**：强调学习要点和常见考点
5. **格式规范**：
   - 使用 `###` 作为主标题
   - 使用 `-` 或 `1.` 列表项
   - 公式用 `$公式$` 包裹{persona_context}

输出格式示例：
### 核心概念
- 概念1：简要说明
- 概念2：简要说明

### 关键公式
- 公式1：$公式$ - 含义说明

### 学习要点
- 要点1
- 要点2
"""
        
        content_preview = node_content[:3000] if len(node_content) > 3000 else node_content
        prompt = f"请总结以下章节内容：\n\n章节名称：{node_name}\n\n内容：\n{content_preview}"

        response = await self._call_llm(prompt, system_prompt)
        if response:
            return self.clean_response_text(response)

        return f"### {node_name} 总结\n\n核心内容已总结完成。"

    def locate_node(self, keyword: str, all_nodes: list) -> dict:
        """按关键词定位课程节点"""
        for node in all_nodes:
            if keyword in node.get('node_name', ''):
                return {
                    "match_node_id": node['node_id'],
                    "match_node_name": node['node_name'],
                }
        return {}

    def locate_node(self, keyword: str, all_nodes: list) -> dict:
        """按关键词定位课程节点"""
        for node in all_nodes:
            if keyword in node.get('node_name', ''):
                return {
                    "match_node_id": node['node_id'],
                    "match_node_name": node['node_name'],
                }
        return {}

