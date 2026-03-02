"""
统一智能导师服务
整合记忆系统、Agent能力、主动推送于一体
让AI助手真正像老师一样
"""

import json
import math
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import defaultdict
import logging

from storage import storage

logger = logging.getLogger(__name__)


class GoalType(Enum):
    TIME_ORIENTED = "time_oriented"
    ABILITY_ORIENTED = "ability_oriented"
    TASK_ORIENTED = "task_oriented"
    HABIT_ORIENTED = "habit_oriented"


class GoalStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    PAUSED = "paused"


class MasteryLevel(Enum):
    NOVICE = 0
    BEGINNER = 1
    INTERMEDIATE = 2
    ADVANCED = 3
    EXPERT = 4


@dataclass
class KnowledgeState:
    node_id: str
    node_title: str
    mastery_level: int
    confidence: float
    last_study_time: Optional[datetime] = None
    study_count: int = 0
    correct_rate: float = 0.0
    time_spent: float = 0.0
    forgetting_score: float = 1.0
    wrong_answers: List[Dict] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            'node_id': self.node_id,
            'node_title': self.node_title,
            'mastery_level': self.mastery_level,
            'confidence': self.confidence,
            'last_study_time': self.last_study_time.isoformat() if self.last_study_time else None,
            'study_count': self.study_count,
            'correct_rate': self.correct_rate,
            'time_spent': self.time_spent,
            'forgetting_score': self.forgetting_score,
            'wrong_answers': self.wrong_answers
        }


@dataclass
class LearningGoal:
    id: str
    title: str
    description: str
    goal_type: GoalType
    status: GoalStatus
    target_value: float
    current_value: float
    unit: str
    deadline: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)
    related_nodes: List[str] = field(default_factory=list)
    priority: int = 1

    @property
    def progress_percentage(self) -> float:
        if self.target_value == 0:
            return 100.0
        return min(100.0, (self.current_value / self.target_value) * 100)

    @property
    def is_overdue(self) -> bool:
        if self.deadline is None:
            return False
        return datetime.now() > self.deadline and self.status != GoalStatus.COMPLETED

    @property
    def days_remaining(self) -> Optional[int]:
        if self.deadline is None:
            return None
        delta = self.deadline - datetime.now()
        return max(0, delta.days)

    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'goal_type': self.goal_type.value,
            'status': self.status.value,
            'target_value': self.target_value,
            'current_value': self.current_value,
            'unit': self.unit,
            'progress_percentage': self.progress_percentage,
            'deadline': self.deadline.isoformat() if self.deadline else None,
            'created_at': self.created_at.isoformat(),
            'related_nodes': self.related_nodes,
            'priority': self.priority,
            'is_overdue': self.is_overdue,
            'days_remaining': self.days_remaining
        }


class UnifiedTutorMemory:
    """
    统一导师记忆系统
    整合学习者画像、知识状态、学习目标、错题记录
    """

    def __init__(self):
        self.user_profiles: Dict[str, Dict] = {}
        self.knowledge_states: Dict[str, Dict[str, KnowledgeState]] = defaultdict(dict)
        self.goals: Dict[str, List[LearningGoal]] = defaultdict(list)
        self.wrong_answer_book: Dict[str, List[Dict]] = defaultdict(list)
        self.study_sessions: Dict[str, List[Dict]] = defaultdict(list)
        self._load_from_storage()

    def _load_from_storage(self):
        try:
            data = storage.load_data('tutor_memory.json')
            if data:
                self.user_profiles = data.get('user_profiles', {})
                for user_id, states in data.get('knowledge_states', {}).items():
                    for node_id, state in states.items():
                        self.knowledge_states[user_id][node_id] = KnowledgeState(
                            node_id=state['node_id'],
                            node_title=state['node_title'],
                            mastery_level=state['mastery_level'],
                            confidence=state['confidence'],
                            last_study_time=datetime.fromisoformat(state['last_study_time']) if state.get('last_study_time') else None,
                            study_count=state.get('study_count', 0),
                            correct_rate=state.get('correct_rate', 0.0),
                            time_spent=state.get('time_spent', 0.0),
                            forgetting_score=state.get('forgetting_score', 1.0),
                            wrong_answers=state.get('wrong_answers', [])
                        )
        except Exception as e:
            logger.warning(f"Could not load tutor memory: {e}")

    def _save_to_storage(self):
        try:
            data = {
                'user_profiles': self.user_profiles,
                'knowledge_states': {
                    user_id: {node_id: state.to_dict() for node_id, state in states.items()}
                    for user_id, states in self.knowledge_states.items()
                }
            }
            storage.save_data('tutor_memory.json', data)
        except Exception as e:
            logger.error(f"Could not save tutor memory: {e}")

    def get_or_create_profile(self, user_id: str) -> Dict:
        if user_id not in self.user_profiles:
            self.user_profiles[user_id] = {
                'user_id': user_id,
                'learning_style': 'mixed',
                'preferred_session_length': 30,
                'preferred_difficulty': 'medium',
                'total_study_time': 0.0,
                'total_sessions': 0,
                'streak_days': 0,
                'last_active_date': None,
                'learning_velocity': 1.0,
                'engagement_score': 0.5,
                'interests': [],
                'common_mistakes': []
            }
        return self.user_profiles[user_id]

    def update_knowledge_state(
        self,
        user_id: str,
        node_id: str,
        node_title: str,
        is_correct: Optional[bool] = None,
        time_spent: float = 0.0,
        question_data: Optional[Dict] = None
    ) -> KnowledgeState:
        if node_id not in self.knowledge_states[user_id]:
            self.knowledge_states[user_id][node_id] = KnowledgeState(
                node_id=node_id,
                node_title=node_title,
                mastery_level=0,
                confidence=0.0
            )

        state = self.knowledge_states[user_id][node_id]
        state.study_count += 1
        state.last_study_time = datetime.now()
        state.time_spent += time_spent

        if is_correct is not None:
            total = state.study_count
            correct_count = state.correct_rate * (total - 1)
            if is_correct:
                correct_count += 1
            state.correct_rate = correct_count / total

            if state.correct_rate >= 0.9 and state.study_count >= 5:
                state.mastery_level = 4
            elif state.correct_rate >= 0.75 and state.study_count >= 3:
                state.mastery_level = 3
            elif state.correct_rate >= 0.6 and state.study_count >= 2:
                state.mastery_level = 2
            elif state.correct_rate >= 0.4:
                state.mastery_level = 1

            if not is_correct and question_data:
                state.wrong_answers.append({
                    'question': question_data.get('question', ''),
                    'user_answer': question_data.get('user_answer', ''),
                    'correct_answer': question_data.get('correct_answer', ''),
                    'timestamp': datetime.now().isoformat()
                })
                self._add_to_wrong_book(user_id, node_id, node_title, question_data)

        state.confidence = min(1.0, state.study_count * 0.1 + state.correct_rate * 0.5)
        state.forgetting_score = self._calculate_forgetting_score(state)

        self._save_to_storage()
        return state

    def _calculate_forgetting_score(self, state: KnowledgeState) -> float:
        if state.last_study_time is None:
            return 1.0
        days_since = (datetime.now() - state.last_study_time).days
        stability = 1.0 + state.study_count * 0.1 + state.mastery_level * 0.2
        retention = math.exp(-days_since / stability)
        return max(0.1, retention)

    def _add_to_wrong_book(self, user_id: str, node_id: str, node_title: str, question_data: Dict):
        self.wrong_answer_book[user_id].append({
            'node_id': node_id,
            'node_title': node_title,
            'question': question_data.get('question', ''),
            'user_answer': question_data.get('user_answer', ''),
            'correct_answer': question_data.get('correct_answer', ''),
            'timestamp': datetime.now().isoformat(),
            'reviewed': False
        })

    def record_study_session(self, user_id: str, duration: float, nodes_studied: List[str]):
        profile = self.get_or_create_profile(user_id)
        profile['total_sessions'] += 1
        profile['total_study_time'] += duration

        today = datetime.now().date()
        if profile.get('last_active_date'):
            last = datetime.fromisoformat(profile['last_active_date']).date()
            if today - last == timedelta(days=1):
                profile['streak_days'] += 1
            elif today != last:
                profile['streak_days'] = 1
        else:
            profile['streak_days'] = 1

        profile['last_active_date'] = datetime.now().isoformat()

        self.study_sessions[user_id].append({
            'date': datetime.now().isoformat(),
            'duration': duration,
            'nodes': nodes_studied
        })

        self._save_to_storage()

    def get_weaknesses(self, user_id: str) -> List[Dict]:
        states = self.knowledge_states.get(user_id, {})
        weaknesses = []
        for state in states.values():
            if state.correct_rate < 0.6 or state.forgetting_score < 0.5:
                weaknesses.append({
                    'node_id': state.node_id,
                    'node_title': state.node_title,
                    'correct_rate': state.correct_rate,
                    'mastery_level': state.mastery_level,
                    'forgetting_score': state.forgetting_score,
                    'study_count': state.study_count
                })
        return sorted(weaknesses, key=lambda x: x['correct_rate'])

    def get_strengths(self, user_id: str) -> List[Dict]:
        states = self.knowledge_states.get(user_id, {})
        strengths = []
        for state in states.values():
            if state.correct_rate >= 0.8 and state.mastery_level >= 2:
                strengths.append({
                    'node_id': state.node_id,
                    'node_title': state.node_title,
                    'correct_rate': state.correct_rate,
                    'mastery_level': state.mastery_level
                })
        return sorted(strengths, key=lambda x: (-x['mastery_level'], -x['correct_rate']))

    def get_review_items(self, user_id: str, limit: int = 5) -> List[Dict]:
        states = self.knowledge_states.get(user_id, {})
        items = []
        for state in states.values():
            if state.forgetting_score < 0.7 and state.study_count > 0:
                items.append({
                    'node_id': state.node_id,
                    'node_title': state.node_title,
                    'forgetting_score': state.forgetting_score,
                    'last_study': state.last_study_time.isoformat() if state.last_study_time else None,
                    'priority': 1 - state.forgetting_score
                })
        items.sort(key=lambda x: x['priority'], reverse=True)
        return items[:limit]

    def get_wrong_answers_for_review(self, user_id: str, limit: int = 5) -> List[Dict]:
        wrongs = self.wrong_answer_book.get(user_id, [])
        unreviewed = [w for w in wrongs if not w.get('reviewed', False)]
        return unreviewed[-limit:]

    def create_goal(
        self,
        user_id: str,
        title: str,
        description: str,
        goal_type: GoalType,
        target_value: float,
        unit: str,
        deadline: Optional[datetime] = None,
        related_nodes: Optional[List[str]] = None,
        priority: int = 1
    ) -> LearningGoal:
        goal_id = f"goal_{datetime.now().strftime('%Y%m%d%H%M%S')}_{len(self.goals[user_id])}"
        goal = LearningGoal(
            id=goal_id,
            title=title,
            description=description,
            goal_type=goal_type,
            status=GoalStatus.PENDING,
            target_value=target_value,
            current_value=0.0,
            unit=unit,
            deadline=deadline,
            related_nodes=related_nodes or [],
            priority=priority
        )
        self.goals[user_id].append(goal)
        return goal

    def update_goal_progress(self, user_id: str, goal_id: str, delta: float) -> Optional[LearningGoal]:
        for goal in self.goals[user_id]:
            if goal.id == goal_id:
                goal.current_value += delta
                if goal.progress_percentage >= 100:
                    goal.status = GoalStatus.COMPLETED
                elif goal.current_value > 0 and goal.status == GoalStatus.PENDING:
                    goal.status = GoalStatus.IN_PROGRESS
                return goal
        return None

    def get_active_goals(self, user_id: str) -> List[LearningGoal]:
        return [g for g in self.goals[user_id] if g.status == GoalStatus.IN_PROGRESS]

    def get_goal_recommendations(self, user_id: str) -> List[Dict]:
        recommendations = []
        for goal in self.goals[user_id]:
            if goal.status == GoalStatus.COMPLETED:
                continue
            if goal.is_overdue:
                recommendations.append({
                    'goal_id': goal.id,
                    'type': 'overdue',
                    'message': f'目标「{goal.title}」已过期',
                    'suggestion': '考虑调整目标或分解为更小的目标'
                })
            elif goal.days_remaining is not None and goal.days_remaining <= 3:
                recommendations.append({
                    'goal_id': goal.id,
                    'type': 'urgent',
                    'message': f'目标「{goal.title}」还剩{goal.days_remaining}天',
                    'suggestion': f'还需完成{goal.target_value - goal.current_value}{goal.unit}'
                })
        return recommendations


class ProactiveTutorEngine:
    """
    主动导师引擎
    生成智能问候、学习建议、复习提醒
    """

    def __init__(self, memory: UnifiedTutorMemory):
        self.memory = memory

    def generate_greeting(self, user_id: str, course_id: str = None, node_id: str = None) -> Dict:
        """
        生成智能问候语
        像真正的老师一样，记住学生的情况
        """
        profile = self.memory.get_or_create_profile(user_id)
        weaknesses = self.memory.get_weaknesses(user_id)
        review_items = self.memory.get_review_items(user_id, limit=3)
        wrong_answers = self.memory.get_wrong_answers_for_review(user_id, limit=2)
        goals = self.memory.get_active_goals(user_id)

        greeting_parts = []
        actions = []

        streak = profile.get('streak_days', 0)
        if streak >= 7:
            greeting_parts.append(f"🎉 太棒了！你已连续学习{streak}天！")
        elif streak >= 3:
            greeting_parts.append(f"💪 连续学习{streak}天，继续保持！")
        elif streak == 1:
            greeting_parts.append("👋 欢迎回来！今天继续学习吧！")
        else:
            greeting_parts.append("👋 你好！准备好开始今天的学习了吗？")

        if review_items:
            items_text = "、".join([f"「{item['node_title']}」" for item in review_items[:2]])
            greeting_parts.append(f"\n📚 根据遗忘曲线，以下知识点需要复习：{items_text}")
            actions.append({
                'type': 'review_reminder',
                'label': '开始复习',
                'data': {'items': review_items}
            })

        if wrong_answers:
            greeting_parts.append(f"\n❌ 你有{len(wrong_answers)}道错题待重做")
            actions.append({
                'type': 'wrong_answer_review',
                'label': '重做错题',
                'data': {'items': wrong_answers}
            })

        if weaknesses:
            weak = weaknesses[0]
            greeting_parts.append(f"\n⚠️ 检测到「{weak['node_title']}」掌握度较低，建议加强练习")
            actions.append({
                'type': 'weakness_practice',
                'label': '针对性练习',
                'data': {'node_id': weak['node_id'], 'node_title': weak['node_title']}
            })

        if goals:
            goal = goals[0]
            progress = goal.progress_percentage
            greeting_parts.append(f"\n🎯 目标「{goal.title}」进度：{progress:.0f}%")

        return {
            'greeting': "\n".join(greeting_parts),
            'actions': actions,
            'stats': {
                'streak_days': streak,
                'total_study_time': profile.get('total_study_time', 0),
                'total_sessions': profile.get('total_sessions', 0),
                'weaknesses_count': len(weaknesses),
                'review_items_count': len(review_items)
            }
        }

    def generate_study_suggestion(self, user_id: str, context: Dict) -> Dict:
        """
        根据当前学习状态生成建议
        """
        profile = self.memory.get_or_create_profile(user_id)
        suggestions = []

        engagement = profile.get('engagement_score', 0.5)
        if engagement < 0.3:
            suggestions.append({
                'type': 'motivation',
                'message': '学习需要坚持，每一点进步都值得肯定！',
                'priority': 8
            })

        if context.get('time_stuck', 0) > 300:
            suggestions.append({
                'type': 'help',
                'message': '看起来你在这个问题上花了不少时间，需要一些提示吗？',
                'priority': 10
            })

        if context.get('consecutive_wrong', 0) >= 3:
            suggestions.append({
                'type': 'intervention',
                'message': '连续答错了好几题，要不要换个方式理解这个概念？',
                'priority': 10
            })

        return {
            'suggestions': sorted(suggestions, key=lambda x: -x['priority'])
        }

    def generate_session_summary(self, user_id: str, session_data: Dict) -> Dict:
        """
        生成学习会话总结
        """
        profile = self.memory.get_or_create_profile(user_id)
        weaknesses = self.memory.get_weaknesses(user_id)
        strengths = self.memory.get_strengths(user_id)

        duration = session_data.get('duration', 0)
        questions_answered = session_data.get('questions_answered', 0)
        correct_count = session_data.get('correct_count', 0)
        accuracy = (correct_count / questions_answered * 100) if questions_answered > 0 else 0

        summary_parts = [
            "📊 本次学习总结",
            f"",
            f"⏱️ 学习时长：{duration:.0f}分钟",
            f"📝 答题数：{questions_answered}题",
            f"✅ 正确率：{accuracy:.0f}%",
            f"",
        ]

        if accuracy >= 80:
            summary_parts.append("🌟 表现优秀！继续保持！")
        elif accuracy >= 60:
            summary_parts.append("💪 还不错，再接再厉！")
        else:
            summary_parts.append("📚 需要多加练习，加油！")

        if strengths:
            summary_parts.append(f"\n💪 擅长：{strengths[0]['node_title']}")
        if weaknesses:
            summary_parts.append(f"📈 待加强：{weaknesses[0]['node_title']}")

        return {
            'summary': "\n".join(summary_parts),
            'stats': {
                'duration': duration,
                'questions_answered': questions_answered,
                'correct_count': correct_count,
                'accuracy': accuracy
            },
            'next_suggestions': [
                {'action': 'review_weaknesses', 'label': '复习薄弱点'},
                {'action': 'continue_learning', 'label': '继续学习'},
                {'action': 'take_break', 'label': '休息一下'}
            ]
        }


tutor_memory = UnifiedTutorMemory()
proactive_engine = ProactiveTutorEngine(tutor_memory)


def get_tutor_memory() -> UnifiedTutorMemory:
    return tutor_memory


def get_proactive_engine() -> ProactiveTutorEngine:
    return proactive_engine
