"""
AI 服务门面模块 (Facade)

向后兼容的聚合类，通过多重继承将所有 AI 子服务组合为单一接口。
现有调用方（main.py、task_manager.py 等）无需修改。

子服务模块：
- ai_base.py: 基础 LLM 调用层（AsyncOpenAI 客户端、JSON 提取、文本清理等）
- ai_course_service.py: 课程生成、节点内容、子节点生成
- ai_quiz_service.py: 测验生成、成绩分析
- ai_qa_service.py: 问答、聊天摘要、苏格拉底辅导
- ai_graph_service.py: 知识图谱生成与验证
- ai_learning_service.py: 学习路径、复习调度（SM-2）、知识掌握度
- ai_diagram_service.py: 图表生成
"""

from ai_course_service import AICourseService
from ai_quiz_service import AIQuizService
from ai_qa_service import AIQAService
from ai_graph_service import AIGraphService
from ai_learning_service import AILearningService
from ai_diagram_service import AIDiagramService


class AIService(AICourseService, AIQuizService, AIQAService,
                AIGraphService, AILearningService, AIDiagramService):
    """向后兼容的门面类，聚合所有 AI 服务功能"""
    pass


# 模块级单例，保持与原有代码的兼容性
ai_service = AIService()
