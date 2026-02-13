import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from storage import storage
import hashlib
import json

logger = logging.getLogger(__name__)


class ConversationTopicTracker:
    """
    对话主题追踪器 - 识别和跟踪对话主题的变化
    """
    def __init__(self):
        self.topic_keywords = {
            'concept': ['概念', '定义', '什么是', 'meaning', 'definition', 'concept'],
            'example': ['例子', '举例', '示例', 'example', 'instance', 'case'],
            'application': ['应用', '使用', '实践', 'apply', 'usage', 'practice'],
            'comparison': ['区别', '对比', '比较', 'vs', 'difference', 'compare'],
            'implementation': ['实现', '代码', '编程', 'code', 'implement', 'programming'],
            'theory': ['理论', '原理', '机制', 'theory', 'principle', 'mechanism'],
            'problem': ['问题', '错误', 'bug', 'problem', 'error', 'issue'],
            'review': ['复习', '总结', '回顾', 'review', 'summary', 'recap']
        }
    
    def detect_topic_shift(self, current_message: str, previous_messages: List[Dict], threshold: float = 0.3) -> Tuple[bool, str]:
        """
        检测对话主题是否发生变化
        
        Returns:
            (是否变化, 新主题)
        """
        if not previous_messages:
            return False, self._classify_topic(current_message)
        
        current_topic = self._classify_topic(current_message)
        
        # 获取最近几条消息的主题
        recent_topics = []
        for msg in previous_messages[-3:]:
            if msg.get('role') == 'user':
                recent_topics.append(self._classify_topic(msg.get('content', '')))
        
        if not recent_topics:
            return False, current_topic
        
        # 检查主题是否一致
        topic_consistency = sum(1 for t in recent_topics if t == current_topic) / len(recent_topics)
        
        return topic_consistency < threshold, current_topic
    
    def _classify_topic(self, message: str) -> str:
        """对消息进行主题分类"""
        message_lower = message.lower()
        topic_scores = {}
        
        for topic, keywords in self.topic_keywords.items():
            score = sum(1 for kw in keywords if kw in message_lower)
            if score > 0:
                topic_scores[topic] = score
        
        if topic_scores:
            return max(topic_scores, key=topic_scores.get)
        return 'general'
    
    def extract_key_entities(self, messages: List[Dict]) -> List[str]:
        """从对话中提取关键实体/概念"""
        entities = set()
        
        for msg in messages:
            content = msg.get('content', '')
            # 简单提取引号内的内容和特定模式
            import re
            # 提取英文术语
            english_terms = re.findall(r'\b[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*\b', content)
            entities.update(english_terms)
            
            # 提取中文术语（带引号的）
            chinese_terms = re.findall(r'[「""']([^「""']+)[」""']', content)
            entities.update(chinese_terms)
        
        return list(entities)[:10]  # 限制数量


class LongTermMemoryManager:
    """
    长期记忆管理器 - 保存和检索跨会话的重要记忆
    """
    def __init__(self):
        self.memory_cache = {}
        self.max_memories_per_topic = 5
    
    def save_conversation_memory(self, course_id: str, node_id: str, 
                                 summary: str, key_concepts: List[str],
                                 user_insights: List[str], difficulty_level: str):
        """保存对话记忆到长期存储"""
        memory_key = f"{course_id}:{node_id}"
        
        memory_entry = {
            'timestamp': datetime.now().isoformat(),
            'summary': summary,
            'key_concepts': key_concepts,
            'user_insights': user_insights,
            'difficulty_level': difficulty_level,
            'memory_id': hashlib.md5(f"{memory_key}:{datetime.now()}".encode()).hexdigest()[:8]
        }
        
        if memory_key not in self.memory_cache:
            self.memory_cache[memory_key] = []
        
        self.memory_cache[memory_key].append(memory_entry)
        
        # 限制每个主题的记忆数量，保留最新的
        if len(self.memory_cache[memory_key]) > self.max_memories_per_topic:
            self.memory_cache[memory_key] = self.memory_cache[memory_key][-self.max_memories_per_topic:]
        
        # 持久化到存储
        self._persist_memories(course_id, node_id)
    
    def get_relevant_memories(self, course_id: str, node_id: str, 
                             query: str = "", limit: int = 3) -> List[Dict]:
        """检索相关的长期记忆"""
        memory_key = f"{course_id}:{node_id}"
        memories = self.memory_cache.get(memory_key, [])
        
        if not query or not memories:
            return memories[-limit:] if memories else []
        
        # 基于关键词匹配排序
        query_keywords = set(query.lower().split())
        scored_memories = []
        
        for memory in memories:
            score = 0
            # 检查摘要匹配
            summary_words = set(memory.get('summary', '').lower().split())
            score += len(query_keywords & summary_words)
            
            # 检查关键概念匹配
            for concept in memory.get('key_concepts', []):
                if any(kw in concept.lower() for kw in query_keywords):
                    score += 2
            
            scored_memories.append((score, memory))
        
        # 按分数排序，返回最相关的
        scored_memories.sort(key=lambda x: x[0], reverse=True)
        return [m for _, m in scored_memories[:limit]]
    
    def _persist_memories(self, course_id: str, node_id: str):
        """将记忆持久化到存储"""
        memory_key = f"{course_id}:{node_id}"
        memories = self.memory_cache.get(memory_key, [])
        
        # 使用storage保存到文件
        try:
            all_memories = storage.load_data('long_term_memories.json') or {}
            all_memories[memory_key] = memories
            storage.save_data('long_term_memories.json', all_memories)
        except Exception as e:
            logger.error(f"Failed to persist memories: {e}")
    
    def load_persisted_memories(self):
        """从存储加载持久化的记忆"""
        try:
            all_memories = storage.load_data('long_term_memories.json') or {}
            self.memory_cache = all_memories
        except Exception as e:
            logger.error(f"Failed to load memories: {e}")


class ContentMemoryManager:
    """
    Manages the 'Main Memory' - Course Content, Knowledge Graph, Context.
    Focus: Textbook knowledge graph, teaching content understanding.
    """
    def __init__(self):
        # Cache for flattened nodes: course_id -> (timestamp, List[Dict])
        self.flat_nodes_cache = {}

    def get_course_context(self, course_id: str, current_node_id: str) -> str:
        """
        Retrieves context for the current node, including:
        1. Current node content.
        2. Parent node context (if any).
        3. Previous/Next sibling context (brief).
        """
        # Storage now uses in-memory cache, so this is fast
        course = storage.load_course(course_id)
        if not course:
            return ""

        nodes = course.get("nodes", [])
        
        # Cache flattened structure (simple invalidation based on object id or we can just recompute if small)
        # Since course object is same ref from storage cache if not reloaded, we can use id(nodes)
        cache_key = (course_id, id(nodes))
        if cache_key in self.flat_nodes_cache:
            flat_nodes = self.flat_nodes_cache[cache_key]
        else:
            flat_nodes = self._flatten_nodes(nodes)
            # Clear old cache for this course to prevent leak
            # Simple approach: clear all for this course_id? Or just keep dict small.
            # For MVP, just set.
            self.flat_nodes_cache = {k:v for k,v in self.flat_nodes_cache.items() if k[0] != course_id}
            self.flat_nodes_cache[cache_key] = flat_nodes
        
        current_node = next((n for n in flat_nodes if n.get("node_id") == current_node_id), None)
        if not current_node:
            return ""

        context_parts = []
        
        # 1. Hierarchy Context (Parent)
        if current_node.get("parent_node_id"):
            parent = next((n for n in flat_nodes if n.get("node_id") == current_node.get("parent_node_id")), None)
            if parent:
                context_parts.append(f"## Parent Chapter: {parent.get('node_name')}\nSummary: {parent.get('node_content', '')[:200]}...")

        # 2. Current Node Content (Main Focus)
        context_parts.append(f"## Current Topic: {current_node.get('node_name')}\nContent:\n{current_node.get('node_content', '')}")

        # 3. Knowledge Graph Connections (Siblings - simplified)
        # Find index
        idx = next((i for i, n in enumerate(flat_nodes) if n.get("node_id") == current_node_id), -1)
        if idx > 0:
            prev = flat_nodes[idx-1]
            context_parts.append(f"## Previous Context: {prev.get('node_name')}")
        if idx < len(flat_nodes) - 1:
            next_node = flat_nodes[idx+1]
            context_parts.append(f"## Next Concept: {next_node.get('node_name')}")

        return "\n\n".join(context_parts)

    def _flatten_nodes(self, nodes: List[Dict]) -> List[Dict]:
        result = []
        for node in nodes:
            result.append(node)
            if "children" in node and node["children"]:
                result.extend(self._flatten_nodes(node["children"]))
        return result


class UserMemoryManager:
    """
    Manages the 'Note Memory' - User Notes, Preferences, Progress, Mistakes.
    Focus: Personal learning behavior, error patterns, personalized strategies.
    """
    def __init__(self):
        pass

    def get_user_context(self, node_id: str) -> Dict[str, str]:
        """
        Retrieves user-specific context split by category.
        """
        annotations = storage.load_annotations()
        
        # 1. Specific Notes for this Node
        node_notes = [a for a in annotations if a.get("node_id") == node_id and a.get("source_type") in ["user", "user_saved"]]
        
        # 2. Mistakes / Weaknesses (Global)
        mistakes = [a for a in annotations if "错题" in a.get("anno_summary", "") or "mistake" in a.get("anno_summary", "").lower()]
        
        # 3. 最近的学习足迹（所有节点）
        recent_annotations = sorted(
            [a for a in annotations if a.get("timestamp")],
            key=lambda x: x.get("timestamp", ""),
            reverse=True
        )[:5]
        
        notes_text = ""
        if node_notes:
            notes_text = "\n".join([f"- {n.get('anno_summary')}: {n.get('answer', '')[:100]}..." for n in node_notes])
        
        mistakes_text = ""
        if mistakes:
            recent_mistakes = mistakes[-3:]
            mistakes_text = "\n".join([f"- {m.get('question')}" for m in recent_mistakes])
        
        # 构建学习足迹摘要
        learning_footprint = ""
        if recent_annotations:
            learning_footprint = "\n".join([
                f"- {a.get('anno_summary', '学习笔记')} ({a.get('node_id', '未知节点')})"
                for a in recent_annotations
            ])

        return {
            "notes": notes_text,
            "mistakes": mistakes_text,
            "learning_footprint": learning_footprint,
            "preferences": "User prefers detailed explanations with examples. Often asks about practical applications." # Placeholder for learned profile
        }


class LearningEffectEvaluator:
    """
    Evaluates the user's learning state based on interaction history.
    """
    def evaluate(self, history: List[Dict]) -> str:
        if not history:
            return "Neutral (New Session)"
            
        user_msgs = [msg['content'] for msg in history if msg.get('role') == 'user']
        ai_msgs = [msg['content'] for msg in history if msg.get('role') == 'assistant']
        
        if not user_msgs:
            return "Neutral"
            
        # Simple heuristic: Check for confusion keywords vs understanding keywords
        confusion_keywords = ["不懂", "难", "为什么", "error", "fail", "hard", "explain again", "困惑", "不明白", "不清楚"]
        understanding_keywords = ["明白", "懂了", "great", "thanks", "ok", "good", "清楚", "理解", "明白了"]
        exploration_keywords = ["如果", "假设", "能不能", "what if", "how about", "能否"]
        
        last_msg = user_msgs[-1].lower()
        
        # 计算对话深度
        avg_user_msg_length = sum(len(m) for m in user_msgs) / len(user_msgs) if user_msgs else 0
        
        if any(k in last_msg for k in confusion_keywords):
            return "Confused/Struggling - Needs simplified explanation"
        elif any(k in last_msg for k in understanding_keywords):
            return "Understanding - Ready for next step or deeper detail"
        elif any(k in last_msg for k in exploration_keywords):
            return "Exploring - Asking follow-up questions, showing curiosity"
        elif avg_user_msg_length > 100:
            return "Engaged - Detailed questions indicate deep engagement"
        elif len(user_msgs) > 5:
            return "Active Learning - Sustained conversation"
            
        return "Active Learning"
    
    def calculate_engagement_score(self, history: List[Dict]) -> Dict:
        """计算用户参与度评分"""
        if not history:
            return {"score": 0, "level": "none"}
        
        user_msgs = [msg for msg in history if msg.get('role') == 'user']
        
        # 计算指标
        message_count = len(user_msgs)
        avg_length = sum(len(m.get('content', '')) for m in user_msgs) / message_count if message_count > 0 else 0
        question_ratio = sum(1 for m in user_msgs if '?' in m.get('content', '') or '？' in m.get('content', '')) / message_count if message_count > 0 else 0
        
        # 综合评分 (0-100)
        score = min(100, message_count * 10 + avg_length / 10 + question_ratio * 20)
        
        level = "low"
        if score > 70:
            level = "high"
        elif score > 40:
            level = "medium"
        
        return {
            "score": round(score, 1),
            "level": level,
            "message_count": message_count,
            "avg_message_length": round(avg_length, 1),
            "question_ratio": round(question_ratio, 2)
        }


class KnowledgeMigrationManager:
    """
    Controls knowledge migration: Finding related concepts from other parts of the user's notes
    to help explain the current concept.
    """
    def find_related_knowledge(self, current_node_id: str, query: str) -> str:
        # In a real system, this would use vector search on all user notes.
        # Here we mock a simple keyword search across all annotations.
        annotations = storage.load_annotations()
        
        # Simple keyword matching from query against other notes
        keywords = [w for w in query.split() if len(w) > 1]
        related = []
        
        for anno in annotations:
            if anno.get("node_id") == current_node_id:
                continue # Skip current node notes (handled by UserMemory)
                
            summary = anno.get("anno_summary", "")
            content = anno.get("answer", "")
            
            score = 0
            for k in keywords:
                if k in summary or k in content:
                    score += 1
            
            if score > 0:
                related.append(f"Related Note ({summary}): {content[:50]}...")
                
        if related:
            return "\n".join(related[:3]) # Limit to top 3
        return ""


class ContextCompressor:
    """
    Smart Context Management & Compression.
    Implements strategies to balance Memory Length vs Model Performance.
    """
    def __init__(self, max_history_tokens=2000):
        self.max_history_tokens = max_history_tokens

    def _estimate_tokens(self, text: str) -> int:
        # Rough estimation: 1 token ~= 1.5 chars for Chinese/English mix
        # This is faster than real tokenization
        return len(text) // 1.5

    def compress_history(self, history: List[Dict]) -> List[Dict]:
        """
        Compresses conversation history using 'Rolling Window with Summary' strategy.
        Preserves:
        1. System instructions (if any)
        2. The most recent N messages (Recency bias)
        3. A condensed summary of older messages (Long-term memory)
        """
        if not history:
            return []

        # 1. Calculate total tokens
        total_text = "".join([str(msg.get('content', '')) for msg in history])
        total_tokens = self._estimate_tokens(total_text)

        # If within limits, return as is
        if total_tokens < self.max_history_tokens:
            return history

        logger.info(f"Compressing history: {total_tokens} tokens -> Target: {self.max_history_tokens}")

        # 2. Strategy: Keep last 5 messages intact, summarize the rest
        # Assuming the first message might be system prompt? 
        # In this app, history passed from frontend usually starts with user/ai pair.
        
        keep_count = 5
        if len(history) <= keep_count:
            return history # Can't compress much if message count is low but tokens are high (huge messages)
            # In that case, we might need to truncate individual message content (not implemented here for safety)

        recent_history = history[-keep_count:]
        older_history = history[:-keep_count]

        # 3. Create Summary
        # We need to call LLM asynchronously. Since this method might be called in a sync context or 
        # inside an async flow where we want to await, we need to handle it carefully.
        # However, to avoid circular imports and complex async injection here, we will define a protocol.
        # Actually, let's inject the summarizer function if possible, or use a callback.
        
        # For this MVP, we will rely on the caller (DualMemoryController) to handle the async summarization 
        # OR we can make this method async. Let's make it async.
        pass

    async def compress_history_async(self, history: List[Dict], summarizer_func) -> List[Dict]:
        """
        Async version that uses an external summarizer function (LLM).
        
        增强版：智能识别重要消息，保留关键转折点
        """
        if not history:
            return []

        # 1. Calculate total tokens
        total_text = "".join([str(msg.get('content', '')) for msg in history])
        total_tokens = self._estimate_tokens(total_text)

        if total_tokens < self.max_history_tokens:
            return history

        logger.info(f"Compressing history (LLM): {total_tokens} tokens -> Target: {self.max_history_tokens}")

        # 2. 智能选择要保留的消息
        # 策略：保留最近的消息 + 重要的历史节点（如主题转换、关键问题）
        keep_count = 5
        if len(history) <= keep_count:
            return history

        recent_history = history[-keep_count:]
        older_history = history[:-keep_count]
        
        # 识别重要的历史节点（用户提问、主题转换）
        important_indices = []
        for i, msg in enumerate(older_history):
            content = msg.get('content', '')
            # 标记重要消息：问题、长回复、包含关键转折词
            if msg.get('role') == 'user' and ('?' in content or '？' in content or len(content) > 100):
                important_indices.append(i)
        
        # 保留部分重要消息（最多3条）
        important_messages = []
        if important_indices:
            # 均匀选择重要节点
            step = max(1, len(important_indices) // 3)
            selected_indices = important_indices[::step][:3]
            important_messages = [older_history[i] for i in selected_indices]

        # 对剩余的历史进行摘要
        history_to_summarize = [h for i, h in enumerate(older_history) if i not in important_indices]
        
        summary_text = "Previous conversation summary: "
        if history_to_summarize:
            try:
                summary_content = await summarizer_func(history_to_summarize)
                summary_text += summary_content
            except Exception as e:
                logger.error(f"Summarization failed: {e}")
                summary_text += " (Auto-summary unavailable)"
        else:
            summary_text += " (Key points preserved in detail)"

        summary_message = {
            "role": "system", 
            "content": f"Context Summary: {summary_text}"
        }

        return [summary_message] + important_messages + recent_history


class DualMemoryController:
    """
    Orchestrates the collaboration between Content and User memory spaces.
    Implements:
    - Memory Retrieval Optimization
    - Context Switching Mechanism
    - Knowledge Migration Control
    - Learning Effect Evaluation
    - Context Compression (NEW)
    - Conversation Topic Tracking (NEW)
    - Long-term Memory (NEW)
    """
    def __init__(self):
        self.content_memory = ContentMemoryManager()
        self.user_memory = UserMemoryManager()
        self.evaluator = LearningEffectEvaluator()
        self.migration_manager = KnowledgeMigrationManager()
        self.compressor = ContextCompressor()
        self.topic_tracker = ConversationTopicTracker()
        self.long_term_memory = LongTermMemoryManager()
        
        # 加载持久化的长期记忆
        self.long_term_memory.load_persisted_memories()

    def build_tutor_prompt(self, course_id: str, node_id: str, query: str, history: List[Dict]) -> str:
        # 1. Retrieve Core Contexts (Dual Memory Spaces)
        content_context = self.content_memory.get_course_context(course_id, node_id)
        user_data = self.user_memory.get_user_context(node_id)
        
        # 2. Evaluate Learning State
        learning_state = self.evaluator.evaluate(history)
        engagement = self.evaluator.calculate_engagement_score(history)
        
        # 3. Knowledge Migration (Cross-reference)
        related_knowledge = self.migration_manager.find_related_knowledge(node_id, query)
        
        # 4. 检索长期记忆
        long_term_memories = self.long_term_memory.get_relevant_memories(course_id, node_id, query)
        long_term_context = ""
        if long_term_memories:
            long_term_context = "\n".join([
                f"- Previous Session ({m.get('timestamp', 'unknown')[:10]}): {m.get('summary', '')}"
                for m in long_term_memories
            ])
        
        # 5. 检测主题变化
        topic_shift_detected = False
        current_topic = "general"
        if history:
            topic_shift_detected, current_topic = self.topic_tracker.detect_topic_shift(
                query, history[:-1] if history else []
            )
        
        # 6. Context Switching Logic (Dynamic Persona Adjustment)
        instruction_tone = "balanced"
        if "Confused" in learning_state:
            instruction_tone = "supportive and simplified"
        elif "Understanding" in learning_state:
            instruction_tone = "challenging and deep"
        elif "Exploring" in learning_state:
            instruction_tone = "encouraging and expansive"
        
        # 7. 提取关键实体
        key_entities = self.topic_tracker.extract_key_entities(history[-5:] if history else [])
        
        # 8. Construct System Prompt
        topic_shift_notice = ""
        if topic_shift_detected:
            topic_shift_notice = f"\n**Note**: User has shifted to a new topic ({current_topic}). Acknowledge this transition naturally."
            
        system_prompt = f"""
You are an AI Private Tutor equipped with an advanced "Dual Memory" system with enhanced context awareness.

=== MEMORY SPACE 1: CONTENT MEMORY (Academic Context) ===
{content_context}

=== MEMORY SPACE 2: USER MEMORY (Personal Context) ===
- Notes on this Topic:
{user_data['notes'] if user_data.get('notes') else "None"}
- Recent Weaknesses/Mistakes:
{user_data['mistakes'] if user_data.get('mistakes') else "None"}
- Learning Footprint (Recent Activity):
{user_data.get('learning_footprint', 'None')}
- Learning Profile: {user_data.get('preferences', 'Default')}

=== LONG-TERM MEMORY (Cross-Session Context) ===
{long_term_context if long_term_context else "No previous sessions recorded for this topic."}

=== DYNAMIC ANALYSIS ===
- Current Learning State: {learning_state}
- Engagement Level: {engagement['level']} (Score: {engagement['score']}/100)
- Current Topic Category: {current_topic}
- Key Concepts in Discussion: {', '.join(key_entities) if key_entities else 'None identified'}
- Related Knowledge from other topics:
{related_knowledge if related_knowledge else "None"}
{topic_shift_notice}

=== INSTRUCTION STRATEGY ===
1. **Tone**: Adopt a {instruction_tone} tone based on the user's state.
2. **Synthesize**: Combine academic knowledge with the user's notes. If they have a note about X, reference it.
3. **Memory Recall**: If long-term memory shows previous learning on this topic, reference it: "As we discussed before..."
4. **Migration**: If related knowledge is provided, use it to build analogies (e.g., "Recall when you learned about...").
5. **Correction**: If the user has made similar mistakes before (listed in Weaknesses), proactively warn them.
6. **Engagement Adaptation**: User engagement is {engagement['level']}. {'Provide more interactive elements' if engagement['level'] == 'low' else 'Maintain depth and challenge' if engagement['level'] == 'high' else 'Balance guidance and exploration'}.
7. **Goal**: Answer the user's query: "{query}" effectively.

=== TEACHER BEHAVIOR (CRITICAL) ===
You act like a real teacher opening a textbook.
1. **LOCATE**: You MUST try to find a specific sentence or paragraph in the "CONTENT MEMORY" that directly answers or relates to the question.
2. **QUOTE**: In the metadata `quote` field, you MUST return this exact text snippet. This will trigger a "Highlight" in the user's interface, like a teacher drawing a line in the book.
3. **EXPLAIN**: Your verbal answer should explain *why* this text is important, expanding on it.
4. **SUMMARIZE**: Your `anno_summary` metadata should be a concise note title (e.g. "Key Definition of X") that captures the essence for the student's notebook.
5. **CONTINUITY**: If this is a follow-up question, explicitly connect to previous points: "Building on what we just discussed about [topic]..."

Answer the user's question now.
"""
        return system_prompt

    async def optimize_history(self, history: List[Dict], summarizer_func=None) -> List[Dict]:
        """
        Public API to compress history.
        Now async to support LLM summarization.
        """
        if summarizer_func:
             return await self.compressor.compress_history_async(history, summarizer_func)
        return self.compressor.compress_history(history)
    
    def save_session_memory(self, course_id: str, node_id: str, 
                           history: List[Dict], summary: str = ""):
        """
        保存会话记忆到长期存储
        """
        if not history or len(history) < 2:
            return
        
        # 提取关键信息
        key_concepts = self.topic_tracker.extract_key_entities(history)
        
        # 识别用户的独特见解（较长的用户消息可能包含思考）
        user_insights = []
        for msg in history:
            if msg.get('role') == 'user' and len(msg.get('content', '')) > 50:
                user_insights.append(msg.get('content', '')[:100] + "...")
        
        # 评估难度级别
        engagement = self.evaluator.calculate_engagement_score(history)
        difficulty_level = "beginner" if engagement['score'] < 40 else "advanced" if engagement['score'] > 70 else "intermediate"
        
        # 如果没有提供摘要，生成一个简单的
        if not summary:
            summary = f"Session with {engagement['message_count']} exchanges on {len(key_concepts)} key concepts."
        
        self.long_term_memory.save_conversation_memory(
            course_id, node_id, summary, key_concepts, user_insights, difficulty_level
        )


memory_controller = DualMemoryController()