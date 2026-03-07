"""
AI 学习路径服务模块

负责学习路径生成、知识掌握度分析、
SM-2 间隔复习算法、复习计划生成、复习结果提交和复习进度查询。
"""

import json
import math
import random
import logging
from datetime import datetime, timedelta
from typing import List, Dict

from ai_base import AIBase
from prompts import get_prompt

logger = logging.getLogger(__name__)


class AILearningService(AIBase):
    """学习路径与复习调度相关的 AI 服务"""

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
        """
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

    async def analyze_knowledge_mastery(
        self,
        course_id: str,
        progress_data: List[Dict],
        quiz_history: List[Dict],
        all_nodes: List[Dict]
    ) -> List[Dict]:
        """
        分析知识掌握度
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
        jitter = random.uniform(0.9, 1.1)
        interval_days = max(1, int(interval_days * jitter))
        
        return interval_days, new_ease_factor, new_review_count
    
    def calculate_retention_rate(self, days_since_review: int, ease_factor: float) -> float:
        """
        计算记忆保留率（艾宾浩斯遗忘曲线）
        """
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
        """
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
        """
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
        """
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
