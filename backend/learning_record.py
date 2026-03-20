# =============================================================================
# 学习记录模块 - 记录测验反馈和薄弱点（P1 新增）
# =============================================================================

from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
import json
import os


@dataclass
class QuizRecord:
    """单道测验题目的答题记录"""
    question_id: str
    node_name: str  # 所属章节
    knowledge_point: str  # 考察的知识点
    is_correct: bool
    user_answer: int  # 用户选择的选项索引
    correct_answer: int  # 正确答案索引
    timestamp: datetime = field(default_factory=datetime.now)
    time_spent_seconds: int = 0  # 答题耗时（秒）
    hint_used: bool = False  # 是否使用了提示


@dataclass
class NodeLearningRecord:
    """单个章节的学习记录"""
    node_name: str
    quiz_records: List[QuizRecord] = field(default_factory=list)
    total_questions: int = 0
    correct_count: int = 0
    weak_knowledge_points: List[str] = field(default_factory=list)  # 薄弱知识点
    
    def add_quiz_record(self, record: QuizRecord):
        """添加答题记录"""
        self.quiz_records.append(record)
        self.total_questions += 1
        if record.is_correct:
            self.correct_count += 1
        
        # 如果答错，记录薄弱知识点
        if not record.is_correct and record.knowledge_point not in self.weak_knowledge_points:
            self.weak_knowledge_points.append(record.knowledge_point)
    
    @property
    def accuracy_rate(self) -> float:
        """计算正确率"""
        if self.total_questions == 0:
            return 0.0
        return self.correct_count / self.total_questions


@dataclass
class CourseLearningRecord:
    """整门课程的学习记录"""
    course_id: str
    course_name: str
    node_records: Dict[str, NodeLearningRecord] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def get_or_create_node_record(self, node_name: str) -> NodeLearningRecord:
        """获取或创建章节学习记录"""
        if node_name not in self.node_records:
            self.node_records[node_name] = NodeLearningRecord(node_name=node_name)
        return self.node_records[node_name]
    
    def add_quiz_result(
        self,
        node_name: str,
        question_id: str,
        knowledge_point: str,
        is_correct: bool,
        user_answer: int,
        correct_answer: int,
        time_spent_seconds: int = 0,
        hint_used: bool = False
    ):
        """添加测验结果"""
        node_record = self.get_or_create_node_record(node_name)
        quiz_record = QuizRecord(
            question_id=question_id,
            node_name=node_name,
            knowledge_point=knowledge_point,
            is_correct=is_correct,
            user_answer=user_answer,
            correct_answer=correct_answer,
            time_spent_seconds=time_spent_seconds,
            hint_used=hint_used
        )
        node_record.add_quiz_record(quiz_record)
        self.updated_at = datetime.now()
    
    def get_all_weak_points(self) -> List[str]:
        """获取所有章节的薄弱知识点"""
        weak_points = []
        for node_record in self.node_records.values():
            weak_points.extend(node_record.weak_knowledge_points)
        return list(set(weak_points))  # 去重
    
    def get_weak_points_for_node(self, node_name: str) -> List[str]:
        """获取特定章节的薄弱知识点"""
        if node_name in self.node_records:
            return self.node_records[node_name].weak_knowledge_points
        return []
    
    def get_prerequisite_weak_points(self, dependencies: List[str]) -> List[str]:
        """获取前置依赖章节的薄弱知识点（用于前置知识上下文注入）"""
        weak_points = []
        for dep_node in dependencies:
            if dep_node in self.node_records:
                weak_points.extend(self.node_records[dep_node].weak_knowledge_points)
        return list(set(weak_points))


class LearningRecordManager:
    """学习记录管理器 - 单例模式"""
    
    _instance = None
    _records: Dict[str, CourseLearningRecord] = {}
    _storage_path = "data/learning_records.json"
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def get_or_create_course_record(self, course_id: str, course_name: str) -> CourseLearningRecord:
        """获取或创建课程学习记录"""
        if course_id not in self._records:
            self._records[course_id] = CourseLearningRecord(
                course_id=course_id,
                course_name=course_name
            )
        return self._records[course_id]
    
    def add_quiz_result(
        self,
        course_id: str,
        course_name: str,
        node_name: str,
        question_id: str,
        knowledge_point: str,
        is_correct: bool,
        user_answer: int,
        correct_answer: int,
        time_spent_seconds: int = 0,
        hint_used: bool = False
    ):
        """添加测验结果"""
        course_record = self.get_or_create_course_record(course_id, course_name)
        course_record.add_quiz_result(
            node_name=node_name,
            question_id=question_id,
            knowledge_point=knowledge_point,
            is_correct=is_correct,
            user_answer=user_answer,
            correct_answer=correct_answer,
            time_spent_seconds=time_spent_seconds,
            hint_used=hint_used
        )
    
    def get_weak_points(self, course_id: str, node_name: Optional[str] = None) -> List[str]:
        """获取薄弱知识点
        
        Args:
            course_id: 课程 ID
            node_name: 可选，如果指定则只返回该章节的薄弱点，否则返回所有章节的薄弱点
        
        Returns:
            薄弱知识点列表
        """
        if course_id not in self._records:
            return []
        
        course_record = self._records[course_id]
        if node_name:
            return course_record.get_weak_points_for_node(node_name)
        else:
            return course_record.get_all_weak_points()
    
    def get_prerequisite_weak_points(
        self,
        course_id: str,
        dependencies: List[str]
    ) -> List[str]:
        """获取前置依赖章节的薄弱知识点"""
        if course_id not in self._records:
            return []
        
        course_record = self._records[course_id]
        return course_record.get_prerequisite_weak_points(dependencies)
    
    def save_to_file(self):
        """保存学习记录到文件"""
        try:
            os.makedirs(os.path.dirname(self._storage_path), exist_ok=True)
            data = {}
            for course_id, record in self._records.items():
                data[course_id] = {
                    "course_id": record.course_id,
                    "course_name": record.course_name,
                    "created_at": record.created_at.isoformat(),
                    "updated_at": record.updated_at.isoformat(),
                    "node_records": {
                        node_name: {
                            "node_name": nr.node_name,
                            "total_questions": nr.total_questions,
                            "correct_count": nr.correct_count,
                            "weak_knowledge_points": nr.weak_knowledge_points,
                            "quiz_records": [
                                {
                                    "question_id": qr.question_id,
                                    "node_name": qr.node_name,
                                    "knowledge_point": qr.knowledge_point,
                                    "is_correct": qr.is_correct,
                                    "user_answer": qr.user_answer,
                                    "correct_answer": qr.correct_answer,
                                    "timestamp": qr.timestamp.isoformat(),
                                    "time_spent_seconds": qr.time_spent_seconds,
                                    "hint_used": qr.hint_used
                                }
                                for qr in nr.quiz_records
                            ]
                        }
                        for node_name, nr in record.node_records.items()
                    }
                }
            
            with open(self._storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存学习记录失败：{e}")
    
    def load_from_file(self):
        """从文件加载学习记录"""
        try:
            if os.path.exists(self._storage_path):
                with open(self._storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                for course_id, course_data in data.items():
                    record = CourseLearningRecord(
                        course_id=course_data["course_id"],
                        course_name=course_data["course_name"],
                        created_at=datetime.fromisoformat(course_data["created_at"]),
                        updated_at=datetime.fromisoformat(course_data["updated_at"])
                    )
                    
                    for node_name, node_data in course_data["node_records"].items():
                        node_record = NodeLearningRecord(
                            node_name=node_name,
                            total_questions=node_data["total_questions"],
                            correct_count=node_data["correct_count"],
                            weak_knowledge_points=node_data["weak_knowledge_points"]
                        )
                        
                        for qr_data in node_data["quiz_records"]:
                            quiz_record = QuizRecord(
                                question_id=qr_data["question_id"],
                                node_name=qr_data["node_name"],
                                knowledge_point=qr_data["knowledge_point"],
                                is_correct=qr_data["is_correct"],
                                user_answer=qr_data["user_answer"],
                                correct_answer=qr_data["correct_answer"],
                                timestamp=datetime.fromisoformat(qr_data["timestamp"]),
                                time_spent_seconds=qr_data["time_spent_seconds"],
                                hint_used=qr_data["hint_used"]
                            )
                            node_record.quiz_records.append(quiz_record)
                        
                        record.node_records[node_name] = node_record
                    
                    self._records[course_id] = record
        except Exception as e:
            print(f"加载学习记录失败：{e}")


# 全局单例
learning_record_manager = LearningRecordManager()


# =============================================================================
# API 辅助函数
# =============================================================================

def record_quiz_answer(
    course_id: str,
    course_name: str,
    node_name: str,
    question_id: str,
    knowledge_point: str,
    user_answer: int,
    correct_answer: int,
    time_spent_seconds: int = 0,
    hint_used: bool = False
):
    """记录测验答题结果（供 API 调用）"""
    is_correct = (user_answer == correct_answer)
    learning_record_manager.add_quiz_result(
        course_id=course_id,
        course_name=course_name,
        node_name=node_name,
        question_id=question_id,
        knowledge_point=knowledge_point,
        is_correct=is_correct,
        user_answer=user_answer,
        correct_answer=correct_answer,
        time_spent_seconds=time_spent_seconds,
        hint_used=hint_used
    )
    learning_record_manager.save_to_file()


def get_learner_weakness(
    course_id: str,
    dependencies: Optional[List[str]] = None
) -> List[str]:
    """获取学习者薄弱点（供内容生成时注入）
    
    Args:
        course_id: 课程 ID
        dependencies: 可选，前置依赖章节列表。如果提供，则返回这些章节的薄弱点
    
    Returns:
        薄弱知识点列表
    """
    if dependencies:
        return learning_record_manager.get_prerequisite_weak_points(course_id, dependencies)
    else:
        return learning_record_manager.get_weak_points(course_id)
