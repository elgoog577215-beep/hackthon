"""
智能学习Agent核心模块
实现目标驱动、学习者建模、主动推送等Agent能力
"""

import json
import math
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
import asyncio
from collections import defaultdict


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
    FAILED = "failed"


class LearningStyle(Enum):
    VISUAL = "visual"
    AUDITORY = "auditory"
    READING = "reading"
    KINESTHETIC = "kinesthetic"
    MIXED = "mixed"


class MasteryLevel(Enum):
    NOVICE = 0
    BEGINNER = 1
    INTERMEDIATE = 2
    ADVANCED = 3
    EXPERT = 4


class ProactiveActionType(Enum):
    REVIEW_REMINDER = "review_reminder"
    PATH_RECOMMENDATION = "path_recommendation"
    DIFFICULTY_INTERVENTION = "difficulty_intervention"
    LEARNING_REPORT = "learning_report"
    GOAL_CHECK_IN = "goal_check_in"
    MOTIVATION_BOOST = "motivation_boost"


@dataclass
class LearningGoal:
    id: str
    user_id: str
    title: str
    description: str
    goal_type: GoalType
    status: GoalStatus
    target_value: float
    current_value: float
    unit: str
    deadline: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    milestones: List[Dict] = field(default_factory=list)
    related_nodes: List[str] = field(default_factory=list)
    related_courses: List[str] = field(default_factory=list)
    priority: int = 1
    metadata: Dict = field(default_factory=dict)

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
        data = asdict(self)
        data['goal_type'] = self.goal_type.value
        data['status'] = self.status.value
        data['deadline'] = self.deadline.isoformat() if self.deadline else None
        data['created_at'] = self.created_at.isoformat()
        data['updated_at'] = self.updated_at.isoformat()
        return data


@dataclass
class KnowledgeState:
    node_id: str
    node_title: str
    mastery_level: MasteryLevel
    confidence: float
    last_study_time: Optional[datetime] = None
    study_count: int = 0
    correct_rate: float = 0.0
    time_spent: float = 0.0
    forgetting_curve_score: float = 1.0
    prerequisites_mastered: bool = True
    related_concepts: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            'node_id': self.node_id,
            'node_title': self.node_title,
            'mastery_level': self.mastery_level.value,
            'confidence': self.confidence,
            'last_study_time': self.last_study_time.isoformat() if self.last_study_time else None,
            'study_count': self.study_count,
            'correct_rate': self.correct_rate,
            'time_spent': self.time_spent,
            'forgetting_curve_score': self.forgetting_curve_score,
            'prerequisites_mastered': self.prerequisites_mastered,
            'related_concepts': self.related_concepts
        }


@dataclass
class LearnerProfile:
    user_id: str
    learning_style: LearningStyle
    preferred_session_length: int
    preferred_difficulty: str
    active_hours: List[int]
    strengths: List[str]
    weaknesses: List[str]
    interests: List[str]
    goals: List[str]
    total_study_time: float = 0.0
    total_sessions: int = 0
    average_session_length: float = 0.0
    streak_days: int = 0
    last_active_date: Optional[datetime] = None
    knowledge_states: Dict[str, KnowledgeState] = field(default_factory=dict)
    learning_velocity: float = 1.0
    retention_rate: float = 0.8
    engagement_score: float = 0.5

    def to_dict(self) -> Dict:
        return {
            'user_id': self.user_id,
            'learning_style': self.learning_style.value,
            'preferred_session_length': self.preferred_session_length,
            'preferred_difficulty': self.preferred_difficulty,
            'active_hours': self.active_hours,
            'strengths': self.strengths,
            'weaknesses': self.weaknesses,
            'interests': self.interests,
            'goals': self.goals,
            'total_study_time': self.total_study_time,
            'total_sessions': self.total_sessions,
            'average_session_length': self.average_session_length,
            'streak_days': self.streak_days,
            'last_active_date': self.last_active_date.isoformat() if self.last_active_date else None,
            'knowledge_states': {k: v.to_dict() for k, v in self.knowledge_states.items()},
            'learning_velocity': self.learning_velocity,
            'retention_rate': self.retention_rate,
            'engagement_score': self.engagement_score
        }


@dataclass
class ProactiveAction:
    id: str
    action_type: ProactiveActionType
    title: str
    content: str
    priority: int
    created_at: datetime = field(default_factory=datetime.now)
    scheduled_for: Optional[datetime] = None
    delivered: bool = False
    dismissed: bool = False
    actioned: bool = False
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'action_type': self.action_type.value,
            'title': self.title,
            'content': self.content,
            'priority': self.priority,
            'created_at': self.created_at.isoformat(),
            'scheduled_for': self.scheduled_for.isoformat() if self.scheduled_for else None,
            'delivered': self.delivered,
            'dismissed': self.dismissed,
            'actioned': self.actioned,
            'metadata': self.metadata
        }


class GoalManager:
    """
    目标管理器
    负责学习目标的创建、追踪、更新和完成
    """

    def __init__(self, data_dir: str = "data/goals"):
        self.data_dir = data_dir
        self.goals: Dict[str, LearningGoal] = {}
        self.user_goals: Dict[str, List[str]] = defaultdict(list)

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
        related_courses: Optional[List[str]] = None,
        priority: int = 1,
        milestones: Optional[List[Dict]] = None
    ) -> LearningGoal:
        goal_id = f"goal_{datetime.now().strftime('%Y%m%d%H%M%S')}_{len(self.goals)}"
        
        goal = LearningGoal(
            id=goal_id,
            user_id=user_id,
            title=title,
            description=description,
            goal_type=goal_type,
            status=GoalStatus.PENDING,
            target_value=target_value,
            current_value=0.0,
            unit=unit,
            deadline=deadline,
            related_nodes=related_nodes or [],
            related_courses=related_courses or [],
            priority=priority,
            milestones=milestones or []
        )
        
        self.goals[goal_id] = goal
        self.user_goals[user_id].append(goal_id)
        
        return goal

    def update_goal_progress(self, goal_id: str, progress_delta: float) -> Optional[LearningGoal]:
        if goal_id not in self.goals:
            return None
        
        goal = self.goals[goal_id]
        goal.current_value += progress_delta
        goal.updated_at = datetime.now()
        
        if goal.progress_percentage >= 100:
            goal.status = GoalStatus.COMPLETED
        elif goal.current_value > 0 and goal.status == GoalStatus.PENDING:
            goal.status = GoalStatus.IN_PROGRESS
        
        return goal

    def get_user_goals(self, user_id: str, status: Optional[GoalStatus] = None) -> List[LearningGoal]:
        goal_ids = self.user_goals.get(user_id, [])
        goals = [self.goals[gid] for gid in goal_ids if gid in self.goals]
        
        if status:
            goals = [g for g in goals if g.status == status]
        
        return sorted(goals, key=lambda g: (-g.priority, g.created_at))

    def get_active_goals(self, user_id: str) -> List[LearningGoal]:
        return self.get_user_goals(user_id, GoalStatus.IN_PROGRESS)

    def check_milestones(self, goal_id: str) -> List[Dict]:
        if goal_id not in self.goals:
            return []
        
        goal = self.goals[goal_id]
        achieved_milestones = []
        
        for milestone in goal.milestones:
            if milestone.get('achieved', False):
                continue
            
            threshold = milestone.get('threshold', 0)
            if goal.current_value >= threshold:
                milestone['achieved'] = True
                milestone['achieved_at'] = datetime.now().isoformat()
                achieved_milestones.append(milestone)
        
        return achieved_milestones

    def get_goal_recommendations(self, user_id: str) -> List[Dict]:
        goals = self.get_user_goals(user_id)
        recommendations = []
        
        for goal in goals:
            if goal.status == GoalStatus.COMPLETED:
                continue
            
            if goal.is_overdue:
                recommendations.append({
                    'goal_id': goal.id,
                    'type': 'overdue',
                    'message': f'目标"{goal.title}"已过期，建议调整或重新设定',
                    'suggestion': '考虑延长截止日期或分解为更小的目标'
                })
            elif goal.days_remaining is not None and goal.days_remaining <= 3:
                progress_needed = goal.target_value - goal.current_value
                recommendations.append({
                    'goal_id': goal.id,
                    'type': 'urgent',
                    'message': f'目标"{goal.title}"还剩{goal.days_remaining}天，还需完成{progress_needed}{goal.unit}',
                    'suggestion': '建议增加学习时间或调整目标'
                })
            elif goal.progress_percentage < 50 and goal.days_remaining is not None:
                days_passed_ratio = 1 - (goal.days_remaining / max(1, (goal.deadline - goal.created_at).days))
                if goal.progress_percentage < days_passed_ratio * 100 * 0.8:
                    recommendations.append({
                        'goal_id': goal.id,
                        'type': 'behind',
                        'message': f'目标"{goal.title}"进度落后，当前{goal.progress_percentage:.1f}%',
                        'suggestion': '建议加快学习进度'
                    })
        
        return recommendations

    def pause_goal(self, goal_id: str) -> Optional[LearningGoal]:
        if goal_id not in self.goals:
            return None
        self.goals[goal_id].status = GoalStatus.PAUSED
        self.goals[goal_id].updated_at = datetime.now()
        return self.goals[goal_id]

    def resume_goal(self, goal_id: str) -> Optional[LearningGoal]:
        if goal_id not in self.goals:
            return None
        self.goals[goal_id].status = GoalStatus.IN_PROGRESS
        self.goals[goal_id].updated_at = datetime.now()
        return self.goals[goal_id]

    def delete_goal(self, goal_id: str) -> bool:
        if goal_id not in self.goals:
            return False
        
        user_id = self.goals[goal_id].user_id
        del self.goals[goal_id]
        
        if user_id in self.user_goals:
            self.user_goals[user_id] = [gid for gid in self.user_goals[user_id] if gid != goal_id]
        
        return True


class LearnerModel:
    """
    学习者模型
    负责建模用户的知识状态、学习风格和学习行为
    """

    def __init__(self, data_dir: str = "data/learners"):
        self.data_dir = data_dir
        self.profiles: Dict[str, LearnerProfile] = {}

    def get_or_create_profile(self, user_id: str) -> LearnerProfile:
        if user_id not in self.profiles:
            self.profiles[user_id] = LearnerProfile(
                user_id=user_id,
                learning_style=LearningStyle.MIXED,
                preferred_session_length=30,
                preferred_difficulty="medium",
                active_hours=[9, 10, 11, 14, 15, 20, 21],
                strengths=[],
                weaknesses=[],
                interests=[],
                goals=[]
            )
        return self.profiles[user_id]

    def update_knowledge_state(
        self,
        user_id: str,
        node_id: str,
        node_title: str,
        is_correct: Optional[bool] = None,
        time_spent: float = 0.0,
        related_concepts: Optional[List[str]] = None
    ) -> KnowledgeState:
        profile = self.get_or_create_profile(user_id)
        
        if node_id not in profile.knowledge_states:
            profile.knowledge_states[node_id] = KnowledgeState(
                node_id=node_id,
                node_title=node_title,
                mastery_level=MasteryLevel.NOVICE,
                confidence=0.0
            )
        
        state = profile.knowledge_states[node_id]
        state.study_count += 1
        state.last_study_time = datetime.now()
        state.time_spent += time_spent
        
        if related_concepts:
            state.related_concepts = list(set(state.related_concepts + related_concepts))
        
        if is_correct is not None:
            total_questions = state.study_count
            correct_count = state.correct_rate * (total_questions - 1)
            if is_correct:
                correct_count += 1
            state.correct_rate = correct_count / total_questions
            
            if state.correct_rate >= 0.9 and state.study_count >= 5:
                state.mastery_level = MasteryLevel.EXPERT
            elif state.correct_rate >= 0.75 and state.study_count >= 3:
                state.mastery_level = MasteryLevel.ADVANCED
            elif state.correct_rate >= 0.6 and state.study_count >= 2:
                state.mastery_level = MasteryLevel.INTERMEDIATE
            elif state.correct_rate >= 0.4:
                state.mastery_level = MasteryLevel.BEGINNER
        
        state.confidence = min(1.0, state.study_count * 0.1 + state.correct_rate * 0.5)
        state.forgetting_curve_score = self._calculate_forgetting_score(state)
        
        return state

    def _calculate_forgetting_score(self, state: KnowledgeState) -> float:
        if state.last_study_time is None:
            return 1.0
        
        days_since_study = (datetime.now() - state.last_study_time).days
        
        stability = 1.0 + state.study_count * 0.1 + state.mastery_level.value * 0.2
        retention = math.exp(-days_since_study / stability)
        
        return max(0.1, retention)

    def update_learning_style(self, user_id: str, style: LearningStyle):
        profile = self.get_or_create_profile(user_id)
        profile.learning_style = style

    def update_preferences(
        self,
        user_id: str,
        session_length: Optional[int] = None,
        difficulty: Optional[str] = None,
        active_hours: Optional[List[int]] = None
    ):
        profile = self.get_or_create_profile(user_id)
        if session_length is not None:
            profile.preferred_session_length = session_length
        if difficulty is not None:
            profile.preferred_difficulty = difficulty
        if active_hours is not None:
            profile.active_hours = active_hours

    def record_session(self, user_id: str, duration: float, nodes_studied: List[str]):
        profile = self.get_or_create_profile(user_id)
        
        profile.total_sessions += 1
        profile.total_study_time += duration
        profile.average_session_length = profile.total_study_time / profile.total_sessions
        
        today = datetime.now().date()
        if profile.last_active_date:
            last_date = profile.last_active_date.date()
            if today - last_date == timedelta(days=1):
                profile.streak_days += 1
            elif today != last_date:
                profile.streak_days = 1
        else:
            profile.streak_days = 1
        
        profile.last_active_date = datetime.now()
        
        self._update_engagement_score(profile)

    def _update_engagement_score(self, profile: LearnerProfile):
        streak_factor = min(1.0, profile.streak_days / 7)
        session_factor = min(1.0, profile.total_sessions / 10)
        time_factor = min(1.0, profile.total_study_time / 600)
        
        profile.engagement_score = (streak_factor * 0.4 + session_factor * 0.3 + time_factor * 0.3)

    def identify_weaknesses(self, user_id: str) -> List[Dict]:
        profile = self.get_or_create_profile(user_id)
        weaknesses = []
        
        for node_id, state in profile.knowledge_states.items():
            if state.correct_rate < 0.6 or state.forgetting_curve_score < 0.5:
                weaknesses.append({
                    'node_id': node_id,
                    'node_title': state.node_title,
                    'correct_rate': state.correct_rate,
                    'mastery_level': state.mastery_level.value,
                    'forgetting_score': state.forgetting_curve_score,
                    'study_count': state.study_count,
                    'reason': 'correct_rate_low' if state.correct_rate < 0.6 else 'forgetting_high'
                })
        
        return sorted(weaknesses, key=lambda x: x['correct_rate'])

    def identify_strengths(self, user_id: str) -> List[Dict]:
        profile = self.get_or_create_profile(user_id)
        strengths = []
        
        for node_id, state in profile.knowledge_states.items():
            if state.correct_rate >= 0.8 and state.mastery_level.value >= MasteryLevel.INTERMEDIATE.value:
                strengths.append({
                    'node_id': node_id,
                    'node_title': state.node_title,
                    'correct_rate': state.correct_rate,
                    'mastery_level': state.mastery_level.value,
                    'study_count': state.study_count
                })
        
        return sorted(strengths, key=lambda x: (-x['mastery_level'], -x['correct_rate']))

    def get_learning_velocity(self, user_id: str) -> float:
        profile = self.get_or_create_profile(user_id)
        
        if profile.total_sessions < 3:
            return 1.0
        
        mastered_count = sum(
            1 for state in profile.knowledge_states.values()
            if state.mastery_level.value >= MasteryLevel.INTERMEDIATE.value
        )
        
        velocity = mastered_count / max(1, profile.total_sessions)
        profile.learning_velocity = min(2.0, velocity * 10)
        
        return profile.learning_velocity

    def predict_difficulty(self, user_id: str, node_id: str, node_prerequisites: List[str]) -> str:
        profile = self.get_or_create_profile(user_id)
        
        prereq_mastered = 0
        for prereq in node_prerequisites:
            if prereq in profile.knowledge_states:
                state = profile.knowledge_states[prereq]
                if state.mastery_level.value >= MasteryLevel.BEGINNER.value:
                    prereq_mastered += 1
        
        prereq_ratio = prereq_mastered / max(1, len(node_prerequisites))
        
        if prereq_ratio >= 0.8 and profile.learning_velocity >= 1.2:
            return "easy"
        elif prereq_ratio >= 0.5 or profile.learning_velocity >= 0.8:
            return "medium"
        else:
            return "hard"

    def get_next_review_items(self, user_id: str, limit: int = 5) -> List[Dict]:
        profile = self.get_or_create_profile(user_id)
        review_items = []
        
        for node_id, state in profile.knowledge_states.items():
            if state.forgetting_curve_score < 0.7 and state.study_count > 0:
                review_items.append({
                    'node_id': node_id,
                    'node_title': state.node_title,
                    'forgetting_score': state.forgetting_curve_score,
                    'last_study': state.last_study_time.isoformat() if state.last_study_time else None,
                    'priority': 1 - state.forgetting_curve_score
                })
        
        review_items.sort(key=lambda x: x['priority'], reverse=True)
        return review_items[:limit]


class ProactiveEngine:
    """
    主动引擎
    负责生成主动推送、复习提醒、困难干预等
    """

    def __init__(
        self,
        goal_manager: GoalManager,
        learner_model: LearnerModel,
        data_dir: str = "data/proactive"
    ):
        self.goal_manager = goal_manager
        self.learner_model = learner_model
        self.data_dir = data_dir
        self.actions: Dict[str, ProactiveAction] = {}
        self.user_actions: Dict[str, List[str]] = defaultdict(list)
        self.action_counter = 0

    def _generate_action_id(self) -> str:
        self.action_counter += 1
        return f"action_{datetime.now().strftime('%Y%m%d%H%M%S')}_{self.action_counter}"

    def generate_review_reminders(self, user_id: str) -> List[ProactiveAction]:
        review_items = self.learner_model.get_next_review_items(user_id)
        actions = []
        
        for item in review_items:
            action = ProactiveAction(
                id=self._generate_action_id(),
                action_type=ProactiveActionType.REVIEW_REMINDER,
                title=f"复习提醒：{item['node_title']}",
                content=f"根据遗忘曲线，您需要复习「{item['node_title']}」了。上次学习后已过去一段时间，及时复习可以巩固记忆。",
                priority=int((1 - item['forgetting_score']) * 10),
                metadata={
                    'node_id': item['node_id'],
                    'forgetting_score': item['forgetting_score']
                }
            )
            
            self.actions[action.id] = action
            self.user_actions[user_id].append(action.id)
            actions.append(action)
        
        return actions

    def generate_path_recommendations(self, user_id: str) -> List[ProactiveAction]:
        profile = self.learner_model.get_or_create_profile(user_id)
        weaknesses = self.learner_model.identify_weaknesses(user_id)
        actions = []
        
        if weaknesses:
            weak_node = weaknesses[0]
            action = ProactiveAction(
                id=self._generate_action_id(),
                action_type=ProactiveActionType.PATH_RECOMMENDATION,
                title=f"学习建议：加强{weak_node['node_title']}",
                content=f"检测到您在「{weak_node['node_title']}」的正确率为{weak_node['correct_rate']*100:.1f}%，建议进行针对性练习。",
                priority=8,
                metadata={
                    'node_id': weak_node['node_id'],
                    'correct_rate': weak_node['correct_rate']
                }
            )
            
            self.actions[action.id] = action
            self.user_actions[user_id].append(action.id)
            actions.append(action)
        
        strengths = self.learner_model.identify_strengths(user_id)
        if strengths and profile.learning_velocity >= 1.0:
            action = ProactiveAction(
                id=self._generate_action_id(),
                action_type=ProactiveActionType.PATH_RECOMMENDATION,
                title="学习建议：挑战新内容",
                content=f"您学习进展顺利！已掌握{len(strengths)}个知识点，建议尝试更有挑战性的内容。",
                priority=6,
                metadata={
                    'strengths_count': len(strengths),
                    'learning_velocity': profile.learning_velocity
                }
            )
            
            self.actions[action.id] = action
            self.user_actions[user_id].append(action.id)
            actions.append(action)
        
        return actions

    def generate_difficulty_intervention(self, user_id: str, context: Dict) -> Optional[ProactiveAction]:
        consecutive_wrong = context.get('consecutive_wrong', 0)
        time_stuck = context.get('time_stuck', 0)
        current_node = context.get('current_node', '')
        current_node_title = context.get('current_node_title', '')
        
        if consecutive_wrong >= 3 or time_stuck > 300:
            intervention_type = "consecutive_errors" if consecutive_wrong >= 3 else "time_stuck"
            
            if intervention_type == "consecutive_errors":
                content = f"检测到您在「{current_node_title}」遇到了困难，连续{consecutive_wrong}次答题错误。要不要换个方式理解这个概念？"
            else:
                content = f"您在「{current_node_title}」已经学习超过{time_stuck//60}分钟了，需要一些提示或者休息一下吗？"
            
            action = ProactiveAction(
                id=self._generate_action_id(),
                action_type=ProactiveActionType.DIFFICULTY_INTERVENTION,
                title="学习困难干预",
                content=content,
                priority=10,
                metadata={
                    'intervention_type': intervention_type,
                    'node_id': current_node,
                    'consecutive_wrong': consecutive_wrong,
                    'time_stuck': time_stuck
                }
            )
            
            self.actions[action.id] = action
            self.user_actions[user_id].append(action.id)
            return action
        
        return None

    def generate_learning_report(self, user_id: str, period: str = "weekly") -> ProactiveAction:
        profile = self.learner_model.get_or_create_profile(user_id)
        goals = self.goal_manager.get_user_goals(user_id)
        weaknesses = self.learner_model.identify_weaknesses(user_id)
        strengths = self.learner_model.identify_strengths(user_id)
        
        completed_goals = [g for g in goals if g.status == GoalStatus.COMPLETED]
        in_progress_goals = [g for g in goals if g.status == GoalStatus.IN_PROGRESS]
        
        if period == "weekly":
            period_label = "本周"
        elif period == "monthly":
            period_label = "本月"
        else:
            period_label = "今日"
        
        content_parts = [
            f"📊 {period_label}学习报告",
            f"",
            f"⏱️ 学习时长：{profile.total_study_time:.1f}分钟",
            f"📚 学习次数：{profile.total_sessions}次",
            f"🔥 连续学习：{profile.streak_days}天",
            f"",
            f"✅ 已掌握知识点：{len(strengths)}个",
            f"⚠️ 需要加强：{len(weaknesses)}个",
            f"",
            f"🎯 目标完成：{len(completed_goals)}个",
            f"🎯 进行中目标：{len(in_progress_goals)}个"
        ]
        
        if strengths:
            content_parts.append(f"\n💪 最擅长：{strengths[0]['node_title']}")
        if weaknesses:
            content_parts.append(f"\n📈 建议加强：{weaknesses[0]['node_title']}")
        
        action = ProactiveAction(
            id=self._generate_action_id(),
            action_type=ProactiveActionType.LEARNING_REPORT,
            title=f"{period_label}学习报告",
            content="\n".join(content_parts),
            priority=5,
            metadata={
                'period': period,
                'total_study_time': profile.total_study_time,
                'total_sessions': profile.total_sessions,
                'streak_days': profile.streak_days,
                'strengths_count': len(strengths),
                'weaknesses_count': len(weaknesses),
                'completed_goals': len(completed_goals)
            }
        )
        
        self.actions[action.id] = action
        self.user_actions[user_id].append(action.id)
        return action

    def generate_goal_check_in(self, user_id: str) -> List[ProactiveAction]:
        recommendations = self.goal_manager.get_goal_recommendations(user_id)
        actions = []
        
        for rec in recommendations:
            action = ProactiveAction(
                id=self._generate_action_id(),
                action_type=ProactiveActionType.GOAL_CHECK_IN,
                title=f"目标检查：{rec['type']}",
                content=rec['message'],
                priority=7,
                metadata={
                    'goal_id': rec['goal_id'],
                    'recommendation_type': rec['type'],
                    'suggestion': rec['suggestion']
                }
            )
            
            self.actions[action.id] = action
            self.user_actions[user_id].append(action.id)
            actions.append(action)
        
        return actions

    def generate_motivation_boost(self, user_id: str) -> Optional[ProactiveAction]:
        profile = self.learner_model.get_or_create_profile(user_id)
        
        messages = []
        
        if profile.streak_days >= 7:
            messages.append(f"🎉 太棒了！您已连续学习{profile.streak_days}天，坚持就是胜利！")
        elif profile.streak_days >= 3:
            messages.append(f"💪 已连续学习{profile.streak_days}天，继续保持！")
        
        if profile.total_sessions >= 10:
            messages.append(f"📚 您已完成{profile.total_sessions}次学习，知识积累越来越多！")
        
        if profile.engagement_score >= 0.7:
            messages.append("🌟 您的学习热情很高，继续保持这种学习状态！")
        
        if not messages:
            if profile.total_sessions == 0:
                messages.append("👋 欢迎开始您的学习之旅！设定一个目标开始吧。")
            else:
                messages.append("📖 学习是一场马拉松，每天进步一点点！")
        
        action = ProactiveAction(
            id=self._generate_action_id(),
            action_type=ProactiveActionType.MOTIVATION_BOOST,
            title="学习激励",
            content=messages[0] if len(messages) == 1 else "\n".join(f"• {m}" for m in messages),
            priority=4,
            metadata={
                'streak_days': profile.streak_days,
                'engagement_score': profile.engagement_score
            }
        )
        
        self.actions[action.id] = action
        self.user_actions[user_id].append(action.id)
        return action

    def get_pending_actions(self, user_id: str, limit: int = 10) -> List[ProactiveAction]:
        action_ids = self.user_actions.get(user_id, [])
        actions = [
            self.actions[aid] for aid in action_ids
            if aid in self.actions and not self.actions[aid].delivered and not self.actions[aid].dismissed
        ]
        
        actions.sort(key=lambda x: (-x.priority, x.created_at))
        return actions[:limit]

    def mark_action_delivered(self, action_id: str) -> bool:
        if action_id in self.actions:
            self.actions[action_id].delivered = True
            return True
        return False

    def dismiss_action(self, action_id: str) -> bool:
        if action_id in self.actions:
            self.actions[action_id].dismissed = True
            return True
        return False

    def action_taken(self, action_id: str) -> bool:
        if action_id in self.actions:
            self.actions[action_id].actioned = True
            return True
        return False


class AgentDecisionController:
    """
    Agent决策中心
    协调目标管理、学习者模型和主动引擎的决策
    """

    def __init__(
        self,
        goal_manager: GoalManager,
        learner_model: LearnerModel,
        proactive_engine: ProactiveEngine
    ):
        self.goal_manager = goal_manager
        self.learner_model = learner_model
        self.proactive_engine = proactive_engine
        self.decision_history: List[Dict] = []

    def analyze_learning_state(self, user_id: str) -> Dict:
        profile = self.learner_model.get_or_create_profile(user_id)
        goals = self.goal_manager.get_user_goals(user_id)
        weaknesses = self.learner_model.identify_weaknesses(user_id)
        strengths = self.learner_model.identify_strengths(user_id)
        
        return {
            'user_id': user_id,
            'engagement_score': profile.engagement_score,
            'learning_velocity': profile.learning_velocity,
            'streak_days': profile.streak_days,
            'total_sessions': profile.total_sessions,
            'active_goals': len([g for g in goals if g.status == GoalStatus.IN_PROGRESS]),
            'completed_goals': len([g for g in goals if g.status == GoalStatus.COMPLETED]),
            'weaknesses_count': len(weaknesses),
            'strengths_count': len(strengths),
            'knowledge_coverage': len(profile.knowledge_states),
            'average_mastery': sum(s.mastery_level.value for s in profile.knowledge_states.values()) / max(1, len(profile.knowledge_states))
        }

    def decide_next_action(self, user_id: str, context: Optional[Dict] = None) -> Dict:
        state = self.analyze_learning_state(user_id)
        context = context or {}
        
        decision = {
            'timestamp': datetime.now().isoformat(),
            'user_id': user_id,
            'state': state,
            'actions_to_take': [],
            'reasoning': []
        }
        
        if context.get('consecutive_wrong', 0) >= 3 or context.get('time_stuck', 0) > 300:
            intervention = self.proactive_engine.generate_difficulty_intervention(user_id, context)
            if intervention:
                decision['actions_to_take'].append({
                    'type': 'immediate',
                    'action': intervention.to_dict()
                })
                decision['reasoning'].append("检测到学习困难，需要立即干预")
                self.decision_history.append(decision)
                return decision
        
        pending_actions = self.proactive_engine.get_pending_actions(user_id, limit=3)
        if pending_actions:
            decision['actions_to_take'].extend([
                {'type': 'pending', 'action': a.to_dict()}
                for a in pending_actions
            ])
            decision['reasoning'].append(f"有{len(pending_actions)}个待处理的主动推送")
        
        if state['engagement_score'] < 0.3 and state['total_sessions'] > 0:
            motivation = self.proactive_engine.generate_motivation_boost(user_id)
            if motivation:
                decision['actions_to_take'].append({
                    'type': 'motivation',
                    'action': motivation.to_dict()
                })
                decision['reasoning'].append("用户参与度较低，需要激励")
        
        review_items = self.learner_model.get_next_review_items(user_id, limit=1)
        if review_items and review_items[0]['forgetting_score'] < 0.4:
            reminders = self.proactive_engine.generate_review_reminders(user_id)
            if reminders:
                decision['actions_to_take'].append({
                    'type': 'review',
                    'action': reminders[0].to_dict()
                })
                decision['reasoning'].append("有知识点需要复习")
        
        goal_recommendations = self.goal_manager.get_goal_recommendations(user_id)
        if goal_recommendations:
            check_ins = self.proactive_engine.generate_goal_check_in(user_id)
            decision['actions_to_take'].extend([
                {'type': 'goal_check', 'action': a.to_dict()}
                for a in check_ins[:2]
            ])
            decision['reasoning'].append("目标需要检查和调整")
        
        self.decision_history.append(decision)
        return decision

    def generate_personalized_prompt(self, user_id: str, task_type: str, context: Dict) -> str:
        profile = self.learner_model.get_or_create_profile(user_id)
        goals = self.goal_manager.get_active_goals(user_id)
        weaknesses = self.learner_model.identify_weaknesses(user_id)
        
        prompt_parts = [
            f"学习者画像：",
            f"- 学习风格：{profile.learning_style.value}",
            f"- 偏好难度：{profile.preferred_difficulty}",
            f"- 学习速度：{profile.learning_velocity:.1f}x",
            f"- 连续学习：{profile.streak_days}天"
        ]
        
        if goals:
            prompt_parts.append(f"\n当前目标：")
            for goal in goals[:3]:
                prompt_parts.append(f"- {goal.title} ({goal.progress_percentage:.0f}%)")
        
        if weaknesses:
            prompt_parts.append(f"\n需要加强的知识点：")
            for w in weaknesses[:3]:
                prompt_parts.append(f"- {w['node_title']} (正确率: {w['correct_rate']*100:.0f}%)")
        
        prompt_parts.append(f"\n任务类型：{task_type}")
        
        if context:
            prompt_parts.append(f"\n上下文信息：")
            for key, value in context.items():
                prompt_parts.append(f"- {key}: {value}")
        
        return "\n".join(prompt_parts)

    def update_after_interaction(
        self,
        user_id: str,
        interaction_type: str,
        node_id: Optional[str] = None,
        is_correct: Optional[bool] = None,
        time_spent: float = 0.0
    ):
        if node_id:
            self.learner_model.update_knowledge_state(
                user_id=user_id,
                node_id=node_id,
                node_title="",  # Should be provided in real usage
                is_correct=is_correct,
                time_spent=time_spent
            )
        
        if interaction_type == "quiz_complete":
            goals = self.goal_manager.get_active_goals(user_id)
            for goal in goals:
                if goal.goal_type == GoalType.TASK_ORIENTED:
                    self.goal_manager.update_goal_progress(goal.id, 1)
        
        elif interaction_type == "study_session":
            self.learner_model.record_session(user_id, time_spent, [node_id] if node_id else [])

    def get_agent_status(self, user_id: str) -> Dict:
        state = self.analyze_learning_state(user_id)
        pending_actions = self.proactive_engine.get_pending_actions(user_id)
        
        return {
            'status': 'active',
            'learner_state': state,
            'pending_actions_count': len(pending_actions),
            'last_decision': self.decision_history[-1] if self.decision_history else None,
            'recommendations': self.goal_manager.get_goal_recommendations(user_id)
        }


agent_goal_manager = GoalManager()
agent_learner_model = LearnerModel()
agent_proactive_engine = ProactiveEngine(agent_goal_manager, agent_learner_model)
agent_controller = AgentDecisionController(
    agent_goal_manager,
    agent_learner_model,
    agent_proactive_engine
)
