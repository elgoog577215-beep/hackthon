"""
AI 测验服务模块

负责测验题目生成、题目验证、智能回退生成、
测验表现分析和学习建议生成。
"""

import logging
from typing import List, Dict

from ai_base import AIBase
from shared.prompt_config import DIFFICULTY_LEVELS, TEACHING_STYLES, DifficultyLevel, TeachingStyle
from prompts import get_prompt

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
        previous_mistakes: List[Dict] = None
    ) -> List[Dict]:
        """
        增强版测验生成 - 支持多种题型和自适应难度
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
