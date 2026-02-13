"""
AI服务模块 - 统一的大模型交互接口

架构说明:
- 提供与LLM(大语言模型)的抽象交互层
- 支持模型路由策略(智能模型vs快速模型)
- 统一的内容生成、测验生成、问答等接口
- 包含响应清理和JSON提取等工具方法

主要功能:
1. 课程生成 - 生成完整的课程大纲和结构
2. 内容生成 - 生成章节正文内容
3. 子节点生成 - 生成L2/L3子章节
4. 测验生成 - 生成多种类型的测验题目
5. 问答系统 - 苏格拉底式AI导师
6. 知识图谱 - 生成课程知识图谱
7. 学习路径 - 个性化学习推荐

模型配置:
- 智能模型: 用于复杂推理、创意写作(Qwen/Qwen3-32B)
- 快速模型: 用于摘要、分类等简单任务
"""

import uuid
import random
import os
import json
import re
import logging
import sys
from pathlib import Path
from dotenv import load_dotenv
from openai import AsyncOpenAI
from typing import List, Dict, Optional, Any

# 加载环境变量（必须在读取环境变量之前调用）
load_dotenv()

# 添加项目根目录到系统路径以导入共享配置
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
from shared.prompt_config import DIFFICULTY_LEVELS, TEACHING_STYLES, DifficultyLevel, TeachingStyle

# 导入提示模板
from prompts import (
    get_prompt,
)

# ============================================================================
# 配置与常量
# ============================================================================

# 配置日志记录
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# API密钥加载与验证
api_key = os.getenv("AI_API_KEY")
if api_key:
    masked_key = f"{api_key[:8]}...{api_key[-4:]}"
    logger.info(f"Loaded AI_API_KEY: {masked_key}")
else:
    logger.error("AI_API_KEY not found in environment variables")

# ============================================================================
# AI服务类
# ============================================================================

class AIService:
    """
    AI 模型交互的抽象层。
    支持根据任务复杂性在不同模型之间切换。
    """
    def __init__(self):
        # 通过环境变量配置 API 密钥
        self.api_key = os.getenv("AI_API_KEY")
        self.api_base = os.getenv("AI_API_BASE", "https://api-inference.modelscope.cn/v1")
        
        # 混合模型策略
        # 智能模型：用于复杂推理、创意写作和详细解释。
        self.model_smart = os.getenv("AI_MODEL", "Qwen/Qwen3-32B")
        
        # 快速模型：用于摘要、分类和简单任务。
        # 如果未指定，默认使用更小、更快的模型。
        self.model_fast = os.getenv("AI_MODEL_FAST", "Qwen/Qwen3-32B")
        
        self.client = AsyncOpenAI(
            base_url=self.api_base,
            api_key=self.api_key,
        )

    # ============================================================================
    # 内容解析工具方法
    # ============================================================================
    
    def _extract_json(self, text: str) -> Optional[Dict]:
        """
        从 LLM 响应中稳健地提取 JSON。
        
        提取策略（按优先级）：
        1. 直接解析完整响应
        2. 从 markdown JSON 代码块提取
        3. 从任意代码块提取
        4. 从文本中查找 JSON 对象边界
        
        Args:
            text: LLM 原始响应文本
            
        Returns:
            解析后的字典，失败返回 None
        """
        logger.info(f"Raw AI Response for JSON extraction: {text[:200]}...")

        # 策略1: 直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 策略2: 从 markdown JSON 代码块提取
        json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError as e:
                logger.warning(f"Markdown JSON decode error: {e}")
                pass

        # 策略3: 从任意代码块提取
        code_match = re.search(r'```\s*(.*?)\s*```', text, re.DOTALL)
        if code_match:
            try:
                return json.loads(code_match.group(1))
            except json.JSONDecodeError:
                pass

        # 策略4: 从文本边界提取
        try:
            start_idx = text.find('{')
            end_idx = text.rfind('}')
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                json_str = text[start_idx:end_idx+1]
                return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(f"Substring JSON decode error: {e}")
            pass

        # 所有策略失败
        logger.warning(f"Failed to extract JSON from: {text[:500]}...")
        
        # 调试：将失败的文本写入文件
        try:
            with open("debug_failed_json.txt", "w", encoding="utf-8") as f:
                f.write(text)
        except Exception:
            pass
            
        return None

    def _clean_mermaid_syntax(self, text: str) -> str:
        """
        修复 Mermaid 图表语法错误。
        
        主要修复：
        - 节点标签引号转义
        - 特殊字符处理
        - 不同图表类型的适配
        
        Args:
            text: 包含 Mermaid 图表的文本
            
        Returns:
            修复后的文本
        """
        pattern = r'```mermaid(.*?)```'
        
        def fix_mermaid_block(match):
            content = match.group(1)
            
            # 检测图表类型
            clean_lines = [line.strip() for line in content.split('\n') 
                           if line.strip() and not line.strip().startswith('%%')]
            
            if not clean_lines:
                return f'```mermaid{content}```'
                
            first_word = clean_lines[0].split(' ')[0]
            
            # 仅对流程图应用节点标签修复
            # 其他图表类型（序列图、类图等）的括号有特殊含义
            if first_word not in ['graph', 'flowchart']:
                return f'```mermaid{content}```'

            def safe_quote(text):
                """确保文本被双引号包裹，内部引号转义。"""
                text = text.strip()
                inner = text
                # 转义现有双引号
                inner = inner.replace('"', '\\"')
                return f'"{inner}"'

            # 修复各种节点形状的标签
            # 1. 方括号: [Text] -> ["Text"]
            content = re.sub(r'(?<!\[)\[(?![\[])([^\[\]]+?)(?<!\])\](?!\])', 
                             lambda m: f'[{safe_quote(m.group(1))}]', 
                             content)
            
            # 2. 圆括号: (Text) -> ("Text")
            content = re.sub(r'(?<!\()(\()(?![(\[])([^()]+?)(?<!\))(\))(?![\)])', 
                             lambda m: f'({safe_quote(m.group(2))})', 
                             content)
            
            # 3. 花括号: {Text} -> {"Text"}
            content = re.sub(r'(?<!\{)\{(?![{!])([^{}]+?)(?<!\})\}(?!\})', 
                             lambda m: f'{{{safe_quote(m.group(1))}}}', 
                             content)
            
            # 4. 双花括号: {{Text}} -> {{"Text"}}
            content = re.sub(r'\{\{([^{}]+?)\}\}', 
                             lambda m: f'{{{{{safe_quote(m.group(1))}}}}}', 
                             content)
            
            # 5. 双圆括号: ((Text)) -> (("Text"))
            content = re.sub(r'\(\(([^()]+?)\)\)', 
                             lambda m: f'(({safe_quote(m.group(1))}))', 
                             content)
            
            return f'```mermaid{content}```'

        return re.sub(pattern, fix_mermaid_block, text, flags=re.DOTALL)

    def _clean_latex_syntax(self, text: str) -> str:
        """
        修复和规范化 LaTeX 语法。
        
        转换规则：
        1. \[ ... \] -> $$ ... $$ (块级公式)
        2. \( ... \) -> $ ... $ (行内公式)
        3. 复杂环境自动包裹在 $$ 中
        4. 清理多余空行
        
        Args:
            text: 包含 LaTeX 的文本
            
        Returns:
            规范化后的文本
        """
        # 1. 转换块级公式标记
        text = re.sub(r'\\\[(.*?)\\\]', r'\n$$\n\1\n$$\n', text, flags=re.DOTALL)
        
        # 2. 转换行内公式标记
        text = re.sub(r'\\\((.*?)\\\)', r'$\1$', text, flags=re.DOTALL)
        
        # 3. 确保复杂环境被 $$ 包裹
        envs = r"matrix|pmatrix|bmatrix|vmatrix|Vmatrix|array|align|align\*|equation|equation\*|cases|gather|gather\*|alignat|alignat\*"
        pattern = fr'(\$\$)?\s*(\\begin{{({envs})}}.*?\\end{{\3}})\s*(\$\$)?'
        
        def fix_latex_block(match):
            content = match.group(2)
            return f"\n$$\n{content.strip()}\n$$\n"

        text = re.sub(pattern, fix_latex_block, text, flags=re.DOTALL)
        
        # 4. 清理多余空行（最多保留2个）
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text

    def clean_response_text(self, text: str) -> str:
        """
        清理 LLM 响应文本。
        
        处理流程：
        1. 去除 markdown 代码块包装
        2. 修复 LaTeX 语法
        3. 修复 Mermaid 语法
        
        Args:
            text: 原始响应文本
            
        Returns:
            清理后的文本
        """
        clean_text = text.strip()
        
        # 去除 ```markdown 包装
        if clean_text.startswith("```markdown") and clean_text.endswith("```"):
            clean_text = clean_text[11:-3].strip()
            
        # 修复 LaTeX
        clean_text = self._clean_latex_syntax(clean_text)
        
        # 修复 Mermaid
        clean_text = self._clean_mermaid_syntax(clean_text)
        
        return clean_text

    # ============================================================================
    # 核心 LLM 调用方法
    # ============================================================================
    
    async def _call_llm(
        self, 
        prompt: str, 
        system_prompt: str = "You are a helpful assistant.", 
        use_fast_model: bool = False
    ) -> str:
        """
        通用 LLM 调用函数。
        
        特性：
        - 支持模型路由（智能模型 vs 快速模型）
        - 支持流式响应
        - 自动处理推理内容日志
        
        Args:
            prompt: 用户输入提示
            system_prompt: 系统指令
            use_fast_model: 是否使用轻量/快速模型
            
        Returns:
            LLM 完整响应文本，失败返回 None
        """
        if not self.api_key:
            return None
        
        try:
            extra_body = {"enable_thinking": False}
            
            # 模型选择
            model_id = self.model_fast if use_fast_model else self.model_smart
            
            response = await self.client.chat.completions.create(
                model=model_id,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                stream=True,
                extra_body=extra_body
            )
            
            # 聚合流式响应
            full_content = ""
            async for chunk in response:
                if chunk.choices:
                    # 处理推理内容（用于日志/调试）
                    if hasattr(chunk.choices[0].delta, 'reasoning_content'):
                        reasoning = chunk.choices[0].delta.reasoning_content
                        if reasoning:
                            print(reasoning, end='', flush=True)
                            
                    delta = chunk.choices[0].delta
                    if delta.content:
                        full_content += delta.content
            
            logger.info(f"AI Response Complete (Model: {model_id})")
            return full_content
        except Exception as e:
            logger.error(f"AI API Call Error: {e}")
            return None

    # ============================================================================
    # 课程生成方法
    # ============================================================================
    
    async def generate_course(
        self, 
        keyword: str, 
        difficulty: DifficultyLevel = DIFFICULTY_LEVELS["INTERMEDIATE"], 
        style: TeachingStyle = TEACHING_STYLES["ACADEMIC"], 
        requirements: str = ""
    ) -> Dict:
        system_prompt = get_prompt("generate_course").format(
            keyword=keyword,
            difficulty=difficulty,
            style=style,
            requirements=requirements if requirements else "无"
        )
        prompt = f"用户想要学习“{keyword}”，请生成一份专业且系统的课程大纲。"
        
        response = await self._call_llm(prompt, system_prompt)
        if response:
            data = self._extract_json(response)
            if data and "nodes" in data:
                # Ensure unique UUIDs and process nested structure
                processed_nodes = []
                for node in data["nodes"]:
                    # L1 Node
                    node_id = str(uuid.uuid4())
                    node["node_id"] = node_id
                    node["node_level"] = 1
                    
                    sub_nodes = node.pop("sub_nodes", [])
                    processed_nodes.append(node)
                    
                    # L2 Nodes
                    for sub in sub_nodes:
                        sub["node_id"] = str(uuid.uuid4())
                        sub["parent_node_id"] = node_id
                        sub["node_level"] = 2
                        sub["node_type"] = "original"
                        if "node_content" not in sub:
                            sub["node_content"] = ""
                        processed_nodes.append(sub)
                
                data["nodes"] = processed_nodes
            return data
        return {"course_name": keyword, "nodes": []}

    # ==================== 测验生成方法 ====================

    async def generate_quiz(
        self,
        content: str,
        node_name: str = "",
        difficulty: DifficultyLevel = DIFFICULTY_LEVELS["INTERMEDIATE"],
        style: TeachingStyle = TEACHING_STYLES["ACADEMIC"],
        user_persona: str = "",
        question_count: int = 3,
        quiz_type: str = "mixed",
        previous_mistakes: List[Dict] = None
    ) -> List[Dict]:
        """
        增强版测验生成 - 支持多种题型和自适应难度

        处理流程:
        1. 构建个性化提示词（用户画像、错题分析）
        2. 根据题型要求生成题目分布
        3. 调用LLM生成测验题目
        4. 验证并标准化题目格式
        5. 失败时使用智能回退生成

        Args:
            content: 课程内容文本
            node_name: 节点名称（内容缺失时作为主题）
            difficulty: 难度级别 (beginner/intermediate/advanced)
            style: 学习风格 (academic/visual/pragmatic)
            user_persona: 用户画像描述
            question_count: 题目数量
            quiz_type: 测验类型 (mixed/conceptual/application/analysis)
            previous_mistakes: 用户之前的错题记录，用于针对性出题

        Returns:
            标准化后的测验题目列表
        """
        system_prompt = get_prompt("generate_quiz").format(
            difficulty=difficulty,
            style=style,
            question_count=question_count
        )
        
        content_text = content
        if not content or len(content) < 50:
            content_text = f"Topic: {node_name}\n(The detailed content is missing, please generate general questions based on this topic)"
        
        # 构建个性化提示
        personalization = ""
        if user_persona:
            personalization = f"\n用户画像：{user_persona}\n请根据用户背景调整题目难度和表述方式。"
        
        # 错题针对性提示
        mistake_focus = ""
        if previous_mistakes and len(previous_mistakes) > 0:
            mistake_topics = [m.get('topic', '') for m in previous_mistakes[-3:]]
            mistake_focus = f"\n用户之前在以下知识点容易出错：{', '.join(mistake_topics)}\n请针对这些薄弱环节设计题目。"
        
        # 题型分布建议
        type_distribution = {
            "mixed": "混合题型：40%概念理解 + 40%应用分析 + 20%综合判断",
            "conceptual": "概念题型：侧重基础概念和定义的理解",
            "application": "应用题型：侧重实际场景应用和问题解决",
            "analysis": "分析题型：侧重逻辑推理和深度分析"
        }
        
        prompt = f"""内容：
{content_text}
{personalization}
{mistake_focus}

题型要求：{type_distribution.get(quiz_type, type_distribution['mixed'])}
难度级别：{difficulty}

请生成恰好 {question_count} 道题目，JSON格式。
每道题必须包含以下字段：
- id: 题号
- type: 题型 (conceptual/application/analysis/synthesis)
- question: 题目内容
- options: 选项数组
- correct_index: 正确答案索引
- explanation: 详细解析（可用Markdown表格或Mermaid图表辅助说明）
- knowledge_point: 考察的知识点
- difficulty_score: 难度评分 (1-5)
"""
        
        response = await self._call_llm(prompt, system_prompt)
        if response:
            result = self._extract_json(response)
            if result:
                # 验证并补充题目字段
                validated_quiz = self._validate_quiz_questions(result, question_count)
                return validated_quiz

        # 智能回退：基于用户错题生成针对性题目
        logger.warning(f"Quiz generation failed for {node_name}. Using smart fallback.")
        return self._generate_smart_fallback_quiz(node_name, question_count, previous_mistakes)
    
    def _validate_quiz_questions(self, questions: List[Dict], expected_count: int) -> List[Dict]:
        """验证并标准化测验题目"""
        validated = []
        for i, q in enumerate(questions[:expected_count]):
            validated_q = {
                "id": q.get("id", i + 1),
                "type": q.get("type", "conceptual"),
                "question": q.get("question", "题目加载失败"),
                "options": q.get("options", ["选项A", "选项B", "选项C", "选项D"]),
                "correct_index": q.get("correct_index", 0),
                "explanation": q.get("explanation", "暂无解析"),
                "knowledge_point": q.get("knowledge_point", "未知知识点"),
                "difficulty_score": q.get("difficulty_score", 3)
            }
            validated.append(validated_q)
        return validated
    
    def _generate_smart_fallback_quiz(self, node_name: str, question_count: int, previous_mistakes: List[Dict] = None) -> List[Dict]:
        """智能回退测验生成 - 基于错题记录"""
        fallback_topic = node_name if node_name else "此主题"
        
        # 基础题目模板
        base_questions = [
            {
                "id": 1,
                "type": "conceptual",
                "question": f"关于「{fallback_topic}」的核心概念，以下描述正确的是？",
                "options": [
                    f"{fallback_topic} 是一个孤立的概念，与其他知识无关",
                    f"{fallback_topic} 是该学科体系中的关键组成部分",
                    f"{fallback_topic} 已经被现代理论完全推翻",
                    f"{fallback_topic} 仅在特定极端情况下适用"
                ],
                "correct_index": 1,
                "explanation": f"**解析**：{fallback_topic} 作为核心知识点，在学科体系中起着承上启下的作用，是理解后续内容的基础。",
                "knowledge_point": f"{fallback_topic}的核心概念",
                "difficulty_score": 2
            },
            {
                "id": 2,
                "type": "application",
                "question": f"在实际应用中，理解「{fallback_topic}」主要有助于解决什么问题？",
                "options": [
                    "历史背景的考证",
                    "复杂系统中的关键机制分析",
                    "无关数据的随机处理",
                    "纯粹的理论推导游戏"
                ],
                "correct_index": 1,
                "explanation": f"**解析**：掌握{fallback_topic}的原理，能够帮助我们分析和处理实际系统中的复杂机制与关键问题。",
                "knowledge_point": f"{fallback_topic}的实际应用",
                "difficulty_score": 3
            },
            {
                "id": 3,
                "type": "analysis",
                "question": f"对于初学者来说，学习「{fallback_topic}」最大的挑战通常是？",
                "options": [
                    "概念过于简单，缺乏挑战",
                    "理解其抽象逻辑与实际场景的映射",
                    "相关资料太少，无法查阅",
                    "没有任何挑战，一学就会"
                ],
                "correct_index": 1,
                "explanation": f"**解析**：{fallback_topic}往往包含一定的抽象逻辑，将其准确映射到实际应用场景中是初学者常见的难点。",
                "knowledge_point": f"{fallback_topic}的学习难点",
                "difficulty_score": 3
            },
            {
                "id": 4,
                "type": "conceptual",
                "question": f"以下哪项不是「{fallback_topic}」的典型特征？",
                "options": [
                    "系统性",
                    "逻辑性",
                    "随意性",
                    "实用性"
                ],
                "correct_index": 2,
                "explanation": f"**解析**：{fallback_topic}作为科学或专业知识，具有严密的逻辑和系统性，绝非随意构建。",
                "knowledge_point": f"{fallback_topic}的特征",
                "difficulty_score": 2
            },
            {
                "id": 5,
                "type": "synthesis",
                "question": f"深入掌握「{fallback_topic}」后，下一步通常应该学习？",
                "options": [
                    "放弃该学科",
                    "该领域的进阶理论或相关交叉学科",
                    "完全不相关的领域",
                    "重复学习基础概念"
                ],
                "correct_index": 1,
                "explanation": f"**解析**：在掌握基础后，进阶理论或交叉学科的应用是深入研究的必经之路。",
                "knowledge_point": f"{fallback_topic}的学习路径",
                "difficulty_score": 4
            }
        ]
        
        # 如果有错题记录，优先返回相关类型的题目
        if previous_mistakes and len(previous_mistakes) > 0:
            weak_types = set(m.get('question_type', 'conceptual') for m in previous_mistakes[-5:])
            prioritized = [q for q in base_questions if q['type'] in weak_types]
            other = [q for q in base_questions if q['type'] not in weak_types]
            combined = prioritized + other
            return combined[:question_count]
        
        return base_questions[:question_count]
    
    async def analyze_quiz_performance(
        self,
        quiz_results: List[Dict],
        user_answers: List[int],
        user_id: str = "default"
    ) -> Dict:
        """
        分析测验表现，生成学习建议

        处理流程:
        1. 统计正确/错误题目数量
        2. 分析薄弱知识点和错误模式
        3. 根据得分生成个性化建议
        4. 生成下一步学习计划

        Args:
            quiz_results: 测验题目和正确答案
            user_answers: 用户的答案
            user_id: 用户ID

        Returns:
            分析报告包含：
            - score: 正确题数
            - total: 总题数
            - percentage: 得分百分比
            - weak_points: 薄弱知识点列表
            - mistake_patterns: 错误类型统计
            - recommendations: 学习建议
            - next_steps: 下一步行动
        """
        if not quiz_results or not user_answers:
            return {"score": 0, "analysis": "无测验数据"}
        
        correct_count = 0
        weak_points = []
        mistake_patterns = {}
        
        for i, (question, user_answer) in enumerate(zip(quiz_results, user_answers)):
            is_correct = user_answer == question.get('correct_index', 0)
            if is_correct:
                correct_count += 1
            else:
                weak_points.append({
                    "question_id": question.get('id'),
                    "knowledge_point": question.get('knowledge_point', '未知'),
                    "question_type": question.get('type', 'conceptual'),
                    "difficulty": question.get('difficulty_score', 3)
                })
                
                # 统计错误类型
                q_type = question.get('type', 'conceptual')
                mistake_patterns[q_type] = mistake_patterns.get(q_type, 0) + 1
        
        total = len(quiz_results)
        score_percentage = (correct_count / total * 100) if total > 0 else 0
        
        # 生成学习建议
        recommendations = []
        if score_percentage >= 90:
            recommendations.append("表现优秀！建议挑战更高难度的内容或进行知识拓展。")
        elif score_percentage >= 70:
            recommendations.append("掌握良好，建议针对错题进行复习巩固。")
        elif score_percentage >= 50:
            recommendations.append("基础尚可，建议重新学习薄弱知识点。")
        else:
            recommendations.append("需要加强基础，建议重新阅读课程内容并做笔记。")
        
        # 基于错误模式给出建议
        if mistake_patterns:
            weakest_type = max(mistake_patterns, key=mistake_patterns.get)
            type_names = {
                "conceptual": "概念理解",
                "application": "应用分析",
                "analysis": "深度分析",
                "synthesis": "综合判断"
            }
            recommendations.append(f"在「{type_names.get(weakest_type, weakest_type)}」题型上需要加强练习。")
        
        return {
            "score": correct_count,
            "total": total,
            "percentage": round(score_percentage, 1),
            "weak_points": weak_points,
            "mistake_patterns": mistake_patterns,
            "recommendations": recommendations,
            "next_steps": self._generate_next_steps(score_percentage, weak_points)
        }
    
    def _generate_next_steps(self, score_percentage: float, weak_points: List[Dict]) -> List[str]:
        """
        生成下一步学习建议

        根据测验得分和薄弱知识点，生成个性化的学习行动计划。
        得分低于60%建议重新学习基础，60-80%建议复习巩固，
        高于80%建议进阶拓展。

        Args:
            score_percentage: 得分百分比
            weak_points: 薄弱知识点列表

        Returns:
            下一步学习建议列表
        """
        steps = []
        
        if score_percentage < 60:
            steps.append("重新阅读相关章节内容")
            steps.append("整理核心概念笔记")
            steps.append("向AI导师提问澄清疑惑")
        elif score_percentage < 80:
            steps.append("复习错题对应的知识点")
            steps.append("尝试用自己的话解释概念")
            steps.append("寻找更多相关例题练习")
        else:
            steps.append("尝试教授他人所学内容")
            steps.append("探索该知识点的进阶应用")
            steps.append("与其他知识点建立联系")
        
        # 针对薄弱知识点给出具体建议
        if weak_points:
            weak_knowledge = list(set(wp['knowledge_point'] for wp in weak_points))[:2]
            for kp in weak_knowledge:
                steps.append(f"重点复习：{kp}")
        
        return steps

    # ==================== 子节点生成方法 ====================

    async def generate_sub_nodes(
        self,
        node_name: str,
        node_level: int,
        node_id: str,
        course_name: str = "",
        parent_context: str = "",
        course_outline: str = "",
        difficulty: DifficultyLevel = DIFFICULTY_LEVELS["INTERMEDIATE"],
        style: TeachingStyle = TEACHING_STYLES["ACADEMIC"]
    ) -> List[Dict]:
        """
        生成子节点内容

        根据父节点信息生成下一层级的子节点列表，
        包含子节点名称和内容大纲。

        Args:
            node_name: 当前节点名称
            node_level: 当前节点层级
            node_id: 当前节点ID
            course_name: 课程名称
            parent_context: 父节点上下文
            course_outline: 课程大纲
            difficulty: 难度级别
            style: 学习风格

        Returns:
            子节点列表，每个节点包含node_id、parent_node_id、
            node_name、node_level、node_content、node_type
        """
        system_prompt = get_prompt("generate_sub_nodes").format(
            course_name=course_name if course_name else "未知课程",
            parent_context=parent_context if parent_context else "无",
            course_outline=course_outline if course_outline else "无",
            difficulty=difficulty,
            style=style
        )
        prompt = f"当前节点信息：名称={node_name}，层级={node_level}。请列出该章节下的所有子小节，确保结构完整且具备专业性。"
        
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

        return [
            {"node_id": str(uuid.uuid4()), "parent_node_id": node_id, "node_name": f"{node_name} - 子节点 1", "node_level": new_level, "node_content": "", "node_type": "custom"},
            {"node_id": str(uuid.uuid4()), "parent_node_id": node_id, "node_name": f"{node_name} - 子节点 2", "node_level": new_level, "node_content": "", "node_type": "custom"}
        ]

    # ==================== 流式 LLM 调用方法 ====================

    async def _stream_llm(
        self,
        prompt: str,
        system_prompt: str = "You are a helpful assistant.",
        use_fast_model: bool = False
    ):
        """
        流式 LLM 调用 - 生成器函数

        以流式方式调用LLM，逐块返回生成的内容，
        适用于实时显示长文本生成过程。

        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词
            use_fast_model: 是否使用快速模型

        Yields:
            生成的文本块
        """
        if not self.api_key:
            yield "AI Service not configured."
            return

        try:
            extra_body = {"enable_thinking": False}

            # 选择模型
            model_id = self.model_fast if use_fast_model else self.model_smart

            response = await self.client.chat.completions.create(
                model=model_id,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                stream=True,
                extra_body=extra_body
            )

            async for chunk in response:
                if chunk.choices:
                    # 处理推理内容（用于日志/调试）
                    if hasattr(chunk.choices[0].delta, 'reasoning_content'):
                        reasoning = chunk.choices[0].delta.reasoning_content
                        if reasoning:
                            # 可以记录思考过程或暂时忽略
                            pass

                    delta = chunk.choices[0].delta
                    if delta.content:
                        yield delta.content
        except Exception as e:
            logger.error(f"Stream Error: {e}")
            yield f"\n[Error: {str(e)}]"

    # ==================== 内容重定义方法 ====================

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

        以流式方式重新生成节点内容，支持课程上下文和前置内容引用，
        适用于实时显示内容生成过程。

        Args:
            node_name: 节点名称
            original_content: 原始内容
            requirement: 内容要求
            course_context: 课程上下文
            previous_context: 前置节点内容
            difficulty: 难度级别
            style: 学习风格

        Yields:
            生成的内容块
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
        重定义节点内容

        根据特定要求重新生成节点内容，使用高级提示词工程
        确保内容结构清晰、专业。

        Args:
            node_name: 节点名称
            requirement: 内容要求/指令
            original_content: 原始内容（可选）
            course_context: 课程上下文
            previous_context: 前置节点内容
            difficulty: 难度级别 (beginner/intermediate/advanced/expert)
            style: 学习风格 (academic/visual/pragmatic)

        Returns:
            清理后的Markdown格式内容
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

    async def generate_node_content(
        self,
        node_name: str,
        node_context: str = "",
        node_id: str = "",
        course_name: str = "",
        difficulty: str = DIFFICULTY_LEVELS["ADVANCED"],
        style: str = TEACHING_STYLES["ACADEMIC"]
    ) -> str:
        """
        生成节点详细正文内容

        为L2子章节生成高质量的详细教科书内容，根据难度级别自动调整内容深度。
        使用GENERATE_CONTENT提示词确保生成完整的正文内容。

        Args:
            node_name: 节点名称
            node_context: 节点上下文线索
            node_id: 节点ID
            course_name: 课程名称
            difficulty: 难度级别 (beginner/intermediate/expert)
            style: 学习风格

        Returns:
            生成的Markdown格式详细正文内容
        """
        from prompts import get_prompt
        
        # 构建课程上下文
        course_context = f"课程名称：{course_name}"
        if node_context:
            course_context += f"\n上下文线索：{node_context}"
        
        # 使用GENERATE_CONTENT提示词生成详细正文
        system_prompt = get_prompt("generate_content").format(
            node_name=node_name,
            node_level="2",
            course_context=course_context,
            difficulty=difficulty,
            style=style
        )
        
        prompt = f"请为'{node_name}'生成完整的详细正文内容。务必包含丰富的理论解释、示例和总结，内容要详实、专业。"

        response = await self._call_llm(prompt, system_prompt)
        if response:
            return self.clean_response_text(response)

        return f"## {node_name}\n\n详细正文内容生成中...\n\n请稍后重试。"

    async def extend_content(self, node_name: str, requirement: str) -> str:
        """
        拓展节点内容

        为节点生成深度延伸阅读材料，补充前沿研究、工程陷阱、
        底层原理或跨学科关联。

        Args:
            node_name: 节点名称
            requirement: 拓展方向/要求

        Returns:
            拓展内容的Markdown格式文本
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
   - 块级公式用 `$$` 包裹。
   - 严禁裸写 LaTeX 命令。
6. **输出格式**：直接输出 **Markdown 格式的内容**，**不需要**包含在 JSON 对象中。
"""
        prompt = f"当前章节：{node_name}\n拓展方向：{requirement}"

        response = await self._call_llm(prompt, system_prompt)
        if response:
            return self.clean_response_text(response)

        return f"拓展知识点：\n关于 {node_name} 的延伸阅读... {requirement}"

    # ==================== 苏格拉底式导师方法 ====================

    async def socratic_tutor(
        self,
        user_message: str,
        course_context: str,
        current_node: Dict,
        relevant_content: str,
        user_notes: str,
        chat_history: List[Dict],
        user_id: str = "default",
        learning_stage: str = "exploring"
    ):
        """
        增强版苏格拉底式AI导师 - 启发式教学

        通过提问引导用户主动思考，而非直接给出答案。
        分析用户意图和学习状态，生成个性化引导内容。

        Args:
            user_message: 用户消息
            course_context: 课程上下文
            current_node: 当前学习节点
            relevant_content: 相关课程内容
            user_notes: 用户笔记
            chat_history: 对话历史
            user_id: 用户ID
            learning_stage: 当前学习阶段 (exploring/practicing/mastering/reviewing)

        Yields:
            生成的引导内容块
        """
        from prompts import get_prompt
        
        # 使用DualMemoryController构建提示词
        from memory import DualMemoryController
        memory_controller = DualMemoryController(course_context, current_node, chat_history)
        system_prompt = memory_controller.build_socratic_prompt(user_id)
        
        # 分析用户意图和学习状态
        intent_analysis = self._analyze_user_intent(user_message, chat_history)
        
        # 格式化用户上下文
        context_text = f"""
当前学习章节：{current_node.get('node_name', '未知章节')}
章节内容：
{relevant_content[:1000]}

用户笔记：
{user_notes[:500] if user_notes else '暂无笔记'}

学习阶段：{learning_stage}
用户意图：{intent_analysis['intent']}
理解程度：{intent_analysis['comprehension_level']}

用户问题：{user_message}
"""
        
        prompt_template = get_prompt("socratic_tutor")
        user_prompt = prompt_template.format(context=context_text)
        
        # 添加结构化输出要求
        structured_prompt = f"""{user_prompt}

请以以下结构化格式输出：
1. **思考引导**：提出启发性问题引导用户思考
2. **知识关联**：关联已学知识和新概念
3. **实例说明**：提供具体例子帮助理解
4. **反思问题**：提出反思性问题加深理解
5. **下一步建议**：建议用户接下来可以做什么

输出要求：
- 使用Markdown格式
- 每个部分用 ### 标题分隔
- 包含至少2-3个启发性问题
- 提供1个具体实例
"""
        
        async for chunk in self._stream_llm(structured_prompt, system_prompt):
            yield chunk
    
    def _analyze_user_intent(self, user_message: str, chat_history: List[Dict]) -> Dict:
        """
        分析用户意图和理解程度

        通过关键词匹配识别用户的主要意图，并根据对话历史长度
        评估用户的理解程度。

        Args:
            user_message: 用户消息
            chat_history: 对话历史

        Returns:
            包含意图、理解程度和详细检测结果的字典
        """
        message_lower = user_message.lower()
        
        # 意图识别
        intents = {
            'question': any(kw in message_lower for kw in ['为什么', '怎么', '如何', '什么', '?', '吗']),
            'confirmation': any(kw in message_lower for kw in ['对吗', '是不是', '是否正确', '理解']),
            'example_request': any(kw in message_lower for kw in ['例子', '举例', '示例', '比如']),
            'explanation_request': any(kw in message_lower for kw in ['解释', '说明', '详细', '展开']),
            'application': any(kw in message_lower for kw in ['应用', '使用', '实践', '做', '实现']),
        }
        
        # 确定主要意图
        primary_intent = 'general'
        for intent, detected in intents.items():
            if detected:
                primary_intent = intent
                break
        
        # 评估理解程度（基于历史对话长度和复杂度）
        history_length = len(chat_history)
        if history_length < 3:
            comprehension = "beginner"
        elif history_length < 8:
            comprehension = "intermediate"
        else:
            comprehension = "advanced"
        
        return {
            'intent': primary_intent,
            'comprehension_level': comprehension,
            'details': intents
        }

    # ==================== 问答生成方法 ====================

    async def answer_question_stream(
        self,
        question: str,
        context: str,
        history: List[dict] = [],
        selection: str = "",
        user_persona: str = "",
        course_id: str = None,
        node_id: str = None,
        user_notes: str = "",
        session_metrics: dict = None,
        enable_long_term_memory: bool = False
    ):
        """
        流式回答用户问题 - 带元数据

        生成回答并在末尾附加元数据，支持双记忆系统优化。
        输出格式：[回答内容]\n\n---METADATA---\n{JSON元数据}

        Args:
            question: 用户问题
            context: 课程内容上下文
            history: 对话历史
            selection: 用户选中的文本
            user_persona: 用户画像
            course_id: 课程ID
            node_id: 当前节点ID
            user_notes: 用户笔记
            session_metrics: 会话指标数据
            enable_long_term_memory: 是否启用长期记忆

        Yields:
            回答内容块
        """
        system_prompt = ""
        
        # Build session context from metrics if available
        session_context = ""
        if session_metrics and enable_long_term_memory:
            session_context = f"""
=== 会话上下文感知 ===
本次会话统计：
- 总消息数：{session_metrics.get('totalMessages', 0)}
- 用户消息：{session_metrics.get('userMessages', 0)}
- AI消息：{session_metrics.get('aiMessages', 0)}
- 会话时长：{session_metrics.get('sessionDuration', 0)} 分钟
- 讨论主题：{', '.join(session_metrics.get('topics', []))}
- 主要问题类型：{', '.join(session_metrics.get('questionTypes', []))}

请根据以上会话背景，保持回答的连贯性和上下文一致性。
"""
        
        # Try to use Dual Memory System if context is available
        if course_id and node_id:
            try:
                # Local import to avoid circular dependency if any
                from memory import memory_controller
                
                # 1. Optimize History (Context Compression)
                # Pass the summarizer method from this instance to avoid circular dependency
                optimized_history = await memory_controller.optimize_history(history, self.summarize_history)
                
                # 2. Build Dual Memory Prompt
                system_prompt = memory_controller.build_tutor_prompt(course_id, node_id, question, optimized_history)
                
                # Add session context if available
                if session_context:
                    system_prompt += session_context
                
                # Use optimized history for prompt construction
                history = optimized_history
                
                # Append the metadata instruction which is critical for frontend parsing
                # We inject the current node_id as default if AI doesn't find a better one
                system_prompt += f"""

=== METADATA OUTPUT RULE (MANDATORY) ===
You MUST output the metadata at the very end of your response.

**Format**:
[Your Answer Content Here]

---METADATA---
{{"node_id": "{node_id}", "quote": "quote from text if any", "anno_summary": "Core knowledge points summary in Markdown bullet points (3-5 points)"}}

DO NOT wrap the JSON in markdown code blocks.
"""
            except Exception as e:
                logger.error(f"Dual Memory Error: {e}")
                # Fallback will be handled below
        
        if not system_prompt:
            # Fallback / Standard Prompt
            system_prompt = f"""
你是学术助手，请根据提供的课程内容、对话历史和选中的文本回答用户的问题。

**用户画像（个性化设定）**：
{user_persona if user_persona else "通用学习者"}
请根据用户画像调整你的回答风格、深度和举例方式。例如，如果用户是初学者，请多用生活类比；如果是专家，请深入底层原理。

{session_context if session_context else ""}

**核心任务**：
1. **回答问题**：直接、专业、简洁地回答用户问题。
2. **定位上下文**：识别答案关联的课程章节或原文。
3. **格式化输出**：
   - **表格**：凡是涉及对比、数据列举、步骤说明的内容，**必须使用 Markdown 表格**展示。
   - **图表**：凡是涉及流程、架构、思维导图的内容，**必须使用 Mermaid 代码块**展示。
   - **代码**：代码片段请使用标准代码块。

**教师模式（TEACHER MODE - 增强版）**：
请像一位真实的苏格拉底式导师（Socratic Tutor）一样：
1. **启发式教学**：
   - 不要直接给出一层不变的答案。
   - 回答完问题后，**必须**主动提出一个相关的、有深度的后续问题（Follow-up Question），引导用户进一步思考。
   - 问题应该基于当前的知识点，或者是将理论联系实际的场景题。
2. **关联记忆（Memory Recall）**：
   - 如果用户之前问过类似问题或犯过类似错误（参考对话历史），请在回答中明确指出：“正如我们之前讨论的...”或“注意不要混淆...”。
3. **定位原文（Locate）**：
   - 尽量在提供的课程内容中找到能够支持你回答的**原句**。
   - 将找到的原句放入 metadata 的 `quote` 字段中。前端界面会自动高亮显示这句话，就像老师在课本上划线一样。
   - 如果找不到精确原句，不要编造。
4. **总结笔记（Note Taking）**：
   - 在 `anno_summary` 中生成一个核心知识点概括（Markdown 列表，3-5点），方便用户快速回顾。

**创新想法捕捉（Innovation Capture）**：
- 如果用户提出了新的解法、思路或独特的见解，请予以积极反馈。
- 帮助用户完善思路，并标记这是一个“创新想法”。
- 在 metadata 的 `anno_summary` 中，使用 `💡 想法：` 开头。

**输出格式规范（严格执行）**：
为了支持流式输出和后续处理，输出必须分为两部分，用 `---METADATA---` 分隔。

**第一部分：回答正文**
- 直接输出 Markdown 格式的回答内容。
- **表格支持（强制要求）**：凡是涉及对比（VS）、参数列表、步骤说明或数据展示的内容，**必须**使用 Markdown 表格呈现。
- **图表支持（强烈推荐）**：凡是涉及流程、时序、类关系或思维导图，请使用 Mermaid 代码块（```mermaid ... ```）展示。
- **严禁**将整个回答包裹在代码块中。
- 回答结束后，**另起一段**，用加粗字体写出你的后续提问：**思考题：...**

**第二部分：元数据**
- 正文结束后，**另起一行**输出分隔符：`---METADATA---`
- 紧接着输出一个标准的 JSON 对象（不要用 markdown 代码块包裹），包含：
  - `node_id`: (string) 答案主要参考的章节ID。如果无法确定，返回 null。
  - `quote`: (string) 答案引用的原文片段（必须是原文中存在的句子）。如果没有引用，返回 null。
  - `anno_summary`: (string) 核心知识点概括，使用 Markdown 无序列表格式（3-5点）。

**示例**：
什么是递归？
递归是指函数调用自身的编程技巧...（解释内容）

**思考题：你能想到生活中有什么现象是类似于递归的吗？**

---METADATA---
{{"node_id": "uuid-123", "quote": "递归是...", "anno_summary": "递归的概念"}}
"""

        # Build prompt
        history_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in history[-5:]])
        
        prompt = f"""
课程内容片段（正文知识）：
{context}

用户笔记（学习足迹）：
{user_notes if user_notes else "无"}

对话历史：
{history_text}

选中内容（用户针对这段文字提问）：
{selection if selection else "无"}

用户问题：{question}

请开始回答（记得在最后附加元数据）：
"""
        async for chunk in self._stream_llm(prompt, system_prompt):
            yield chunk

    async def summarize_note(self, content: str) -> str:
        """
        生成笔记摘要/标题

        基于笔记内容生成简洁的标题或摘要。
        如果内容包含问答结构，优先总结问题部分。

        Args:
            content: 笔记内容

        Returns:
            生成的标题或摘要
        """
        system_prompt = get_prompt("summarize_note").format()
        
        # If content contains Q&A structure, try to summarize the Question primarily
        prompt = f"笔记内容：\n{content[:2000]}\n\n请生成标题："
        
        # Use Fast Model
        response = await self._call_llm(prompt, system_prompt, use_fast_model=True)
        return response if response else (content[:20] + "...")

    async def summarize_chat(
        self,
        history: List[dict],
        course_context: str = "",
        user_persona: str = ""
    ) -> Dict:
        """
        生成对话复盘总结

        基于对话历史生成详细的复盘报告，包含关键知识点回顾和学习建议。

        Args:
            history: 对话历史记录
            course_context: 课程背景信息
            user_persona: 用户画像

        Returns:
            包含标题和内容的总结字典
        """
        system_prompt = get_prompt("summarize_chat").format(
            user_persona=user_persona if user_persona else "通用学习者"
        )
        
        # Convert history to text
        history_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in history])
        
        prompt = f"课程背景：\n{course_context}\n\n对话历史：\n{history_text}\n\n请生成详细的复盘报告，确保内容丰富充实："
        
        # Use standard model for better quality summary
        response = await self._call_llm(prompt, system_prompt, use_fast_model=False)
        if response:
            return self._extract_json(response) or {"title": "对话总结", "content": response}
        return {"title": "总结失败", "content": "无法生成总结。"}

    async def summarize_history(self, history: List[Dict]) -> str:
        """
        总结对话历史

        使用LLM对对话历史进行摘要总结。

        Args:
            history: 对话历史记录列表

        Returns:
            对话摘要文本
        """
        system_prompt = get_prompt("summarize_history").format()
        history_text = "\n".join([f"{msg.get('role', 'unknown')}: {msg.get('content', '')}" for msg in history])
        
        prompt = f"Please summarize the following conversation:\n\n{history_text}"
        
        # Use Fast Model for summarization
        response = await self._call_llm(prompt, system_prompt, use_fast_model=True)
        return response if response else "Previous conversation summary (auto-generated failed)."

    # ==================== 知识图谱生成方法 ====================

    async def generate_knowledge_graph(
        self,
        course_name: str,
        course_context: str,
        nodes: List[Dict]
    ) -> Dict:
        """
        生成知识图谱结构

        基于课程内容生成知识图谱，包含节点和关系。
        支持自修复机制，自动验证和修复无效的章节ID。

        Args:
            course_name: 课程名称
            course_context: 课程大纲/上下文
            nodes: 课程节点列表

        Returns:
            包含nodes和edges的知识图谱字典
        """
        from prompts import get_prompt
        
        # Build course context summary
        nodes_summary = []
        for node in nodes[:50]:  # Increased limit to cover full course structure
            nodes_summary.append({
                "id": node.get("node_id", ""),
                "name": node.get("node_name", ""),
                "level": node.get("node_level", 1),
                "content": node.get("node_content", "")[:200]  # Increased content context
            })
        
        context_text = f"""
课程名称：{course_name}

课程大纲：
{course_context}

章节列表：
{json.dumps(nodes_summary, ensure_ascii=False, indent=2)}
"""
        
        # Get the knowledge graph prompt template
        prompt_template = get_prompt("generate_knowledge_graph")
        system_prompt = prompt_template.format(
            course_name=course_name,
            course_context=context_text
        )
        
        user_prompt = f"""请基于以下课程内容生成知识图谱：

课程名称：{course_name}

主要章节：
{chr(10).join([f"- [ID: {n.get('id', '')}] {n.get('name', '')}: {n.get('content', '')[:50]}..." for n in nodes_summary[:15]])}

请生成包含节点和关系的知识图谱JSON。"""
        
        response = await self._call_llm(user_prompt, system_prompt)
        
        if response:
            result = self._extract_json(response)
            if result and "nodes" in result and "edges" in result and len(result["nodes"]) > 0:
                # Self-Healing: Validate and fix chapter_ids
                valid_chapter_ids = {n.get("node_id") for n in nodes}
                node_name_to_id = {n.get("node_name"): n.get("node_id") for n in nodes}
                
                for graph_node in result["nodes"]:
                    chapter_id = graph_node.get("chapter_id")
                    
                    # If invalid or missing
                    if not chapter_id or chapter_id not in valid_chapter_ids:
                        best_match_id = None
                        
                        # Priority 0: Check if chapter_id is actually a node name
                        if chapter_id in node_name_to_id:
                            best_match_id = node_name_to_id[chapter_id]

                        # Priority 1: Match by Node Label (Exact)
                        if not best_match_id:
                            node_label = graph_node.get("label", "")
                            for n in nodes:
                                if n.get("node_name", "") == node_label:
                                    best_match_id = n.get("node_id")
                                    break
                                    
                        # Priority 2: Match by Node Label (Substring)
                        if not best_match_id:
                            node_label = graph_node.get("label", "")
                            for n in nodes:
                                if node_label in n.get("node_name", "") or n.get("node_name", "") in node_label:
                                    best_match_id = n.get("node_id")
                                    break
                        
                        # Fallback to the first available node if no match found
                        if not best_match_id and nodes:
                            best_match_id = nodes[0].get("node_id")
                            
                        if best_match_id:
                            graph_node["chapter_id"] = best_match_id
                            
                return result
        
        # Fallback: Generate a simple graph based on node hierarchy
        logger.warning("Knowledge graph generation failed, using fallback")
        return self._generate_fallback_knowledge_graph(nodes)
    
    def _generate_fallback_knowledge_graph(self, nodes: List[Dict]) -> Dict:
        """
        生成回退知识图谱

        当知识图谱生成失败时，基于节点层级结构生成简单的回退图谱。
        根据节点层级确定节点类型，创建父子关系边。

        Args:
            nodes: 课程节点列表

        Returns:
            包含nodes和edges的简单知识图谱
        """
        graph_nodes = []
        graph_edges = []
        
        # Create nodes
        for node in nodes[:15]:
            node_id = node.get("node_id", str(uuid.uuid4()))
            node_level = node.get("node_level", 1)
            
            # Determine node type based on level
            if node_level == 1:
                node_type = "module"
            else:
                node_type = "concept"
            
            graph_nodes.append({
                "id": node_id,
                "label": node.get("node_name", "Unknown"),
                "type": node_type,
                "description": node.get("node_content", "")[:50],
                "chapter_id": node_id
            })
        
        # Add Root Node
        root_id = "root_" + str(uuid.uuid4())[:8]
        graph_nodes.insert(0, {
            "id": root_id,
            "label": "课程核心",
            "type": "root",
            "description": "课程根节点",
            "chapter_id": nodes[0].get("node_id") if nodes else ""
        })
        
        # Connect Root to Level 1 Modules
        for node in graph_nodes:
             if node["type"] == "module":
                graph_edges.append({
                    "source": root_id,
                    "target": node["id"],
                    "relation": "contains",
                    "label": "包含"
                })

        # Create edges based on parent-child relationships
        node_map = {n["id"]: n for n in graph_nodes}
        for node in nodes[:15]:
            node_id = node.get("node_id", "")
            parent_id = node.get("parent_node_id", "")
            
            if parent_id and parent_id in node_map and node_id in node_map:
                graph_edges.append({
                    "source": parent_id,
                    "target": node_id,
                    "relation": "contains",
                    "label": "包含"
                })
        
        # Add some cross-references between same-level nodes
        level_groups = {}
        for node in graph_nodes:
            level = node.get("type", "basic")
            if level not in level_groups:
                level_groups[level] = []
            level_groups[level].append(node)
        
        # Connect nodes within same level
        for level, group in level_groups.items():
            for i in range(len(group) - 1):
                if len(graph_edges) < 30:  # Limit total edges
                    graph_edges.append({
                        "source": group[i]["id"],
                        "target": group[i + 1]["id"],
                        "relation": "related",
                        "label": "关联"
                    })
        
        return {
            "nodes": graph_nodes,
            "edges": graph_edges
        }

    def locate_node(self, keyword: str, all_nodes: List[Dict]) -> Dict:
        """
        定位节点

        基于关键词在节点列表中搜索匹配的节点。
        使用简单的关键词匹配（MVP阶段），未来可升级为语义搜索。

        Args:
            keyword: 搜索关键词
            all_nodes: 所有节点列表

        Returns:
            匹配节点信息字典，未找到返回空字典
        """
        for node in all_nodes:
            if keyword in node['node_name']:
                return {
                    "match_node_id": node['node_id'],
                    "match_node_name": node['node_name'],
                    "node_path": "Path/To/Node"  # Mock path
                }
        return {}

    # ==================== 学习路径生成方法 ====================

    async def generate_learning_path(
        self,
        course_id: str,
        progress_data: List[Dict],
        wrong_answer_nodes: List[str],
        target_goal: str,
        available_time: int,
        all_nodes: List[Dict]
    ) -> Dict:
        """
        生成个性化学习路径推荐

        基于用户的学习进度、薄弱环节和目标生成个性化学习路径。
        包含进度分析、薄弱点识别和学习计划生成。

        Args:
            course_id: 课程ID
            progress_data: 各章节学习进度列表
            wrong_answer_nodes: 用户答错题目的节点ID列表
            target_goal: 用户学习目标
            available_time: 每日可用学习时间（分钟）
            all_nodes: 课程所有节点

        Returns:
            包含recommendations、weak_points和study_plan的字典
        """
        from prompts import get_prompt
        
        # Build progress summary
        total_nodes = len(all_nodes)
        completed_nodes = sum(1 for p in progress_data if p.get('is_read', False))
        progress_percent = (completed_nodes / total_nodes * 100) if total_nodes > 0 else 0
        
        # Identify weak points
        weak_points = []
        node_map = {n.get('node_id'): n for n in all_nodes}
        
        for progress in progress_data:
            node_id = progress.get('node_id')
            node = node_map.get(node_id)
            if not node:
                continue
                
            node_name = node.get('node_name', 'Unknown')
            
            # Check for weak points
            if progress.get('quiz_score') is not None and progress.get('quiz_score', 100) < 60:
                weak_points.append({
                    "node_id": node_id,
                    "node_name": node_name,
                    "weakness_type": "low_quiz_score",
                    "severity": "high" if progress.get('quiz_score', 0) < 40 else "medium",
                    "suggested_action": f"重新学习 {node_name} 并做练习题"
                })
            elif progress.get('read_time_minutes', 0) < 5 and progress.get('is_read', False):
                weak_points.append({
                    "node_id": node_id,
                    "node_name": node_name,
                    "weakness_type": "insufficient_reading",
                    "severity": "medium",
                    "suggested_action": f"仔细阅读 {node_name} 的内容"
                })
        
        # Add wrong answer nodes as weak points
        for node_id in wrong_answer_nodes:
            if node_id not in [wp['node_id'] for wp in weak_points]:
                node = node_map.get(node_id)
                if node:
                    weak_points.append({
                        "node_id": node_id,
                        "node_name": node.get('node_name', 'Unknown'),
                        "weakness_type": "frequent_wrong_answers",
                        "severity": "high",
                        "suggested_action": f"复习 {node.get('node_name', '该章节')} 并理解正确答案"
                    })
        
        # Build prompt for LLM
        progress_summary = f"""
课程进度概览：
- 总章节数: {total_nodes}
- 已完成: {completed_nodes} ({progress_percent:.1f}%)
- 薄弱环节数: {len(weak_points)}
- 学习目标: {target_goal or '系统学习'}
- 每日可用时间: {available_time} 分钟

详细进度：
{json.dumps(progress_data[:20], ensure_ascii=False, indent=2)}

薄弱环节：
{json.dumps(weak_points, ensure_ascii=False, indent=2)}

课程结构：
{json.dumps([{"id": n.get('node_id'), "name": n.get('node_name'), "level": n.get('node_level')} for n in all_nodes[:30]], ensure_ascii=False, indent=2)}
"""
        
        prompt_template = get_prompt("generate_learning_path")
        system_prompt = prompt_template.format(
            course_id=course_id,
            progress_summary=progress_summary,
            target_goal=target_goal or "系统学习",
            available_time=available_time
        )
        
        user_prompt = f"""基于以下学习数据，生成个性化学习路径推荐：

{progress_summary}

请生成包含以下内容的JSON格式推荐：
1. recommendations: 推荐学习项列表（按优先级排序）
2. daily_study_plan: 每日学习计划
3. estimated_completion_time: 预计完成时间"""
        
        response = await self._call_llm(user_prompt, system_prompt)
        
        if response:
            result = self._extract_json(response)
            if result and isinstance(result, dict):
                # Merge with calculated data
                result['weak_points'] = weak_points
                result['overall_progress_percent'] = round(progress_percent, 1)
                return result
        
        # Fallback: Generate basic recommendations
        return self._generate_fallback_learning_path(
            progress_data, weak_points, all_nodes, available_time, progress_percent
        )
    
    def _generate_fallback_learning_path(
        self,
        progress_data: List[Dict],
        weak_points: List[Dict],
        all_nodes: List[Dict],
        available_time: int,
        progress_percent: float
    ) -> Dict:
        """
        生成回退学习路径

        当LLM生成失败时，基于简单规则生成基础学习路径。
        优先级：复习薄弱点 > 学习新内容 > 巩固已学内容

        Args:
            progress_data: 学习进度数据
            weak_points: 薄弱环节列表
            all_nodes: 所有节点
            available_time: 可用时间
            progress_percent: 总体进度百分比

        Returns:
            包含推荐项、每日计划和预计完成时间的字典
        """
        recommendations = []
        node_map = {n.get('node_id'): n for n in all_nodes}
        progress_map = {p.get('node_id'): p for p in progress_data}
        
        # Priority 1: Review weak points
        for wp in weak_points[:3]:
            recommendations.append({
                "type": "review",
                "node_id": wp['node_id'],
                "node_name": wp['node_name'],
                "reason": f"薄弱环节: {wp['weakness_type']}",
                "priority": 10,
                "estimated_time_minutes": min(available_time // 2, 20)
            })
        
        # Priority 2: Continue with unread nodes
        unread_nodes = [n for n in all_nodes 
                       if not progress_map.get(n.get('node_id'), {}).get('is_read', False)]
        
        for i, node in enumerate(unread_nodes[:5]):
            recommendations.append({
                "type": "next_topic",
                "node_id": node.get('node_id'),
                "node_name": node.get('node_name'),
                "reason": "继续学习新内容" if i == 0 else "系统性学习",
                "priority": 8 - i,
                "estimated_time_minutes": min(available_time // 3, 15)
            })
        
        # Priority 3: Practice if many weak points
        if len(weak_points) >= 2:
            recommendations.append({
                "type": "practice",
                "node_id": "quiz_review",
                "node_name": "错题重练",
                "reason": "巩固薄弱环节",
                "priority": 7,
                "estimated_time_minutes": min(available_time // 4, 10)
            })
        
        # Sort by priority
        recommendations.sort(key=lambda x: x['priority'], reverse=True)
        
        # Generate daily study plan
        daily_plan = []
        remaining_time = available_time
        
        for rec in recommendations[:5]:
            if remaining_time >= rec['estimated_time_minutes']:
                daily_plan.append({
                    "task": f"{rec['node_name']} ({rec['type']})",
                    "duration_minutes": rec['estimated_time_minutes'],
                    "node_id": rec['node_id']
                })
                remaining_time -= rec['estimated_time_minutes']
        
        # Estimate completion
        remaining_nodes = len(unread_nodes)
        days_needed = max(1, remaining_nodes * 15 // available_time)
        
        return {
            "recommendations": recommendations[:8],
            "weak_points": weak_points,
            "overall_progress_percent": round(progress_percent, 1),
            "estimated_completion_time": f"约 {days_needed} 天" if days_needed < 30 else "约 1 个月+",
            "daily_study_plan": daily_plan
        }
    
    # ==================== 知识掌握度分析方法 ====================

    async def analyze_knowledge_mastery(
        self,
        course_id: str,
        progress_data: List[Dict],
        quiz_history: List[Dict],
        all_nodes: List[Dict]
    ) -> List[Dict]:
        """
        分析知识掌握度

        基于学习进度、阅读时长、测验成绩和笔记数量计算每个节点的掌握度。
        掌握度计算公式：阅读(0.3) + 阅读时长(0.1-0.2) + 测验(0.4) + 笔记(0.1)

        Args:
            course_id: 课程ID
            progress_data: 学习进度数据
            quiz_history: 测验历史记录
            all_nodes: 所有课程节点

        Returns:
            知识点掌握度数据列表
        """
        mastery_data = []
        progress_map = {p.get('node_id'): p for p in progress_data}
        
        for node in all_nodes:
            node_id = node.get('node_id')
            node_name = node.get('node_name', 'Unknown')
            progress = progress_map.get(node_id, {})
            
            # Calculate mastery level
            mastery_level = 0.0
            
            if progress.get('is_read', False):
                mastery_level += 0.3  # Base for reading
                
                # Add for reading time
                read_time = progress.get('read_time_minutes', 0)
                if read_time >= 10:
                    mastery_level += 0.2
                elif read_time >= 5:
                    mastery_level += 0.1
                
                # Add for quiz score
                quiz_score = progress.get('quiz_score')
                if quiz_score is not None:
                    mastery_level += (quiz_score / 100) * 0.4
                
                # Add for notes
                if progress.get('notes_count', 0) > 0:
                    mastery_level += 0.1
            
            # Cap at 1.0
            mastery_level = min(1.0, mastery_level)
            
            # Determine label
            if mastery_level >= 0.9:
                label = "精通"
            elif mastery_level >= 0.7:
                label = "掌握"
            elif mastery_level >= 0.4:
                label = "熟悉"
            elif mastery_level >= 0.1:
                label = "初学"
            else:
                label = "未开始"
            
            mastery_data.append({
                "node_id": node_id,
                "node_name": node_name,
                "mastery_level": round(mastery_level, 2),
                "mastery_label": label,
                "last_tested": progress.get('last_accessed')
            })
        
        return mastery_data


    # ==================== 间隔重复算法方法 ====================

    def calculate_next_review(self, review_count: int, ease_factor: float, quality: int) -> tuple:
        """
        SM-2算法实现 - 计算下一次复习间隔

        基于SuperMemo SM-2算法计算最优复习间隔。
        根据答题质量调整简易度因子和复习间隔。

        间隔规则：
        - 第1次：1天
        - 第2次：6天
        - 第3次+：间隔 × 简易度因子

        Args:
            review_count: 已复习次数
            ease_factor: 简易度因子 (通常2.5)
            quality: 质量评分 (0-5)

        Returns:
            (interval_days, new_ease_factor, new_review_count)
        """
        # 根据质量评分调整简易度因子
        new_ease_factor = ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
        new_ease_factor = max(1.3, new_ease_factor)  # 最小值为1.3
        
        # 计算间隔天数
        if quality < 3:
            # 如果回答错误，重置间隔
            new_review_count = 0
            interval_days = 1
        else:
            new_review_count = review_count + 1
            
            if new_review_count == 1:
                interval_days = 1
            elif new_review_count == 2:
                interval_days = 6
            else:
                interval_days = int((review_count) * ease_factor)
        
        # 添加一些随机性，避免复习堆叠
        import random
        jitter = random.uniform(0.9, 1.1)
        interval_days = max(1, int(interval_days * jitter))
        
        return interval_days, new_ease_factor, new_review_count
    
    def calculate_retention_rate(self, days_since_review: int, ease_factor: float) -> float:
        """
        计算记忆保留率（艾宾浩斯遗忘曲线）

        使用指数衰减模型计算记忆保留率。
        公式：R = e^(-t/S)，其中 S 是记忆强度，与 ease_factor 相关。

        Args:
            days_since_review: 距离上次复习的天数
            ease_factor: 简易度因子

        Returns:
            记忆保留率 (0.0-1.0)
        """
        import math
        if days_since_review <= 0:
            return 1.0
        
        # 记忆强度与简易度因子成正比
        memory_strength = ease_factor * 2  # 基础记忆强度
        retention = math.exp(-days_since_review / memory_strength)
        return min(1.0, max(0.0, retention))
    
    async def generate_review_schedule(
        self,
        course_id: str,
        course_data: dict,
        max_items: int = 20,
        focus_on_weak: bool = True
    ) -> dict:
        """
        生成智能复习计划

        基于SM-2算法和艾宾浩斯遗忘曲线生成个性化复习计划。
        根据测验成绩、复习历史和记忆保留率确定复习优先级。

        Args:
            course_id: 课程ID
            course_data: 课程数据，包含节点和复习历史
            max_items: 最大复习项数量
            focus_on_weak: 是否重点关注薄弱环节

        Returns:
            包含复习项列表、统计数据和预计时间的字典
        """
        from datetime import datetime, timedelta
        
        nodes = course_data.get("nodes", [])
        review_items = []
        now = datetime.now()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # 加载复习历史（如果存在）
        review_history = course_data.get("review_history", {})
        
        for node in nodes:
            node_id = node.get("node_id")
            node_name = node.get("node_name", "Unknown")
            node_content = node.get("node_content", "")
            quiz_score = node.get("quiz_score")
            
            # 获取或初始化复习数据
            node_review = review_history.get(node_id, {
                "review_count": 0,
                "ease_factor": 2.5,
                "last_reviewed": None,
                "next_review": None
            })
            
            # 确定优先级
            priority = "medium"
            if quiz_score is not None:
                if quiz_score < 60:
                    priority = "high"
                elif quiz_score >= 80:
                    priority = "low"
            
            # 如果没有复习历史或从未复习过
            if node_review.get("last_reviewed") is None:
                # 新节点或从未复习的节点
                if quiz_score is not None or node.get("is_read", False):
                    # 已学习但未复习
                    next_review = today
                    status = "due"
                else:
                    continue  # 跳过未学习的节点
            else:
                last_reviewed = datetime.fromisoformat(node_review["last_reviewed"])
                next_review = datetime.fromisoformat(node_review["next_review"]) if node_review.get("next_review") else last_reviewed + timedelta(days=1)
                
                # 确定状态
                if next_review.date() < today.date():
                    status = "overdue"
                    priority = "high"  # 逾期项目提升优先级
                elif next_review.date() == today.date():
                    status = "due"
                else:
                    status = "scheduled"
                    continue  # 跳过未到期的项目
            
            # 计算记忆保留率
            if node_review.get("last_reviewed"):
                days_since = (now - datetime.fromisoformat(node_review["last_reviewed"])).days
                retention = self.calculate_retention_rate(days_since, node_review.get("ease_factor", 2.5))
            else:
                retention = 0.5  # 新内容假设50%保留率
            
            # 如果是弱项且需要重点关注
            if focus_on_weak and quiz_score is not None and quiz_score < 60:
                priority = "high"
                # 提前安排复习
                if status == "scheduled":
                    status = "due"
                    next_review = today
            
            review_items.append({
                "node_id": node_id,
                "node_name": node_name,
                "node_content": node_content[:500] if node_content else "",  # 限制内容长度
                "quiz_score": quiz_score,
                "last_reviewed": node_review.get("last_reviewed"),
                "next_review": next_review.isoformat() if isinstance(next_review, datetime) else next_review,
                "review_count": node_review.get("review_count", 0),
                "interval_days": node_review.get("interval_days", 1),
                "ease_factor": node_review.get("ease_factor", 2.5),
                "priority": priority,
                "status": status,
                "retention_rate": round(retention, 2)
            })
        
        # 按优先级和到期时间排序
        priority_order = {"high": 0, "medium": 1, "low": 2}
        review_items.sort(key=lambda x: (priority_order.get(x["priority"], 1), x["next_review"]))
        
        # 限制数量
        selected_items = review_items[:max_items]
        
        # 计算统计数据
        due_today = sum(1 for item in review_items if item["status"] == "due")
        overdue = sum(1 for item in review_items if item["status"] == "overdue")
        completed_today = sum(1 for item in review_items 
                             if item.get("last_reviewed") and 
                             datetime.fromisoformat(item["last_reviewed"]).date() == today.date())
        
        # 计算平均保留率
        avg_retention = sum(item.get("retention_rate", 0.5) for item in review_items) / len(review_items) if review_items else 0
        
        # 计算连续学习天数（简化版）
        streak_days = course_data.get("learning_streak", 0)
        
        stats = {
            "total_items": len(nodes),
            "due_today": due_today,
            "overdue": overdue,
            "completed_today": completed_today,
            "streak_days": streak_days,
            "retention_rate": round(avg_retention, 2)
        }
        
        # 估算所需时间（每题约2-3分钟）
        estimated_time = len(selected_items) * 3
        
        return {
            "items": selected_items,
            "stats": stats,
            "estimated_time_minutes": estimated_time
        }
    
    async def submit_review_results(
        self,
        course_id: str,
        course_data: dict,
        results: list
    ) -> dict:
        """
        提交复习结果并更新复习计划

        使用SM-2算法更新复习间隔和简易度因子。
        根据答题质量（0-5分）调整下一次复习时间。

        Args:
            course_id: 课程ID
            course_data: 课程数据
            results: 复习结果列表，每项包含node_id和quality

        Returns:
            更新后的复习统计数据
        """
        from datetime import datetime
        
        review_history = course_data.get("review_history", {})
        now = datetime.now()
        
        updated_count = 0
        correct_count = 0
        
        for result in results:
            node_id = result.get("node_id")
            quality = result.get("quality", 3)
            
            # 获取现有复习数据
            node_review = review_history.get(node_id, {
                "review_count": 0,
                "ease_factor": 2.5,
                "last_reviewed": None,
                "next_review": None,
                "total_reviews": 0,
                "correct_count": 0
            })
            
            # 使用SM-2算法计算新间隔
            interval_days, new_ease_factor, new_review_count = self.calculate_next_review(
                node_review.get("review_count", 0),
                node_review.get("ease_factor", 2.5),
                quality
            )
            
            # 更新复习数据
            next_review = now + timedelta(days=interval_days)
            
            review_history[node_id] = {
                "review_count": new_review_count,
                "ease_factor": new_ease_factor,
                "last_reviewed": now.isoformat(),
                "next_review": next_review.isoformat(),
                "interval_days": interval_days,
                "total_reviews": node_review.get("total_reviews", 0) + 1,
                "correct_count": node_review.get("correct_count", 0) + (1 if quality >= 3 else 0),
                "last_quality": quality
            }
            
            updated_count += 1
            if quality >= 3:
                correct_count += 1
        
        # 更新课程数据
        course_data["review_history"] = review_history
        course_data["last_review_date"] = now.isoformat()
        
        # 更新连续学习天数
        last_study_date = course_data.get("last_study_date")
        if last_study_date:
            last_date = datetime.fromisoformat(last_study_date).date()
            today = now.date()
            if (today - last_date).days == 1:
                course_data["learning_streak"] = course_data.get("learning_streak", 0) + 1
            elif (today - last_date).days > 1:
                course_data["learning_streak"] = 1
        else:
            course_data["learning_streak"] = 1
        
        course_data["last_study_date"] = now.isoformat()
        
        accuracy = correct_count / len(results) if results else 0
        
        return {
            "updated_count": updated_count,
            "accuracy": round(accuracy, 2),
            "next_review_date": (now + timedelta(days=1)).isoformat()
        }
    
    async def get_review_progress(self, course_id: str, course_data: dict) -> dict:
        """
        获取复习进度和记忆曲线数据

        生成过去30天的记忆曲线、薄弱节点分析和掌握度趋势。

        Args:
            course_id: 课程ID
            course_data: 课程数据，包含复习历史和节点信息

        Returns:
            包含记忆曲线、复习统计、薄弱节点和掌握度趋势的字典
        """
        from datetime import datetime, timedelta
        import math
        
        review_history = course_data.get("review_history", {})
        nodes = course_data.get("nodes", [])
        
        # 生成记忆曲线数据（过去30天）
        memory_curve = []
        now = datetime.now()
        
        for day_offset in range(-29, 1):
            date = now + timedelta(days=day_offset)
            date_str = date.strftime("%Y-%m-%d")
            
            # 统计当天的复习次数
            review_count = sum(1 for h in review_history.values() 
                             if h.get("last_reviewed") and 
                             datetime.fromisoformat(h["last_reviewed"]).strftime("%Y-%m-%d") == date_str)
            
            # 计算平均保留率
            total_retention = 0
            retention_count = 0
            
            for node_id, history in review_history.items():
                if history.get("last_reviewed"):
                    last_reviewed = datetime.fromisoformat(history["last_reviewed"])
                    days_since = (date - last_reviewed).days
                    if days_since >= 0:
                        ease_factor = history.get("ease_factor", 2.5)
                        retention = self.calculate_retention_rate(days_since, ease_factor)
                        total_retention += retention
                        retention_count += 1
            
            avg_retention = total_retention / retention_count if retention_count > 0 else 0.5
            
            memory_curve.append({
                "day": day_offset,
                "date": date_str,
                "retention": round(avg_retention, 2),
                "review_count": review_count
            })
        
        # 找出薄弱节点
        weak_nodes = []
        for node in nodes:
            node_id = node.get("node_id")
            quiz_score = node.get("quiz_score")
            
            if quiz_score is not None and quiz_score < 60:
                history = review_history.get(node_id, {})
                weak_nodes.append({
                    "node_id": node_id,
                    "node_name": node.get("node_name"),
                    "quiz_score": quiz_score,
                    "review_count": history.get("review_count", 0),
                    "ease_factor": history.get("ease_factor", 2.5)
                })
        
        # 按测验分数排序
        weak_nodes.sort(key=lambda x: x["quiz_score"])
        
        # 计算掌握度趋势
        mastery_trend = []
        for day_offset in range(-6, 1):
            date = now + timedelta(days=day_offset)
            date_str = date.strftime("%Y-%m-%d")
            
            # 计算当天掌握度
            total_mastery = 0
            mastery_count = 0
            
            for node in nodes:
                node_id = node.get("node_id")
                quiz_score = node.get("quiz_score")
                history = review_history.get(node_id, {})
                
                if quiz_score is not None:
                    # 基于测验分数和复习次数计算掌握度
                    base_mastery = quiz_score / 100
                    review_bonus = min(0.2, history.get("review_count", 0) * 0.05)
                    mastery = min(1.0, base_mastery + review_bonus)
                    
                    total_mastery += mastery
                    mastery_count += 1
            
            avg_mastery = total_mastery / mastery_count if mastery_count > 0 else 0
            
            mastery_trend.append({
                "date": date_str,
                "mastery": round(avg_mastery, 2)
            })
        
        # 总复习次数
        total_reviews = sum(h.get("total_reviews", 0) for h in review_history.values())
        
        # 平均保留率
        avg_retention = sum(day["retention"] for day in memory_curve) / len(memory_curve) if memory_curve else 0
        
        return {
            "memory_curve": memory_curve,
            "total_reviews": total_reviews,
            "average_retention": round(avg_retention, 2),
            "weak_nodes": weak_nodes[:10],  # 只返回前10个
            "mastery_trend": mastery_trend
        }


    # ==================== 图表生成方法 ====================

    async def generate_diagram(
        self,
        description: str,
        diagram_type: str = "flowchart",
        context: str = ""
    ) -> Dict[str, Any]:
        """
        生成 Mermaid 图表

        基于用户描述生成各种类型的 Mermaid 图表代码。
        支持流程图、时序图、类图等多种图表类型。

        Args:
            description: 图表描述
            diagram_type: 图表类型 (flowchart, sequenceDiagram, classDiagram 等)
            context: 额外上下文信息

        Returns:
            包含生成的 Mermaid 代码和元数据的字典
        """
        from prompts import get_prompt
        
        prompt_template = get_prompt("generate_diagram")
        system_prompt = prompt_template.format(
            description=description,
            diagram_type=diagram_type,
            context=context or "无额外上下文"
        )
        
        user_prompt = f"""请根据以下描述生成一个 {diagram_type} 类型的 Mermaid 图表：

描述：{description}

{context if context else ""}

请只返回 Mermaid 代码块，不要包含任何解释。"""
        
        try:
            response = await self._call_llm(user_prompt, system_prompt)
            
            if not response:
                return {
                    "success": False,
                    "error": "AI服务未返回响应",
                    "diagram_code": None
                }
            
            # Extract Mermaid code from response
            diagram_code = self._extract_mermaid_code(response)
            
            if not diagram_code:
                return {
                    "success": False,
                    "error": "无法从AI响应中提取有效的Mermaid代码",
                    "raw_response": response[:500] if response else None
                }
            
            # Clean up the diagram code
            diagram_code = self._clean_mermaid_syntax(diagram_code)
            
            return {
                "success": True,
                "diagram_code": diagram_code,
                "diagram_type": diagram_type,
                "description": description
            }
            
        except Exception as e:
            logger.error(f"Error generating diagram: {e}")
            return {
                "success": False,
                "error": f"生成图表时出错: {str(e)}",
                "diagram_code": None
            }
    
    def _extract_mermaid_code(self, response: str) -> Optional[str]:
        """
        从 AI 响应中提取 Mermaid 代码

        支持多种代码块格式和直接图表语法识别。

        Args:
            response: AI 响应文本

        Returns:
            提取的 Mermaid 代码，如果未找到则返回 None
        """
        import re
        
        # Try to find code block with mermaid
        patterns = [
            r'```mermaid\s*\n(.*?)```',
            r'```\s*\n(graph|flowchart|sequenceDiagram|classDiagram|stateDiagram|erDiagram|gantt|pie|mindmap)\s+(.*?)```',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, response, re.DOTALL | re.IGNORECASE)
            if match:
                code = match.group(0)
                # Remove the ```mermaid and ``` markers
                code = re.sub(r'^```mermaid\s*\n', '', code, flags=re.IGNORECASE)
                code = re.sub(r'```\s*$', '', code)
                return code.strip()
        
        # If no code block found, check if response starts with graph or other diagram keywords
        lines = response.strip().split('\n')
        diagram_keywords = ['graph ', 'flowchart ', 'sequenceDiagram', 'classDiagram', 
                           'stateDiagram', 'erDiagram', 'gantt', 'pie ', 'mindmap']
        
        for i, line in enumerate(lines):
            stripped = line.strip().lower()
            if any(stripped.startswith(kw.lower()) for kw in diagram_keywords):
                # Found the start of diagram code
                return '\n'.join(lines[i:]).strip()
        
        return None
    
    def _clean_mermaid_syntax(self, code: str) -> str:
        """
        清理和修复常见的 Mermaid 语法问题

        处理特殊字符、HTML 标签、箭头格式等常见问题。

        Args:
            code: 原始 Mermaid 代码

        Returns:
            清理后的 Mermaid 代码
        """
        import re
        
        # Remove any markdown formatting that might have been included
        code = re.sub(r'^```.*\n?', '', code, flags=re.MULTILINE)
        code = re.sub(r'```\s*$', '', code)
        
        # Fix common issues with node labels
        # Ensure node text with special characters is properly quoted
        def fix_node_labels(match):
            node_id = match.group(1)
            node_text = match.group(2)
            brackets = match.group(3)
            
            # If text already has quotes, keep them
            if node_text.startswith('"') and node_text.endswith('"'):
                return f'{node_id}[{node_text}]'
            
            # If text has special characters, wrap in quotes
            if any(c in node_text for c in ['[', ']', '(', ')', '{', '}', '|', '"', ',', ';']):
                # Escape any existing double quotes
                node_text = node_text.replace('"', '\\"')
                return f'{node_id}["{node_text}"]'
            
            return match.group(0)
        
        # Fix square bracket nodes
        code = re.sub(r'(\w+)\[(.+?)\](\[|\(|\{)', fix_node_labels, code)
        
        # Remove any HTML tags that might break rendering
        code = re.sub(r'<[^>]+>', '', code)
        
        # Fix arrow spacing
        code = re.sub(r'--\s*>', '-->', code)
        code = re.sub(r'<-\s*--', '<--', code)
        code = re.sub(r'==\s*>', '==>', code)
        
        return code.strip()


ai_service = AIService()
