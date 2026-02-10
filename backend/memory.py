import logging
from typing import List, Dict, Optional
from datetime import datetime
from storage import storage

logger = logging.getLogger(__name__)

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
        
        notes_text = ""
        if node_notes:
            notes_text = "\n".join([f"- {n.get('anno_summary')}: {n.get('answer', '')[:100]}..." for n in node_notes])
        
        mistakes_text = ""
        if mistakes:
            recent_mistakes = mistakes[-3:]
            mistakes_text = "\n".join([f"- {m.get('question')}" for m in recent_mistakes])

        return {
            "notes": notes_text,
            "mistakes": mistakes_text,
            "preferences": "User prefers detailed explanations with examples. Often asks about practical applications." # Placeholder for learned profile
        }

class LearningEffectEvaluator:
    """
    Evaluates the user's learning state based on interaction history.
    """
    def evaluate(self, history: List[Dict]) -> str:
        if not history:
            return "Neutral (New Session)"
            
        user_msgs = [msg['content'] for msg in history if msg['role'] == 'user']
        if not user_msgs:
            return "Neutral"
            
        # Simple heuristic: Check for confusion keywords vs understanding keywords
        confusion_keywords = ["不懂", "难", "为什么", "error", "fail", "hard", "explain again"]
        understanding_keywords = ["明白", "懂了", "great", "thanks", "ok", "good"]
        
        last_msg = user_msgs[-1].lower()
        
        if any(k in last_msg for k in confusion_keywords):
            return "Confused/Struggling - Needs simplified explanation"
        if any(k in last_msg for k in understanding_keywords):
            return "Understanding - Ready for next step or deeper detail"
            
        return "Active Learning"

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
        """
        if not history:
            return []

        # 1. Calculate total tokens
        total_text = "".join([str(msg.get('content', '')) for msg in history])
        total_tokens = self._estimate_tokens(total_text)

        if total_tokens < self.max_history_tokens:
            return history

        logger.info(f"Compressing history (LLM): {total_tokens} tokens -> Target: {self.max_history_tokens}")

        keep_count = 5
        if len(history) <= keep_count:
            return history

        recent_history = history[-keep_count:]
        older_history = history[:-keep_count]

        # Call the injected summarizer function
        summary_text = "Previous conversation summary: "
        try:
            summary_content = await summarizer_func(older_history)
            summary_text += summary_content
        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            summary_text += " (Auto-summary unavailable)"

        summary_message = {
            "role": "system", 
            "content": f"Context Summary: {summary_text}"
        }

        return [summary_message] + recent_history

class DualMemoryController:
    """
    Orchestrates the collaboration between Content and User memory spaces.
    Implements:
    - Memory Retrieval Optimization
    - Context Switching Mechanism
    - Knowledge Migration Control
    - Learning Effect Evaluation
    - Context Compression (NEW)
    """
    def __init__(self):
        self.content_memory = ContentMemoryManager()
        self.user_memory = UserMemoryManager()
        self.evaluator = LearningEffectEvaluator()
        self.migration_manager = KnowledgeMigrationManager()
        self.compressor = ContextCompressor()

    def build_tutor_prompt(self, course_id: str, node_id: str, query: str, history: List[Dict]) -> str:
        # 1. Retrieve Core Contexts (Dual Memory Spaces)
        content_context = self.content_memory.get_course_context(course_id, node_id)
        user_data = self.user_memory.get_user_context(node_id)
        
        # 2. Evaluate Learning State
        learning_state = self.evaluator.evaluate(history)
        
        # 3. Knowledge Migration (Cross-reference)
        related_knowledge = self.migration_manager.find_related_knowledge(node_id, query)
        
        # 4. Context Switching Logic (Dynamic Persona Adjustment)
        instruction_tone = "balanced"
        if "Confused" in learning_state:
            instruction_tone = "supportive and simplified"
        elif "Understanding" in learning_state:
            instruction_tone = "challenging and deep"
            
        # 5. Construct System Prompt
        system_prompt = f"""
You are an AI Private Tutor equipped with a "Dual Memory" system.

=== MEMORY SPACE 1: CONTENT MEMORY (Academic Context) ===
{content_context}

=== MEMORY SPACE 2: USER MEMORY (Personal Context) ===
- Notes on this Topic:
{user_data['notes'] if user_data['notes'] else "None"}
- Recent Weaknesses/Mistakes:
{user_data['mistakes'] if user_data['mistakes'] else "None"}
- Learning Profile: {user_data['preferences']}

=== DYNAMIC ANALYSIS ===
- Current Learning State: {learning_state}
- Related Knowledge from other topics:
{related_knowledge if related_knowledge else "None"}

=== INSTRUCTION STRATEGY ===
1. **Tone**: Adopt a {instruction_tone} tone based on the user's state.
2. **Synthesize**: Combine academic knowledge with the user's notes. If they have a note about X, reference it.
3. **Migration**: If related knowledge is provided, use it to build analogies (e.g., "Recall when you learned about...").
4. **Correction**: If the user has made similar mistakes before (listed in Weaknesses), proactively warn them.
5. **Goal**: Answer the user's query: "{query}" effectively.

=== TEACHER BEHAVIOR (CRITICAL) ===
You act like a real teacher opening a textbook.
1. **LOCATE**: You MUST try to find a specific sentence or paragraph in the "CONTENT MEMORY" that directly answers or relates to the question.
2. **QUOTE**: In the metadata `quote` field, you MUST return this exact text snippet. This will trigger a "Highlight" in the user's interface, like a teacher drawing a line in the book.
3. **EXPLAIN**: Your verbal answer should explain *why* this text is important, expanding on it.
4. **SUMMARIZE**: Your `anno_summary` metadata should be a concise note title (e.g. "Key Definition of X") that captures the essence for the student's notebook.

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

memory_controller = DualMemoryController()