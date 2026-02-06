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
        pass

    def get_course_context(self, course_id: str, current_node_id: str) -> str:
        """
        Retrieves context for the current node, including:
        1. Current node content.
        2. Parent node context (if any).
        3. Previous/Next sibling context (brief).
        """
        course = storage.load_course(course_id)
        if not course:
            return ""

        nodes = course.get("nodes", [])
        flat_nodes = self._flatten_nodes(nodes)
        
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

class DualMemoryController:
    """
    Orchestrates the collaboration between Content and User memory spaces.
    Implements:
    - Memory Retrieval Optimization
    - Context Switching Mechanism
    - Knowledge Migration Control
    - Learning Effect Evaluation
    """
    def __init__(self):
        self.content_memory = ContentMemoryManager()
        self.user_memory = UserMemoryManager()
        self.evaluator = LearningEffectEvaluator()
        self.migration_manager = KnowledgeMigrationManager()

    def build_tutor_prompt(self, course_id: str, node_id: str, query: str, history: List[Dict]) -> str:
        # 1. Retrieve Core Contexts (Dual Memory Spaces)
        content_context = self.content_memory.get_course_context(course_id, node_id)
        user_data = self.user_memory.get_user_context(node_id)
        
        # 2. Evaluate Learning State
        learning_state = self.evaluator.evaluate(history)
        
        # 3. Knowledge Migration (Cross-reference)
        related_knowledge = self.migration_manager.find_related_knowledge(node_id, query)
        
        # 4. Context Switching Logic (Dynamic Persona Adjustment)
        # If user is confused, emphasize User Memory (mistakes, preferences) and simplify Content.
        # If user is advanced, emphasize Content Memory (depth) and reduce hand-holding.
        
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

memory_controller = DualMemoryController()
