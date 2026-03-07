"""
AI 问答服务模块

负责苏格拉底式导师对话、流式问答、
笔记摘要、对话总结和历史摘要。
"""

import logging
from typing import List, Dict

from ai_base import AIBase
from prompts import get_prompt

logger = logging.getLogger(__name__)


class AIQAService(AIBase):
    """问答与聊天相关的 AI 服务"""

    async def socratic_tutor(
        self,
        user_message: str,
        course_context: str,
        current_node: Dict,
        relevant_content: str,
        user_notes: str,
        chat_history: List[Dict],
        user_id: str = "default",
        learning_stage: str = "exploring"
    ):
        """
        增强版苏格拉底式AI导师 - 启发式教学
        """
        # 使用DualMemoryController构建提示词
        from memory import DualMemoryController
        memory_controller = DualMemoryController(course_context, current_node, chat_history)
        system_prompt = memory_controller.build_socratic_prompt(user_id)
        
        # 分析用户意图和学习状态
        intent_analysis = self._analyze_user_intent(user_message, chat_history)
        
        # 格式化用户上下文
        context_text = f"""
当前学习章节：{current_node.get('node_name', '未知章节')}
章节内容：
{relevant_content[:1000]}

用户笔记：
{user_notes[:500] if user_notes else '暂无笔记'}

学习阶段：{learning_stage}
用户意图：{intent_analysis['intent']}
理解程度：{intent_analysis['comprehension_level']}

用户问题：{user_message}
"""
        
        prompt_template = get_prompt("socratic_tutor")
        user_prompt = prompt_template.format(context=context_text)
        
        # 添加结构化输出要求
        structured_prompt = f"""{user_prompt}

请以以下结构化格式输出：
1. **思考引导**：提出启发性问题引导用户思考
2. **知识关联**：关联已学知识和新概念
3. **实例说明**：提供具体例子帮助理解
4. **反思问题**：提出反思性问题加深理解
5. **下一步建议**：建议用户接下来可以做什么

输出要求：
- 使用Markdown格式
- 每个部分用 ### 标题分隔
- 包含至少2-3个启发性问题
- 提供1个具体实例
"""
        
        async for chunk in self._stream_llm(structured_prompt, system_prompt):
            yield chunk
    
    def _analyze_user_intent(self, user_message: str, chat_history: List[Dict]) -> Dict:
        """
        分析用户意图和理解程度
        """
        message_lower = user_message.lower()
        
        # 意图识别
        intents = {
            'question': any(kw in message_lower for kw in ['为什么', '怎么', '如何', '什么', '?', '吗']),
            'confirmation': any(kw in message_lower for kw in ['对吗', '是不是', '是否正确', '理解']),
            'example_request': any(kw in message_lower for kw in ['例子', '举例', '示例', '比如']),
            'explanation_request': any(kw in message_lower for kw in ['解释', '说明', '详细', '展开']),
            'application': any(kw in message_lower for kw in ['应用', '使用', '实践', '做', '实现']),
        }
        
        # 确定主要意图
        primary_intent = 'general'
        for intent, detected in intents.items():
            if detected:
                primary_intent = intent
                break
        
        # 评估理解程度（基于历史对话长度和复杂度）
        history_length = len(chat_history)
        if history_length < 3:
            comprehension = "beginner"
        elif history_length < 8:
            comprehension = "intermediate"
        else:
            comprehension = "advanced"
        
        return {
            'intent': primary_intent,
            'comprehension_level': comprehension,
            'details': intents
        }

    async def answer_question_stream(
        self,
        question: str,
        context: str,
        history: List[dict] = [],
        selection: str = "",
        user_persona: str = "",
        course_id: str = None,
        node_id: str = None,
        user_notes: str = "",
        session_metrics: dict = None,
        enable_long_term_memory: bool = False
    ):
        """
        流式回答用户问题 - 带元数据
        """
        system_prompt = ""
        
        # Build session context from metrics if available
        session_context = ""
        if session_metrics and enable_long_term_memory:
            # Process question types
            q_types_dict = session_metrics.get('question_types', {})
            q_types_list = []
            if isinstance(q_types_dict, dict):
                for k, v in q_types_dict.items():
                    if v > 0:
                        q_types_list.append(f"{k} ({v})")
            
            topics = session_metrics.get('topics_discussed', [])
            if not isinstance(topics, list):
                topics = []

            session_context = f"""
=== 会话上下文感知 ===
本次会话统计：
- 总消息数：{session_metrics.get('total_messages', 0)}
- 用户消息：{session_metrics.get('user_messages', 0)}
- AI消息：{session_metrics.get('ai_messages', 0)}
- 会话时长：{session_metrics.get('session_duration_minutes', 0)} 分钟
- 讨论主题：{', '.join(topics)}
- 主要问题类型：{', '.join(q_types_list)}

请根据以上会话背景，保持回答的连贯性和上下文一致性。
"""
        
        # Try to use Dual Memory System if context is available
        if course_id and node_id:
            try:
                # Local import to avoid circular dependency if any
                from memory import memory_controller
                
                # 1. Optimize History (Context Compression)
                # Pass the summarizer method from this instance to avoid circular dependency
                optimized_history = await memory_controller.optimize_history(history, self.summarize_history)
                
                # 2. Build Dual Memory Prompt
                system_prompt = memory_controller.build_tutor_prompt(course_id, node_id, question, optimized_history)
                
                # Add session context if available
                if session_context:
                    system_prompt += session_context
                
                # Use optimized history for prompt construction
                history = optimized_history
                
                # Append the metadata instruction which is critical for frontend parsing
                # We inject the current node_id as default if AI doesn't find a better one
                system_prompt += f"""

=== METADATA OUTPUT RULE (MANDATORY) ===
You MUST output the metadata at the very end of your response.

**Format**:
[Your Answer Content Here]

---METADATA---
{{"node_id": "{node_id}", "quote": "quote from text if any", "anno_summary": "Core knowledge points summary in Markdown bullet points (3-5 points)"}}

DO NOT wrap the JSON in markdown code blocks.
"""
            except Exception as e:
                logger.error(f"Dual Memory Error: {e}")
                # Fallback will be handled below
        
        if not system_prompt:
            # Fallback / Standard Prompt
            system_prompt = f"""
你是学术助手，请根据提供的课程内容、对话历史和选中的文本回答用户的问题。

**用户画像（个性化设定）**：
{user_persona if user_persona else "通用学习者"}
请根据用户画像调整你的回答风格、深度和举例方式。例如，如果用户是初学者，请多用生活类比；如果是专家，请深入底层原理。

{session_context if session_context else ""}

**核心任务**：
1. **回答问题**：直接、专业、简洁地回答用户问题。
2. **定位上下文**：识别答案关联的课程章节或原文。
3. **格式化输出**：
   - **表格**：凡是涉及对比、数据列举、步骤说明的内容，**必须使用 Markdown 表格**展示。
   - **图表**：凡是涉及流程、架构、思维导图的内容，**必须使用 Mermaid 代码块**展示。
   - **代码**：代码片段请使用标准代码块。

**教师模式（TEACHER MODE - 增强版）**：
请像一位真实的苏格拉底式导师（Socratic Tutor）一样：
1. **启发式教学**：
   - 不要直接给出一层不变的答案。
   - 回答完问题后，**必须**主动提出一个相关的、有深度的后续问题（Follow-up Question），引导用户进一步思考。
   - 问题应该基于当前的知识点，或者是将理论联系实际的场景题。
2. **关联记忆（Memory Recall）**：
   - 如果用户之前问过类似问题或犯过类似错误（参考对话历史），请在回答中明确指出："正如我们之前讨论的..."或"注意不要混淆..."。
3. **定位原文（Locate）**：
   - 尽量在提供的课程内容中找到能够支持你回答的**原句**。
   - 将找到的原句放入 metadata 的 `quote` 字段中。前端界面会自动高亮显示这句话，就像老师在课本上划线一样。
   - 如果找不到精确原句，不要编造。
4. **总结笔记（Note Taking）**：
   - 在 `anno_summary` 中生成一个核心知识点概括（Markdown 列表，3-5点），方便用户快速回顾。

**创新想法捕捉（Innovation Capture）**：
- 如果用户提出了新的解法、思路或独特的见解，请予以积极反馈。
- 帮助用户完善思路，并标记这是一个"创新想法"。
- 在 metadata 的 `anno_summary` 中，使用 `💡 想法：` 开头。

**输出格式规范（严格执行）**：
为了支持流式输出和后续处理，输出必须分为两部分，用 `---METADATA---` 分隔。

**第一部分：回答正文**
- 直接输出 Markdown 格式的回答内容。
- **表格支持（强制要求）**：凡是涉及对比（VS）、参数列表、步骤说明或数据展示的内容，**必须**使用 Markdown 表格呈现。
- **图表支持（强烈推荐）**：凡是涉及流程、时序、类关系或思维导图，请使用 Mermaid 代码块（```mermaid ... ```）展示。
- **严禁**将整个回答包裹在代码块中。
- 回答结束后，**另起一段**，用加粗字体写出你的后续提问：**思考题：...**

**第二部分：元数据**
- 正文结束后，**另起一行**输出分隔符：`---METADATA---`
- 紧接着输出一个标准的 JSON 对象（不要用 markdown 代码块包裹），包含：
  - `node_id`: (string) 答案主要参考的章节ID。如果无法确定，返回 null。
  - `quote`: (string) 答案引用的原文片段（必须是原文中存在的句子）。如果没有引用，返回 null。
  - `anno_summary`: (string) 核心知识点概括，使用 Markdown 无序列表格式（3-5点）。

**示例**：
什么是递归？
递归是指函数调用自身的编程技巧...（解释内容）

**思考题：你能想到生活中有什么现象是类似于递归的吗？**

---METADATA---
{{"node_id": "uuid-123", "quote": "递归是...", "anno_summary": "递归的概念"}}
"""

        # Build prompt
        history_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in history[-5:]])
        
        prompt = f"""
课程内容片段（正文知识）：
{context}

用户笔记（学习足迹）：
{user_notes if user_notes else "无"}

对话历史：
{history_text}

选中内容（用户针对这段文字提问）：
{selection if selection else "无"}

用户问题：{question}

请开始回答（记得在最后附加元数据）：
"""
        async for chunk in self._stream_llm(prompt, system_prompt):
            yield chunk

    async def summarize_note(self, content: str) -> str:
        """
        生成笔记摘要/标题
        """
        system_prompt = get_prompt("summarize_note").format()
        
        # If content contains Q&A structure, try to summarize the Question primarily
        prompt = f"笔记内容：\n{content[:2000]}\n\n请生成标题："
        
        # Use Fast Model
        response = await self._call_llm(prompt, system_prompt, use_fast_model=True)
        return response if response else (content[:20] + "...")

    async def summarize_chat(
        self,
        history: List[dict],
        course_context: str = "",
        user_persona: str = ""
    ) -> Dict:
        """
        生成对话复盘总结
        """
        system_prompt = get_prompt("summarize_chat").format(
            user_persona=user_persona if user_persona else "通用学习者"
        )
        
        # Convert history to text
        history_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in history])
        
        prompt = f"课程背景：\n{course_context}\n\n对话历史：\n{history_text}\n\n请生成详细的复盘报告，确保内容丰富充实："
        
        # Use standard model for better quality summary
        response = await self._call_llm(prompt, system_prompt, use_fast_model=False)
        if response:
            return self._extract_json(response) or {"title": "对话总结", "content": response}
        return {"title": "总结失败", "content": "无法生成总结。"}

    async def summarize_history(self, history: List[Dict]) -> str:
        """
        总结对话历史
        """
        system_prompt = get_prompt("summarize_history").format()
        history_text = "\n".join([f"{msg.get('role', 'unknown')}: {msg.get('content', '')}" for msg in history])
        
        prompt = f"Please summarize the following conversation:\n\n{history_text}"
        
        # Use Fast Model for summarization
        response = await self._call_llm(prompt, system_prompt, use_fast_model=True)
        return response if response else "Previous conversation summary (auto-generated failed)."
