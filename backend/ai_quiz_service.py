"""
AI 测验服务模块

负责测验题目生成、题目验证、智能回退生成、
测验表现分析和学习建议生成。
"""

import logging
from typing import List, Dict, Optional

from ai_base import AIBase
from shared.prompt_config import DIFFICULTY_LEVELS, TEACHING_STYLES, DifficultyLevel, TeachingStyle
from prompts import get_prompt, get_difficulty_config, get_style_config, get_quiz_discipline_config, get_quiz_difficulty_constraints

logger = logging.getLogger(__name__)


class AIQuizService(AIBase):
    """测验生成与分析相关的 AI 服务"""

    async def generate_quiz(
        self,
        content: str,
        node_name: str = "",
        difficulty: DifficultyLevel = DIFFICULTY_LEVELS["INTERMEDIATE"],
        style: TeachingStyle = TEACHING_STYLES["ACADEMIC"],
        user_persona: str = "",
        question_count: int = 3,
        quiz_type: str = "mixed",
        previous_mistakes: List[Dict] = None,
        discipline_type: str = None
    ) -> List[Dict]:
        """
        增强版测验生成 - 支持多种题型和自适应难度
        """
        system_prompt = get_prompt("generate_quiz").format(
            difficulty=difficulty,
            style=style,
            question_count=question_count,
            discipline_type=discipline_type or "natural_science",
            difficulty_config_text=get_difficulty_config(difficulty),
            style_config_text=get_style_config(style),
            quiz_discipline_config=get_quiz_discipline_config(discipline_type)
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
        
        # 出题专用难度约束
        quiz_difficulty_text = get_quiz_difficulty_constraints(difficulty)
        
        prompt = f"""以下是课程内容，请仔细阅读后基于内容出题：

---
{content_text}
---
{personalization}
{mistake_focus}

{quiz_difficulty_text}

题型要求：{type_distribution.get(quiz_type, type_distribution['mixed'])}

请严格基于以上课程内容，并严格遵守上述难度约束，生成恰好 {question_count} 道选择题。
直接输出 JSON 数组，不要输出任何其他文字。
"""
        
        result = await self._generate_quiz_with_retry(prompt, system_prompt, question_count)
        if result:
            return result

        # 智能回退：基于用户错题生成针对性题目
        logger.warning(f"Quiz generation failed for '{node_name}' after retries. Using smart fallback.")
        return self._generate_smart_fallback_quiz(node_name, question_count, previous_mistakes, discipline_type)
    
    async def _generate_quiz_with_retry(self, prompt: str, system_prompt: str, question_count: int, max_attempts: int = 2) -> Optional[List[Dict]]:
        """尝试生成测验，JSON 解析失败时自动重试一次"""
        last_raw_response = None
        
        for attempt in range(max_attempts):
            if attempt == 0:
                current_prompt = prompt
            else:
                # 第二次尝试：把上次的原始输出发回去，让 LLM 修正格式
                logger.info(f"Quiz JSON parse failed, retrying with format correction (attempt {attempt + 1})")
                current_prompt = f"""你上次的输出无法被解析为有效 JSON。请修正格式后重新输出。

上次的输出：
{last_raw_response[:2000]}

要求：
1. 只输出一个 JSON 数组 [...]
2. 不要用 {{"questions": [...]}} 包装
3. 不要输出任何解释文字
4. 确保字符串中没有未转义的特殊字符
"""
            
            response = await self._call_llm(current_prompt, system_prompt)
            if not response:
                logger.warning(f"Empty LLM response on quiz attempt {attempt + 1}")
                continue
            
            last_raw_response = response
            result = self._extract_json(response)
            
            if result:
                # 解包 dict wrapper
                if isinstance(result, dict):
                    for key in ("questions", "quiz", "data", "items"):
                        if key in result and isinstance(result[key], list):
                            result = result[key]
                            break
                    else:
                        if "question" in result:
                            result = [result]
                        else:
                            vals = list(result.values())
                            result = vals[0] if vals and isinstance(vals[0], list) else []
                
                if isinstance(result, list) and len(result) > 0:
                    validated_quiz = self._validate_quiz_questions(result, question_count)
                    if validated_quiz:
                        logger.info(f"Quiz generated successfully on attempt {attempt + 1}: {len(validated_quiz)} questions")
                        return validated_quiz
            
            logger.warning(f"Quiz attempt {attempt + 1} failed: JSON extraction returned {type(result).__name__}")
        
        return None
    
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
    
    def _generate_smart_fallback_quiz(self, node_name: str, question_count: int, previous_mistakes: List[Dict] = None, discipline_type: str = None) -> List[Dict]:
        """智能回退测验生成 - 基于错题记录和学科类型"""
        fallback_topic = node_name if node_name else "此主题"
        
        # 基础通用题目模板（discipline_type 为 None 时使用）
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
        
        # 自然科学学科专用回退题目
        natural_science_questions = [
            {
                "id": 1, "type": "conceptual",
                "question": f"关于「{fallback_topic}」的核心定义，以下哪个描述最准确？",
                "options": [f"{fallback_topic}是一个纯理论概念，没有实际应用", f"{fallback_topic}是该领域的基础概念，具有严格的数学/科学定义", f"{fallback_topic}是一个已被淘汰的过时理论", f"{fallback_topic}仅适用于极端条件下的特殊情况"],
                "correct_index": 1, "explanation": f"**解析**：{fallback_topic}作为自然科学的核心概念，具有严格的定义和广泛的应用基础。", "knowledge_point": f"{fallback_topic}的核心定义", "difficulty_score": 2
            },
            {
                "id": 2, "type": "conceptual",
                "question": f"「{fallback_topic}」与相关概念之间的关系，以下说法正确的是？",
                "options": ["它们之间完全独立，互不影响", "它们之间存在严格的逻辑推导关系", "它们之间仅有历史渊源，无逻辑联系", "它们之间的关系尚未被科学界认可"],
                "correct_index": 1, "explanation": f"**解析**：在自然科学体系中，{fallback_topic}与相关概念之间通常存在严格的逻辑推导和数学关系。", "knowledge_point": f"{fallback_topic}的概念关系", "difficulty_score": 2
            },
            {
                "id": 3, "type": "application",
                "question": f"在工程或科研实践中，「{fallback_topic}」最常用于解决什么类型的问题？",
                "options": ["文献综述和历史考证", "定量分析和模型构建", "主观评价和审美判断", "社会调查和问卷设计"],
                "correct_index": 1, "explanation": f"**解析**：{fallback_topic}在工程和科研中主要用于定量分析、模型构建和问题求解。", "knowledge_point": f"{fallback_topic}的工程应用", "difficulty_score": 3
            },
            {
                "id": 4, "type": "application",
                "question": f"如果需要验证「{fallback_topic}」的正确性，最合适的方法是？",
                "options": ["专家投票表决", "实验验证或数学证明", "网络搜索热度", "历史文献引用次数"],
                "correct_index": 1, "explanation": f"**解析**：自然科学的核心方法论是通过实验验证或严格的数学证明来确认理论的正确性。", "knowledge_point": f"{fallback_topic}的验证方法", "difficulty_score": 3
            },
            {
                "id": 5, "type": "analysis",
                "question": f"学习「{fallback_topic}」时，以下哪种学习策略最有效？",
                "options": ["死记硬背所有公式和定义", "理解推导过程并通过例题练习巩固", "只看结论不关心推导过程", "仅阅读科普文章了解大意"],
                "correct_index": 1, "explanation": f"**解析**：对于自然科学概念，理解推导过程并通过例题练习是最有效的学习方法。", "knowledge_point": f"{fallback_topic}的学习方法", "difficulty_score": 2
            }
        ]
        
        # 人文学科专用回退题目
        humanities_questions = [
            {
                "id": 1, "type": "conceptual",
                "question": f"关于「{fallback_topic}」的概念界定，以下哪种理解最为准确？",
                "options": [f"{fallback_topic}有唯一确定的标准定义", f"{fallback_topic}的内涵随历史语境和学术传统而有不同诠释", f"{fallback_topic}是一个无法定义的模糊概念", f"{fallback_topic}的定义已被学界完全统一"],
                "correct_index": 1, "explanation": f"**解析**：人文学科中的概念往往具有历史性和语境依赖性，{fallback_topic}的内涵在不同学术传统中有不同的诠释。", "knowledge_point": f"{fallback_topic}的概念界定", "difficulty_score": 2
            },
            {
                "id": 2, "type": "conceptual",
                "question": f"不同学派对「{fallback_topic}」的看法，以下描述正确的是？",
                "options": ["所有学派观点完全一致", "不同学派从各自理论框架出发，提出了不同的分析视角", "学派之间的分歧已经完全消除", "只有一个学派的观点是正确的"],
                "correct_index": 1, "explanation": f"**解析**：人文学科的特点之一是多元视角并存，不同学派对{fallback_topic}的理解反映了各自的理论立场。", "knowledge_point": f"{fallback_topic}的多元视角", "difficulty_score": 3
            },
            {
                "id": 3, "type": "application",
                "question": f"将「{fallback_topic}」的理论应用于当代社会分析时，最需要注意什么？",
                "options": ["直接套用原始理论，无需调整", "考虑历史语境差异，进行批判性转化", "完全抛弃原始理论，重新构建", "忽略理论背景，只关注实用性"],
                "correct_index": 1, "explanation": f"**解析**：将人文理论应用于当代分析时，需要考虑历史语境的差异，进行批判性的转化和重新诠释。", "knowledge_point": f"{fallback_topic}的当代应用", "difficulty_score": 3
            },
            {
                "id": 4, "type": "application",
                "question": f"研究「{fallback_topic}」时，以下哪种研究方法最为适切？",
                "options": ["纯定量统计分析", "文本分析与诠释学方法", "实验室控制实验", "大规模问卷调查"],
                "correct_index": 1, "explanation": f"**解析**：人文学科研究通常采用文本分析、诠释学等质性研究方法来深入理解概念的内涵。", "knowledge_point": f"{fallback_topic}的研究方法", "difficulty_score": 3
            },
            {
                "id": 5, "type": "analysis",
                "question": f"批判性地审视「{fallback_topic}」时，最重要的思维能力是？",
                "options": ["记忆大量事实和年代", "识别论证中的隐含前提和逻辑结构", "快速阅读大量文献", "精确引用原文"],
                "correct_index": 1, "explanation": f"**解析**：批判性思维的核心是能够识别论证中的隐含前提、分析逻辑结构、评估论据的充分性。", "knowledge_point": f"{fallback_topic}的批判性分析", "difficulty_score": 4
            }
        ]
        
        # 技能学科专用回退题目
        skill_based_questions = [
            {
                "id": 1, "type": "conceptual",
                "question": f"关于「{fallback_topic}」这项技能，以下哪种理解最准确？",
                "options": [f"{fallback_topic}是天生的能力，无法通过训练提升", f"{fallback_topic}是可以通过系统训练和刻意练习掌握的技能", f"{fallback_topic}只需要理论学习，不需要实践", f"{fallback_topic}没有明确的评估标准"],
                "correct_index": 1, "explanation": f"**解析**：{fallback_topic}作为一项技能，可以通过系统的训练方法和持续的刻意练习来逐步提升。", "knowledge_point": f"{fallback_topic}的技能本质", "difficulty_score": 2
            },
            {
                "id": 2, "type": "application",
                "question": f"练习「{fallback_topic}」时，以下哪个步骤顺序最合理？",
                "options": ["直接实战→总结→学习理论", "学习理论→观摩示范→模仿练习→实战应用→反思改进", "只看理论不练习", "随意练习，不需要计划"],
                "correct_index": 1, "explanation": f"**解析**：技能学习的有效路径是：理论理解→示范观摩→模仿练习→实战应用→反思改进的循环过程。", "knowledge_point": f"{fallback_topic}的练习步骤", "difficulty_score": 2
            },
            {
                "id": 3, "type": "application",
                "question": f"在实际场景中运用「{fallback_topic}」时，遇到困难应该怎么做？",
                "options": ["立即放弃，说明不适合", "分析问题原因，调整策略后重新尝试", "完全照搬他人的做法", "降低标准，敷衍了事"],
                "correct_index": 1, "explanation": f"**解析**：技能提升的关键在于遇到困难时能够分析原因、调整策略并持续改进。", "knowledge_point": f"{fallback_topic}的问题解决", "difficulty_score": 3
            },
            {
                "id": 4, "type": "conceptual",
                "question": f"评估「{fallback_topic}」的掌握程度，最可靠的方式是？",
                "options": ["自我感觉良好即可", "通过实际任务表现和他人反馈来评估", "只看理论考试成绩", "与他人比较排名"],
                "correct_index": 1, "explanation": f"**解析**：技能的掌握程度最好通过实际任务中的表现和来自专业人士的反馈来综合评估。", "knowledge_point": f"{fallback_topic}的评估方法", "difficulty_score": 3
            },
            {
                "id": 5, "type": "analysis",
                "question": f"要从「{fallback_topic}」的初学者成长为高手，最关键的因素是？",
                "options": ["天赋决定一切", "持续的刻意练习和及时的反馈调整", "学习时间越长越好", "只需要找到正确的方法论"],
                "correct_index": 1, "explanation": f"**解析**：研究表明，刻意练习（有目标、有反馈、持续改进）是技能精进的最关键因素。", "knowledge_point": f"{fallback_topic}的精进路径", "difficulty_score": 4
            }
        ]
        
        # 根据学科类型选择题目模板
        discipline_question_map = {
            "natural_science": natural_science_questions,
            "humanities": humanities_questions,
            "skill_based": skill_based_questions,
        }
        questions = discipline_question_map.get(discipline_type, base_questions) if discipline_type else base_questions
        
        # 如果有错题记录，优先返回相关类型的题目
        if previous_mistakes and len(previous_mistakes) > 0:
            weak_types = set(m.get('question_type', 'conceptual') for m in previous_mistakes[-5:])
            prioritized = [q for q in questions if q['type'] in weak_types]
            other = [q for q in questions if q['type'] not in weak_types]
            combined = prioritized + other
            return combined[:question_count]
        
        return questions[:question_count]
    
    async def analyze_quiz_performance(
        self,
        quiz_results: List[Dict],
        user_answers: List[int],
        user_id: str = "default"
    ) -> Dict:
        """
        分析测验表现，生成学习建议
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
