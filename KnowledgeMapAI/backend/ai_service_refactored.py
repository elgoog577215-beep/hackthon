"""
AI Service - Refactored version using centralized prompt management.

This is a demonstration of how to use the new prompts.py module.
To use this refactored version, rename this file to ai_service.py
or integrate the changes into the existing ai_service.py
"""

import uuid
import random
import os
import json
import re
import logging
from dotenv import load_dotenv
from openai import AsyncOpenAI
from typing import List, Dict, Optional

# Import prompt templates
from prompts import (
    get_prompt,
    TUTOR_SYSTEM_BASE,
    TUTOR_METADATA_RULE,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


class AIService:
    """AI Service with centralized prompt management."""
    
    def __init__(self):
        # Configure API Key via environment variable
        self.api_key = os.getenv("AI_API_KEY")
        self.api_base = os.getenv("AI_API_BASE", "https://api-inference.modelscope.cn/v1")
        
        # Hybrid Model Strategy
        self.model_smart = os.getenv("AI_MODEL", "Qwen/Qwen2.5-72B-Instruct")
        self.model_fast = os.getenv("AI_MODEL_FAST", "Qwen/Qwen2.5-7B-Instruct")
        
        self.client = AsyncOpenAI(
            base_url=self.api_base,
            api_key=self.api_key,
        )

    def _extract_json(self, text: str) -> Optional[Dict]:
        """Robust JSON extraction from LLM response."""
        logger.info(f"Raw AI Response for JSON extraction: {text[:200]}...")

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try markdown JSON block
        json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError as e:
                logger.warning(f"Markdown JSON decode error: {e}")

        # Try any code block
        code_match = re.search(r'```\s*(.*?)\s*```', text, re.DOTALL)
        if code_match:
            try:
                return json.loads(code_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find JSON between braces
        try:
            start_idx = text.find('{')
            end_idx = text.rfind('}')
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                json_str = text[start_idx:end_idx+1]
                return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(f"Substring JSON decode error: {e}")

        logger.warning(f"Failed to extract JSON from: {text[:500]}...")
        return None

    def _clean_mermaid_syntax(self, text: str) -> str:
        """Fix common Mermaid syntax errors."""
        pattern = r'```mermaid(.*?)```'
        
        def fix_mermaid_block(match):
            content = match.group(1)
            
            def quote_if_needed(text, type_char):
                if text.startswith('"') and text.endswith('"'):
                    return text
                text = text.replace('"', '\\"')
                return f'"{text}"'
            
            lines = content.split('\n')
            fixed_lines = []
            
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    fixed_lines.append(line)
                    continue
                    
                # Skip comments and keywords
                if stripped.startswith('%') or stripped in ['graph TD', 'graph LR', 'flowchart TD']:
                    fixed_lines.append(line)
                    continue
                
                # Fix node definitions
                if '[' in stripped and ']' in stripped:
                    parts = stripped.split('[')
                    if len(parts) == 2:
                        node_id = parts[0].strip()
                        rest = parts[1]
                        
                        if ']' in rest:
                            inner_content = rest.split(']')[0]
                            after_bracket = rest.split(']', 1)[1] if ']' in rest else ''
                            
                            if not (inner_content.startswith('"') and inner_content.endswith('"')):
                                inner_content = inner_content.replace('"', '\\"')
                                inner_content = f'"{inner_content}"'
                            
                            fixed_line = line.replace(
                                f'[{rest.split("]")[0]}]',
                                f'[{inner_content}]'
                            )
                            fixed_lines.append(fixed_line)
                            continue
                
                fixed_lines.append(line)
            
            return '```mermaid' + '\n'.join(fixed_lines) + '```'
        
        return re.sub(pattern, fix_mermaid_block, text, flags=re.DOTALL)

    def clean_response_text(self, text: str) -> str:
        """Clean and normalize AI response text."""
        if not text:
            return ""
        
        # Remove think tags
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        text = re.sub(r'---\s*Thinking\s*---.*?---\s*End Thinking\s*---', '', text, flags=re.DOTALL)
        
        # Fix Mermaid syntax
        text = self._clean_mermaid_syntax(text)
        
        # Normalize whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text.strip()

    async def _call_llm(self, prompt: str, system_prompt: str = "You are a helpful assistant.", use_fast_model: bool = False) -> str:
        """Generic function to call LLM."""
        if not self.api_key:
            logger.warning("AI Service not configured - returning None")
            return None

        try:
            extra_body = {"enable_thinking": True}
            model_id = self.model_fast if use_fast_model else self.model_smart

            logger.info(f"Calling AI API (Model: {model_id}, Fast: {use_fast_model})")
            
            response = await self.client.chat.completions.create(
                model=model_id,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                stream=True,
                extra_body=extra_body
            )
            
            full_content = ""
            async for chunk in response:
                if chunk.choices and chunk.choices[0].delta:
                    if hasattr(chunk.choices[0].delta, 'reasoning_content') and chunk.choices[0].delta.reasoning_content:
                        reasoning = chunk.choices[0].delta.reasoning_content
                        if reasoning:
                            print(reasoning, end='', flush=True)
                            
                    delta = chunk.choices[0].delta
                    if delta.content:
                        full_content += delta.content
            
            logger.info(f"AI Response Complete (Model: {model_id})")
            return full_content
        except Exception as e:
            logger.error(f"AI API Call Error: {e}")
            return None

    async def _stream_llm(self, prompt: str, system_prompt: str = "You are a helpful assistant.", use_fast_model: bool = False):
        """Generator function to stream LLM response chunks."""
        if not self.api_key:
            yield "AI Service not configured."
            return

        try:
            extra_body = {"enable_thinking": True}
            model_id = self.model_fast if use_fast_model else self.model_smart

            response = await self.client.chat.completions.create(
                model=model_id,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                stream=True,
                extra_body=extra_body
            )
            
            async for chunk in response:
                if chunk.choices:
                    if hasattr(chunk.choices[0].delta, 'reasoning_content') and chunk.choices[0].delta.reasoning_content:
                        reasoning = chunk.choices[0].delta.reasoning_content
                        if reasoning:
                            print(reasoning, end='', flush=True)
                            
                    delta = chunk.choices[0].delta
                    if delta.content:
                        yield delta.content
                        
        except Exception as e:
            logger.error(f"AI Stream Error: {e}")
            yield f"\n\n[Error: AI服务调用失败 - {str(e)}]"

    # ========================================================================
    # REFACTORED METHODS USING CENTRALIZED PROMPTS
    # ========================================================================

    async def generate_course(self, keyword: str, difficulty: str = "medium", style: str = "academic", requirements: str = "") -> Dict:
        """Generate course structure using centralized prompt."""
        prompt_template = get_prompt("generate_course")
        system_prompt = prompt_template.format(
            difficulty=difficulty,
            style=style,
            requirements=requirements if requirements else "无"
        )
        prompt = f"用户想要学习"{keyword}"，请生成一份专业且系统的课程大纲。"
        
        response = await self._call_llm(prompt, system_prompt)
        if response:
            return self._extract_json(response)
        return {"course_name": keyword, "nodes": []}

    async def generate_quiz(self, content: str, node_name: str = "", difficulty: str = "medium", style: str = "standard", user_persona: str = "", question_count: int = 3) -> List[Dict]:
        """Generate quiz using centralized prompt."""
        prompt_template = get_prompt("generate_quiz")
        system_prompt = prompt_template.format(
            difficulty=difficulty,
            style=style,
            question_count=question_count
        )
        
        content_text = content if content and len(content) >= 50 else f"Topic: {node_name}\n(详细内容缺失，请基于该主题生成通用问题)"
        
        prompt = f"Content:\n{content_text}\n\n请生成恰好 {question_count} 道 JSON 格式的题目。"
        
        response = await self._call_llm(prompt, system_prompt)
        if response:
            result = self._extract_json(response)
            if result:
                return result if isinstance(result, list) else result.get("questions", [])
        
        # Fallback questions
        return [
            {
                "id": i + 1,
                "question": f"关于 {node_name} 的问题 {i+1}",
                "options": ["选项 A", "选项 B", "选项 C", "选项 D"],
                "correct_index": 0,
                "explanation": f"这是 {node_name} 的基础概念解释。"
            }
            for i in range(question_count)
        ]

    async def generate_sub_nodes(self, node_name: str, node_level: int, node_id: str, course_name: str = "", parent_context: str = "") -> List[Dict]:
        """Generate sub-nodes using centralized prompt."""
        prompt_template = get_prompt("generate_sub_nodes")
        system_prompt = prompt_template.format(
            course_name=course_name if course_name else "未知课程",
            parent_context=parent_context if parent_context else "无"
        )
        
        prompt = f"当前节点信息：名称={node_name}，层级={node_level}。请列出该章节下的所有子小节。"
        
        response = await self._call_llm(prompt, system_prompt)
        new_level = node_level + 1
        
        if response:
            data = self._extract_json(response)
            if data:
                return [
                    {
                        "node_id": str(uuid.uuid4()),
                        "parent_node_id": node_id,
                        "node_name": item.get("node_name", "新节点"),
                        "node_level": new_level,
                        "node_content": item.get("node_content", ""),
                        "node_type": "custom"
                    }
                    for item in data.get("sub_nodes", [])
                ]
        
        # Fallback
        return [
            {"node_id": str(uuid.uuid4()), "parent_node_id": node_id, "node_name": f"{node_name} - 子节点 {i+1}", "node_level": new_level, "node_content": "", "node_type": "custom"}
            for i in range(2)
        ]

    async def generate_content_stream(self, node_name: str, original_content: str = "", course_context: str = "", previous_context: str = "", requirement: str = ""):
        """Stream content generation using centralized prompt."""
        prompt_template = get_prompt("generate_content")
        system_prompt = prompt_template.format()
        
        prompt = f"""
全书大纲：
{course_context}

上文摘要（用于承接）：
{previous_context}

当前章节标题：{node_name}
原始简介（参考）：{original_content}
用户额外需求：{requirement}

请开始撰写（记得包含 <!-- BODY_START --> 分隔符）：
"""
        async for chunk in self._stream_llm(prompt, system_prompt):
            yield chunk

    async def redefine_content(self, node_name: str, requirement: str, original_content: str = "", course_context: str = "", previous_context: str = "") -> str:
        """Refine content using centralized prompt."""
        prompt_template = get_prompt("redefine_content")
        system_prompt = prompt_template.format()
        
        prompt_parts = [f"当前章节标题：{node_name}"]
        if course_context:
            prompt_parts.append(f"全书大纲：\n{course_context}")
        if previous_context:
            prompt_parts.append(f"上文摘要：\n{previous_context}")
        if original_content:
            prompt_parts.append(f"原始简介（参考）：\n{original_content}")
            
        prompt_parts.append(f"用户额外需求：{requirement}（请保持专业、简洁、流畅，适合大学生阅读）")
        prompt_parts.append("请开始撰写正文：")
        
        prompt = "\n\n".join(prompt_parts)
        
        response = await self._call_llm(prompt, system_prompt)
        if response:
            return self.clean_response_text(response)
                
        return f"基于需求 '{requirement}' 重定义的 {node_name} 内容。\n\n1. 核心点一：...\n2. 核心点二：..."

    async def extend_content(self, node_name: str, requirement: str) -> str:
        """Extend content using centralized prompt."""
        prompt_template = get_prompt("extend_content")
        system_prompt = prompt_template.format()
        
        prompt = f"当前章节：{node_name}\n拓展方向：{requirement}"

        response = await self._call_llm(prompt, system_prompt)
        if response:
            return self.clean_response_text(response)

        return f"拓展知识点：\n关于 {node_name} 的延伸阅读... {requirement}"

    async def answer_question_stream(self, question: str, context: str, history: List[dict] = [], selection: str = "", user_persona: str = "", course_id: str = None, node_id: str = None):
        """Stream answer with metadata using centralized prompt components."""
        system_prompt = ""
        
        # Try to use Dual Memory System if context is available
        if course_id and node_id:
            try:
                from memory import memory_controller
                
                optimized_history = await memory_controller.optimize_history(history, self.summarize_history)
                system_prompt = memory_controller.build_tutor_prompt(course_id, node_id, question, optimized_history)
                history = optimized_history
                
                # Append metadata instruction
                system_prompt += TUTOR_METADATA_RULE.format(node_id=node_id)
                
            except Exception as e:
                logger.error(f"Dual Memory Error: {e}")
        
        if not system_prompt:
            # Fallback using centralized base prompt
            system_prompt = TUTOR_SYSTEM_BASE + f"""

**用户画像**：
{user_persona if user_persona else "通用学习者"}

{TUTOR_METADATA_RULE.format(node_id=node_id or "current")}
"""
        
        # Build conversation history
        messages = []
        for msg in history[-5:]:  # Keep last 5 messages
            role = "user" if msg.get("type") == "user" else "assistant"
            messages.append({"role": role, "content": msg.get("content", "")})
        
        # Construct prompt with context
        prompt_parts = []
        if context:
            prompt_parts.append(f"课程上下文：\n{context}\n")
        if selection:
            prompt_parts.append(f"用户选中的文本：\n{selection}\n")
        prompt_parts.append(f"用户问题：{question}")
        
        prompt = "\n".join(prompt_parts)
        
        async for chunk in self._stream_llm(prompt, system_prompt):
            yield chunk

    async def summarize_history(self, history_text: str) -> str:
        """Summarize conversation history using fast model."""
        system_prompt = "你是一个对话摘要助手。请将以下对话历史总结为3-5个要点，捕捉关键事实和用户的理解水平。"
        prompt = f"请总结以下对话历史：\n\n{history_text}"
        
        response = await self._call_llm(prompt, system_prompt, use_fast_model=True)
        return response if response else "对话摘要"


# Singleton instance
ai_service = AIService()
