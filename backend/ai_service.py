"""
AI 服务门面模块 (Facade)

向后兼容的聚合类，通过多重继承将所有 AI 子服务组合为单一接口。
现有调用方（main.py、task_manager.py 等）无需修改。

子服务模块：
- ai_base.py: 基础 LLM 调用层（AsyncOpenAI 客户端、JSON 提取、文本清理等）
- course_service.py: 课程生成、节点内容、子节点生成（不挂在本门面）
- ai_qa_service.py: 问答、聊天摘要、苏格拉底辅导
- ai_learning_service.py: 学习路径、复习调度（SM-2）、知识掌握度
- ai_diagram_service.py: 图表生成
"""

from ai_qa_service import AIQAService
from ai_learning_service import AILearningService
from ai_diagram_service import AIDiagramService
from ai_profile_service import AIProfileService


class AIService(AIQAService, AILearningService, AIDiagramService, AIProfileService):
    """非课程 AI 服务门面；课程生成统一走 course_service.CourseService。"""
    pass


# 模块级单例，保持与原有代码的兼容性
ai_service = AIService()
