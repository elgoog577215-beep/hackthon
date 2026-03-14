
from typing import List, Optional, Literal, Dict
from pydantic import BaseModel, Field
from datetime import datetime
import uuid
import sys
from pathlib import Path

# 添加项目根目录到系统路径以导入共享配置
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
from shared.prompt_config import DifficultyLevel, TeachingStyle

# === 课程相关 ===
class Node(BaseModel):
    node_id: str
    parent_node_id: str
    node_name: str
    node_level: int
    node_content: str = ""
    node_type: Literal["original", "custom", "extend"] = "original"
    create_time: Optional[datetime] = None
    is_read: bool = False
    quiz_score: Optional[int] = None

# === 标注与笔记 ===
class Annotation(BaseModel):
    anno_id: str
    node_id: str
    question: str
    answer: str
    anno_summary: str
    source_type: Literal["internal", "external"] = "internal"
    create_time: datetime = Field(default_factory=datetime.now)

class GenerateCourseRequest(BaseModel):
    keyword: str = Field(..., min_length=1, max_length=200)
    difficulty: Optional[DifficultyLevel] = "intermediate"
    style: Optional[TeachingStyle] = "academic"
    requirements: Optional[str] = Field(default="", max_length=2000)

class GenerateSubNodesRequest(BaseModel):
    node_id: str
    node_name: str
    node_level: int
    difficulty: Optional[DifficultyLevel] = "intermediate"  # beginner, intermediate, advanced
    style: Optional[TeachingStyle] = "academic"  # academic, industrial, socratic, humorous

class RedefineContentRequest(BaseModel):
    node_id: str
    node_name: str
    original_content: str
    user_requirement: str
    course_context: Optional[str] = ""
    previous_context: Optional[str] = ""
    difficulty: Optional[DifficultyLevel] = "advanced"
    style: Optional[TeachingStyle] = "academic"

class ExtendContentRequest(BaseModel):
    node_id: str
    node_name: str
    current_content: str
    user_requirement: str

class AskQuestionRequest(BaseModel):
    course_id: Optional[str] = None
    node_id: str
    node_name: str = Field(..., max_length=500)
    node_content: str = Field(..., max_length=50000)
    question: str = Field(..., min_length=1, max_length=5000)
    history: List[dict] = Field(default=[], max_length=100)
    selection: Optional[str] = Field(default="", max_length=10000)
    user_notes: Optional[str] = Field(default="", max_length=10000)
    user_persona: Optional[str] = Field(default="", max_length=500)
    session_metrics: Optional[dict] = None
    enable_long_term_memory: Optional[bool] = False

# === 节点操作 ===
class AddNodeRequest(BaseModel):
    parent_node_id: str = "root"
    node_name: str = "New Node"

class SaveAnnotationRequest(BaseModel):
    anno_id: Optional[str] = None
    node_id: str
    course_id: Optional[str] = None
    question: str
    answer: str
    anno_summary: str
    source_type: Literal["user", "ai", "user_saved", "wrong", "format"] = "user"
    quote: Optional[str] = None

class UpdateNodeRequest(BaseModel):
    node_name: Optional[str] = None
    node_content: Optional[str] = None
    is_read: Optional[bool] = None
    quiz_score: Optional[int] = None

class SummarizeNodeRequest(BaseModel):
    node_content: str
    node_name: str
    user_persona: Optional[str] = None

class UpdateAnnotationRequest(BaseModel):
    content: str

# === 测验 ===
class GenerateQuizRequest(BaseModel):
    node_content: str
    node_name: Optional[str] = ""
    difficulty: DifficultyLevel = "intermediate"
    style: Optional[TeachingStyle] = "academic"
    user_persona: Optional[str] = ""
    question_count: int = 3
    discipline_type: Optional[str] = None


class SummarizeChatRequest(BaseModel):
    history: List[dict]
    course_context: Optional[str] = ""
    user_persona: Optional[str] = ""

class LocateNodeRequest(BaseModel):
    keyword: str

# === 学习路径与推荐 ===
class LearningProgressData(BaseModel):
    """学习进度数据"""
    node_id: str
    node_name: str
    is_read: bool
    read_time_minutes: int = 0
    quiz_score: Optional[int] = None
    last_accessed: Optional[datetime] = None
    notes_count: int = 0

class WeakPointAnalysis(BaseModel):
    """薄弱环节分析"""
    node_id: str
    node_name: str
    weakness_type: Literal["low_quiz_score", "insufficient_reading", "frequent_wrong_answers"]
    severity: Literal["high", "medium", "low"]
    suggested_action: str

class LearningRecommendation(BaseModel):
    """学习推荐项"""
    type: str  # "next_topic", "review", "practice", "explore"
    node_id: str
    node_name: str
    reason: str
    priority: int  # 1-10, higher is more important
    estimated_time_minutes: int

class LearningPathRequest(BaseModel):
    """学习路径请求"""
    course_id: str
    progress_data: List[LearningProgressData]
    wrong_answer_nodes: List[str] = []  # node_ids where user got wrong answers
    target_goal: Optional[str] = ""  # e.g., "master_basics", "prepare_exam", "deep_dive"
    available_time_minutes: Optional[int] = 30  # daily study time

class LearningPathResponse(BaseModel):
    """学习路径响应"""
    recommendations: List[LearningRecommendation]
    weak_points: List[WeakPointAnalysis]
    overall_progress_percent: float
    estimated_completion_time: str
    daily_study_plan: List[dict]

class KnowledgePointMastery(BaseModel):
    """知识点掌握度"""
    node_id: str
    node_name: str
    mastery_level: float  # 0.0 - 1.0
    mastery_label: str  # "未开始", "初学", "熟悉", "掌握", "精通"
    last_tested: Optional[datetime] = None


# === 复习系统 ===
class ReviewItem(BaseModel):
    """复习项目"""
    node_id: str
    node_name: str
    node_content: str = ""
    quiz_score: Optional[int] = None
    last_reviewed: Optional[datetime] = None
    next_review: datetime
    review_count: int = 0
    interval_days: int = 1
    ease_factor: float = 2.5
    priority: Literal["high", "medium", "low"] = "medium"  # 复习优先级
    status: Literal["due", "completed", "overdue"] = "due"  # 复习状态

class ReviewStats(BaseModel):
    """复习统计数据"""
    total_items: int
    due_today: int
    overdue: int
    completed_today: int
    streak_days: int
    retention_rate: float  # 0.0 - 1.0

class ReviewSession(BaseModel):
    """复习会话"""
    session_id: str
    course_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    items_reviewed: List[str] = []  # node_ids
    correct_count: int = 0
    incorrect_count: int = 0

class ReviewResult(BaseModel):
    """复习结果"""
    node_id: str
    quality: int  # 0-5, SM-2算法质量评分
    time_spent_seconds: int
    notes: Optional[str] = None

class ReviewScheduleRequest(BaseModel):
    """生成复习计划请求"""
    course_id: str
    max_items: int = 20
    focus_on_weak: bool = True

class ReviewScheduleResponse(BaseModel):
    """复习计划响应"""
    items: List[ReviewItem]
    stats: ReviewStats
    estimated_time_minutes: int

class SubmitReviewRequest(BaseModel):
    """提交复习结果请求"""
    course_id: str
    results: List[ReviewResult]

class MemoryCurveData(BaseModel):
    """记忆曲线数据点"""
    day: int
    retention: float  # 0.0 - 1.0
    review_count: int = 0

class ReviewProgressResponse(BaseModel):
    """复习进度响应"""
    memory_curve: List[MemoryCurveData]
    total_reviews: int
    average_retention: float
    weak_nodes: List[dict]
    mastery_trend: List[dict]  # 掌握度趋势


# === 代码执行 ===
class ExecuteCodeRequest(BaseModel):
    """代码执行请求"""
    code: str = Field(..., min_length=1, max_length=5000)
    language: str = Field(default="python", max_length=20)
    timeout: int = Field(default=10, ge=1, le=30)

class ExecuteCodeResponse(BaseModel):
    """代码执行响应"""
    success: bool
    output: str
    error: Optional[str] = None
    execution_time: float  # milliseconds
    language: str

# === 图表 ===
class GenerateDiagramRequest(BaseModel):
    """AI图表生成请求"""
    description: str = Field(..., description="图表描述", min_length=1, max_length=2000)
    diagram_type: str = Field(default="flowchart", description="图表类型")
    context: str = Field(default="", description="额外上下文信息", max_length=1000)

class GenerateDiagramResponse(BaseModel):
    """AI图表生成响应"""
    success: bool = Field(..., description="是否成功")
    diagram_code: Optional[str] = Field(default=None, description="生成的Mermaid代码")
    diagram_type: str = Field(default="flowchart", description="图表类型")
    description: str = Field(default="", description="原始描述")
    error: Optional[str] = Field(default=None, description="错误信息")

# === 知识图谱 ===
class KnowledgeGraphRequest(BaseModel):
    course_id: str

class GenerateKnowledgeGraphRequest(BaseModel):
    course_id: str

# === AI 辅导 ===
class CreateGoalRequest(BaseModel):
    title: str
    description: str
    goal_type: str = "task_oriented"
    target_value: float
    unit: str = "个"
    deadline: Optional[str] = None
    related_nodes: List[str] = []
    priority: int = 1

class UpdateGoalProgressRequest(BaseModel):
    progress_delta: float

class RecordLearningRequest(BaseModel):
    node_id: str
    node_title: str
    is_correct: Optional[bool] = None
    time_spent: float = 0.0
    question_data: Optional[Dict] = None

class SessionSummaryRequest(BaseModel):
    duration: float
    questions_answered: int = 0
    correct_count: int = 0
    nodes_studied: List[str] = []

class TutorContextRequest(BaseModel):
    time_stuck: int = 0
    consecutive_wrong: int = 0
    current_node_id: Optional[str] = None

# === 其他 ===
class ImportMarkdownResponse(BaseModel):
    """Markdown 导入响应"""
    course_id: str
    course_name: str
