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

# Mock AI Service with capabilities to switch to Real API
class AIService:
    """
    Abstraction layer for AI model interactions.
    Supports switching between different models based on task complexity.
    """
    def __init__(self):
        # Configure API Key via environment variable
        self.api_key = os.getenv("AI_API_KEY")
        self.api_base = os.getenv("AI_API_BASE", "https://api-inference.modelscope.cn/v1")
        
        # Hybrid Model Strategy
        # Smart Model: For complex reasoning, creative writing, and detailed explanations.
        self.model_smart = os.getenv("AI_MODEL", "Qwen/Qwen3-32B")
        
        # Fast Model: For summarization, classification, and simple tasks.
        # Default to a smaller, faster model if not specified.
        self.model_fast = os.getenv("AI_MODEL_FAST", "Qwen/Qwen3-32B")
        
        self.client = AsyncOpenAI(
            base_url=self.api_base,
            api_key=self.api_key,
        )

    def _extract_json(self, text: str) -> Optional[Dict]:
        """
        Robust JSON extraction from LLM response.
        Handles Markdown blocks, plain text, and potential noise.
        """
        logger.info(f"Raw AI Response for JSON extraction: {text[:200]}...")

        try:
            # First try direct parsing
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to find JSON block in markdown
        # Relaxed regex to capture content between ```json and ```
        json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError as e:
                logger.warning(f"Markdown JSON decode error: {e}")
                pass

        # Try to find any code block
        code_match = re.search(r'```\s*(.*?)\s*```', text, re.DOTALL)
        if code_match:
            try:
                return json.loads(code_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find the first '{' and the last '}'
        try:
            start_idx = text.find('{')
            end_idx = text.rfind('}')
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                json_str = text[start_idx:end_idx+1]
                return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(f"Substring JSON decode error: {e}")
            pass

        logger.warning(f"Failed to extract JSON from: {text[:500]}...")
        
        # Debug: Write failed text to file
        try:
            with open("debug_failed_json.txt", "w", encoding="utf-8") as f:
                f.write(text)
        except Exception:
            pass
            
        return None

    def _clean_mermaid_syntax(self, text: str) -> str:
        """
        Fix common Mermaid syntax errors in the text.
        """
        # Regex to find mermaid blocks
        pattern = r'```mermaid(.*?)```'
        
        def fix_mermaid_block(match):
            content = match.group(1)
            
            def quote_if_needed(text, type_char):
                # Check if already quoted (simple check)
                if text.startswith('"') and text.endswith('"'):
                    return text
                
                # Escape quotes inside the text
                text = text.replace('"', '\\"')
                return f'"{text}"'

            # Fix 1: [Text] -> ["Text"] (Rectangular nodes)
            # Exclude content starting with (, [, /, \, < to avoid breaking shapes
            content = re.sub(r'\[(?![(\[/\\<])([^\[\]\n]+?)\]', 
                             lambda m: f'[{quote_if_needed(m.group(1), "[")}]', 
                             content)
            
            # Fix 2: (Text) -> ("Text") (Round nodes)
            # Exclude content starting with ( to avoid breaking shapes
            content = re.sub(r'\((?!\()([^()\n]+?)\)', 
                             lambda m: f'({quote_if_needed(m.group(1), "(")})', 
                             content)
            
            # Fix 3: {Text} -> {"Text"} (Rhombus nodes)
            # Exclude {{Hexagon}}
            content = re.sub(r'\{(?![{!])([^{}\n]+?)\}', 
                             lambda m: f'{{{quote_if_needed(m.group(1), "{")}}}', 
                             content)
            
            return f'```mermaid{content}```'

        return re.sub(pattern, fix_mermaid_block, text, flags=re.DOTALL)

    def clean_response_text(self, text: str) -> str:
        """
        Cleans LLM response: strips markdown wrapper and fixes LaTeX and Mermaid.
        """
        clean_text = text.strip()
        # Strip ```markdown wrapper
        if clean_text.startswith("```markdown") and clean_text.endswith("```"):
            clean_text = clean_text[11:-3].strip()
            
        # Fix LaTeX
        pattern = r'(?<!\$)(?<!\$\$)\\begin\{(matrix|pmatrix|bmatrix|vmatrix|Vmatrix|array|align|equation|cases)\}.*?\\end\{\1\}(?!\$)(?!\$\$)'
        clean_text = re.sub(pattern, lambda m: f"\n$$\n{m.group(0)}\n$$\n", clean_text, flags=re.DOTALL)
        
        # Fix Mermaid
        clean_text = self._clean_mermaid_syntax(clean_text)
        
        return clean_text

    async def _call_llm(self, prompt: str, system_prompt: str = "You are a helpful assistant.", use_fast_model: bool = False) -> str:
        """
        Generic function to call LLM using OpenAI client.
        Supports Model Routing (Smart vs Fast).
        
        Args:
            prompt: User input prompt
            system_prompt: System instruction
            use_fast_model: If True, uses the lighter/faster model (e.g. for simple summaries)
        """
        if not self.api_key:
            return None # Signal to use mock fallback
        
        try:
            extra_body = {
                "enable_thinking": False
            }
            
            # Select Model
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
            
            full_content = ""
            async for chunk in response:
                if chunk.choices:
                    # Handle reasoning content if available (for logging/debugging)
                    if hasattr(chunk.choices[0].delta, 'reasoning_content'):
                        reasoning = chunk.choices[0].delta.reasoning_content
                        if reasoning:
                            # Log thinking process to console to match user expectation
                            print(reasoning, end='', flush=True)
                            
                    delta = chunk.choices[0].delta
                    if delta.content:
                        full_content += delta.content
            
            logger.info(f"AI Response Complete (Model: {model_id})")
            return full_content
        except Exception as e:
            logger.error(f"AI API Call Error: {e}")
            return None

    async def generate_course(self, keyword: str, difficulty: str = "medium", style: str = "academic", requirements: str = "") -> Dict:
        system_prompt = get_prompt("generate_course").format(
            difficulty=difficulty,
            style=style,
            requirements=requirements if requirements else "无"
        )
        prompt = f"用户想要学习“{keyword}”，请生成一份专业且系统的课程大纲。"
        
        response = await self._call_llm(prompt, system_prompt)
        if response:
            return self._extract_json(response)
        return {"course_name": keyword, "nodes": []}

    async def generate_quiz(self, content: str, node_name: str = "", difficulty: str = "medium", style: str = "standard", user_persona: str = "", question_count: int = 3) -> List[Dict]:
        system_prompt = get_prompt("generate_quiz").format(
            difficulty=difficulty,
            style=style,
            question_count=question_count
        )
        
        content_text = content
        if not content or len(content) < 50:
            content_text = f"Topic: {node_name}\n(The detailed content is missing, please generate general questions based on this topic)"
        
        # Explicitly mention question count in the user prompt as well to reinforce it
        prompt = f"Content:\n{content_text}\n\nPlease generate exactly {question_count} questions in JSON format. Remember to use Markdown tables or Mermaid diagrams in 'explanation' if helpful for understanding."
        
        response = await self._call_llm(prompt, system_prompt)
        if response:
            result = self._extract_json(response)
            if result:
                return result

        
        # Hard Fallback: If AI fails or returns empty, generate template questions
        # This ensures the user NEVER sees "Cannot generate" error.
        logger.warning(f"Quiz generation failed for {node_name}. Using hard fallback.")
        fallback_topic = node_name if node_name else "此主题"
        fallback_questions = [
            {
                "id": 1,
                "question": f"关于“{fallback_topic}”的核心概念，以下描述正确的是？",
                "options": [
                    f"{fallback_topic} 是一个孤立的概念，与其他知识无关",
                    f"{fallback_topic} 是该学科体系中的关键组成部分",
                    f"{fallback_topic} 已经被现代理论完全推翻",
                    f"{fallback_topic} 仅在特定极端情况下适用"
                ],
                "correct_index": 1,
                "explanation": f"{fallback_topic} 作为核心知识点，在学科体系中起着承上启下的作用，是理解后续内容的基础。"
            },
            {
                "id": 2,
                "question": f"在实际应用中，理解“{fallback_topic}”主要有助于解决什么问题？",
                "options": [
                    "历史背景的考证",
                    "复杂系统中的关键机制分析",
                    "无关数据的随机处理",
                    "纯粹的理论推导游戏"
                ],
                "correct_index": 1,
                "explanation": f"掌握{fallback_topic}的原理，能够帮助我们分析和处理实际系统中的复杂机制与关键问题。"
            },
            {
                "id": 3,
                "question": f"对于初学者来说，学习“{fallback_topic}”最大的挑战通常是？",
                "options": [
                    "概念过于简单，缺乏挑战",
                    "理解其抽象逻辑与实际场景的映射",
                    "相关资料太少，无法查阅",
                    "没有任何挑战，一学就会"
                ],
                "correct_index": 1,
                "explanation": f"{fallback_topic}往往包含一定的抽象逻辑，将其准确映射到实际应用场景中是初学者常见的难点。"
            },
            {
                "id": 4,
                "question": f"以下哪项不是“{fallback_topic}”的典型特征？",
                "options": [
                    "系统性",
                    "逻辑性",
                    "随意性",
                    "实用性"
                ],
                "correct_index": 2,
                "explanation": f"{fallback_topic}作为科学或专业知识，具有严密的逻辑和系统性，绝非随意构建。"
            },
            {
                "id": 5,
                "question": f"深入掌握“{fallback_topic}”后，下一步通常应该学习？",
                "options": [
                    "放弃该学科",
                    "该领域的进阶理论或相关交叉学科",
                    "完全不相关的领域",
                    "重复学习基础概念"
                ],
                "correct_index": 1,
                "explanation": f"在掌握基础后，进阶理论或交叉学科的应用是深入研究的必经之路。"
            }
        ]
        
        return fallback_questions[:question_count]

    async def generate_sub_nodes(self, node_name: str, node_level: int, node_id: str, course_name: str = "", parent_context: str = "") -> List[Dict]:
        system_prompt = get_prompt("generate_sub_nodes").format(
            course_name=course_name if course_name else "未知课程",
            parent_context=parent_context if parent_context else "无"
        )
        prompt = f"当前节点信息：名称={node_name}，层级={node_level}。请列出该章节下的所有子小节，确保结构完整且具备专业性。"
        
        response = await self._call_llm(prompt, system_prompt)
        new_level = node_level + 1
        
        if response:
            data = self._extract_json(response)
            if data:
                result = []
                for item in data.get("sub_nodes", []):
                    result.append({
                        "node_id": str(uuid.uuid4()),
                        "parent_node_id": node_id,
                        "node_name": item.get("node_name", "新节点"),
                        "node_level": new_level,
                        "node_content": item.get("node_content", ""),
                        "node_type": "custom"
                    })
                return result

        return [
            {"node_id": str(uuid.uuid4()), "parent_node_id": node_id, "node_name": f"{node_name} - 子节点 1", "node_level": new_level, "node_content": "", "node_type": "custom"},
            {"node_id": str(uuid.uuid4()), "parent_node_id": node_id, "node_name": f"{node_name} - 子节点 2", "node_level": new_level, "node_content": "", "node_type": "custom"}
        ]

    async def _stream_llm(self, prompt: str, system_prompt: str = "You are a helpful assistant.", use_fast_model: bool = False):
        """
        Generator function to stream LLM response chunks.
        """
        if not self.api_key:
            yield "AI Service not configured."
            return

        try:
            extra_body = {
                "enable_thinking": False
            }
            
            # Select Model
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
                    # Handle reasoning content if available (for logging/debugging)
                    if hasattr(chunk.choices[0].delta, 'reasoning_content'):
                        reasoning = chunk.choices[0].delta.reasoning_content
                        if reasoning:
                             # We can log thinking process or just ignore it for now
                             pass
                    
                    delta = chunk.choices[0].delta
                    if delta.content:
                        yield delta.content
        except Exception as e:
            logger.error(f"Stream Error: {e}")
            yield f"\n[Error: {str(e)}]"

    async def redefine_node_content(self, node_name: str, original_content: str, requirement: str, course_context: str = "", previous_context: str = ""):
        """
        Stream version of redefine_content with book-level context awareness.
        """
        system_prompt = """
你是一位资深学科专家、世界顶尖大学的终身教授，并拥有一线大厂的首席架构师背景。

## 学术定位
- **受众**：大学本科生、研究生及专业技术人员
- **目标**：构建系统化、理论联系实际的知识体系，不仅讲“是什么”，更讲“为什么”和“怎么做”
- **标准**：符合学术规范和行业标准
- **风格**：专业严谨，深入浅出，拒绝科普性质的浅层介绍

## 内容架构要求
### 核心输出结构（必须严格遵守）
你的输出必须包含两部分，并用 `<!-- BODY_START -->` 分隔：
1. **第一部分：学术性导言（Annotation）**
   - 简短的导读或批注（100字以内）。
   - 阐述本章在学科体系中的地位和价值，概述核心问题和研究意义。
   - 必须放在 `<!-- BODY_START -->` 之前。
2. **分隔符**
   - 必须严格输出 `<!-- BODY_START -->` 字符串。
3. **第二部分：专业正文内容（Main Body）**
   - 详细的教科书内容（Markdown格式）。
   - 必须放在 `<!-- BODY_START -->` 之后。

### 内容质量标准
1. **学术深度**
   - 深入剖析概念的理论基础和历史渊源
   - 分析技术原理的数学或逻辑基础
   - 探讨方法的适用范围和局限性

2. **专业表达**
   - 使用规范的学术术语和表达方式
   - 避免生活化比喻，采用专业类比
   - 引用权威研究和实证数据

3. **结构严谨性**
   - 正文结构应包含：
     - **### 💡 核心概念与背景**：清晰定义 + 产生背景/核心价值（关键名词使用 **加粗** 强调）
     - **### 🔍 深度原理/底层机制**：深入剖析工作原理、底层逻辑、数学模型或演化逻辑（重中之重）
     - **### 🛠️ 技术实现/方法论**：具体的推导过程、算法步骤或执行细节
     - **### 🎨 可视化图解**：**必须**包含至少一个 Mermaid 图表（流程图或时序图）。ID纯英文无空格，文本双引号包裹。
     - **### 🏭 实战案例/行业应用**：结合真实产业界的落地案例进行分析
     - **### ✅ 思考与挑战**：提供 1-2 个能引发深度思考的问题

### 技术规范
- **图表（强制要求）**：每章**必须**包含至少一张 Mermaid 图表（如流程图、时序图、类图或思维导图），用于直观解释核心概念或流程。
  - 节点 ID 必须纯英文，严禁中文或特殊符号。
  - 节点文本必须双引号包裹。
- **公式规范（绝对严格执行）**
  - 行内公式：必须使用 `$公式$` 格式，内部不要有空格（例如 `$E=mc^2$`）
  - 块级公式：必须使用 `$$` 包裹，且独占一行
  - 严禁裸写 LaTeX 命令
- **参考文献**：符合学术引用规范

### 篇幅与输出
- **字数**：800-1500 字，确保解释透彻。
- **输出**：直接输出 Markdown 内容，包含分隔符。
"""
        # Inject Style and Difficulty context from requirement string if possible
        # Since 'requirement' is just a string, we append it directly.
        
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
        """
        Refine the content of a node based on specific requirements.
        Uses advanced prompt engineering for better structure and clarity.
        """
        system_prompt = """
你是一位资深学科专家、世界顶尖大学的终身教授，并拥有一线大厂的首席架构师背景。

## 学术定位
- **受众**：大学本科生、研究生及专业技术人员
- **目标**：构建系统化、理论联系实际的知识体系，不仅讲“是什么”，更讲“为什么”和“怎么做”
- **标准**：符合学术规范和行业标准
- **风格**：专业严谨，深入浅出，拒绝科普性质的浅层介绍

## 核心任务
根据用户的特定需求，重新撰写或调整章节内容。

## 处理原则
1. **保持学术严谨性**：即使调整风格，也不降低内容质量
2. **响应用户需求**：优先满足用户的明确要求
3. **维持结构完整性**：保持原有的章节结构和逻辑框架
4. **衔接上下文**：确保与前后章节内容的连贯性

## 内容质量标准
1. **专业严谨**：准确使用学术术语，定义清晰，推导严密
2. **深度解析**：不仅停留在表面定义，深入剖析背后的原理和机制
3. **场景化解释**：使用具体的行业应用场景或技术场景辅助解释，而非简单的生活类比
4. **逻辑连贯**：段落之间过渡自然，论证严密

## 结构化写作要求
- **### 💡 核心概念与背景**：清晰定义 + 产生背景/核心价值（关键名词使用 **加粗** 强调）
- **### 🔍 深度原理/底层机制**：深入剖析工作原理、底层逻辑、数学模型或演化逻辑（重中之重）
- **### 🛠️ 技术实现/方法论**：具体的推导过程、算法步骤或执行细节
- **### 🎨 可视化图解**：**必须**包含至少一个 Mermaid 图表（流程图或时序图）。ID纯英文无空格，文本双引号包裹。
- **### 🏭 实战案例/行业应用**：结合真实产业界的落地案例进行分析
- **### ✅ 思考与挑战**：提供 1-2 个能引发深度思考的问题

## 技术规范
- **图表（强制要求）**：每章**必须**包含至少一张 Mermaid 图表。
- **公式规范（绝对严格执行）**
  - 行内公式：必须使用 `$公式$` 格式，内部不要有空格（例如 `$E=mc^2$`）
  - 块级公式：必须使用 `$$` 包裹，且独占一行
  - 严禁裸写 LaTeX 命令

## 篇幅要求
**800-1500字**，根据用户需求可适当调整。

## 输出格式
- 直接输出 **Markdown 正文**。
"""
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
                
        return f"基于需求 '{requirement}' 重定义的 {node_name} 内容。\n\n1. 核心点一：...\n2. 核心点二：...\n(参考来源：权威资料)"

    async def extend_content(self, node_name: str, requirement: str) -> str:
        system_prompt = """
你是学术视野拓展专家，需为当前教科书章节补充具有深度的延伸阅读材料。
要求：
1. **受众定位**：面向大学生及专业人士，拒绝科普性质的浅层介绍。
2. **拓展方向**：重点补充学术界的前沿研究、工业界的工程陷阱、底层数学原理或跨学科的深度关联。
3. **内容风格**：专业、干练、逻辑严密。
4. **格式规范**：内容充实（300-500 字），可使用“延伸阅读”或“深度思考”作为标题。
5. **公式规范**：
   - 行内公式用 `$公式$`（**内部不要有空格**）。
   - 块级公式用 `$$` 包裹。
   - 严禁裸写 LaTeX 命令。
6. **输出格式**：直接输出 **Markdown 格式的内容**，**不需要**包含在 JSON 对象中。
"""
        prompt = f"当前章节：{node_name}\n拓展方向：{requirement}"

        response = await self._call_llm(prompt, system_prompt)
        if response:
            return self.clean_response_text(response)

        return f"拓展知识点：\n关于 {node_name} 的延伸阅读... {requirement}"

    async def answer_question_stream(self, question: str, context: str, history: List[dict] = [], selection: str = "", user_persona: str = "", course_id: str = None, node_id: str = None, user_notes: str = ""):
        """
        Stream answer with metadata appended at the end.
        Structure: [Answer Content] \n\n---METADATA---\n [JSON Metadata]
        """
        system_prompt = ""
        
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
   - 如果用户之前问过类似问题或犯过类似错误（参考对话历史），请在回答中明确指出：“正如我们之前讨论的...”或“注意不要混淆...”。
3. **定位原文（Locate）**：
   - 尽量在提供的课程内容中找到能够支持你回答的**原句**。
   - 将找到的原句放入 metadata 的 `quote` 字段中。前端界面会自动高亮显示这句话，就像老师在课本上划线一样。
   - 如果找不到精确原句，不要编造。
4. **总结笔记（Note Taking）**：
   - 在 `anno_summary` 中生成一个核心知识点概括（Markdown 列表，3-5点），方便用户快速回顾。

**创新想法捕捉（Innovation Capture）**：
- 如果用户提出了新的解法、思路或独特的见解，请予以积极反馈。
- 帮助用户完善思路，并标记这是一个“创新想法”。
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
        Generate a concise title/summary for a note content.
        """
        system_prompt = get_prompt("summarize_note").format()
        
        # If content contains Q&A structure, try to summarize the Question primarily
        prompt = f"笔记内容：\n{content[:2000]}\n\n请生成标题："
        
        # Use Fast Model
        response = await self._call_llm(prompt, system_prompt, use_fast_model=True)
        return response if response else (content[:20] + "...")

    async def summarize_chat(self, history: List[dict], course_context: str = "", user_persona: str = "") -> Dict:
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
        Summarizes conversation history using LLM.
        """
        system_prompt = get_prompt("summarize_history").format()
        history_text = "\n".join([f"{msg.get('role', 'unknown')}: {msg.get('content', '')}" for msg in history])
        
        prompt = f"Please summarize the following conversation:\n\n{history_text}"
        
        # Use Fast Model for summarization
        response = await self._call_llm(prompt, system_prompt, use_fast_model=True)
        return response if response else "Previous conversation summary (auto-generated failed)."

    async def generate_knowledge_graph(self, course_name: str, course_context: str, nodes: List[Dict]) -> Dict:
        """
        Generate a knowledge graph structure based on course content.
        
        Args:
            course_name: Name of the course
            course_context: Full course outline/context
            nodes: List of course nodes with their content
            
        Returns:
            Dictionary containing nodes and edges for the knowledge graph
        """
        from prompts import get_prompt
        
        # Build course context summary
        nodes_summary = []
        for node in nodes[:50]:  # Increased limit to cover full course structure
            nodes_summary.append({
                "id": node.get("node_id", ""),
                "name": node.get("node_name", ""),
                "level": node.get("node_level", 1),
                "content": node.get("node_content", "")[:200]  # Increased content context
            })
        
        context_text = f"""
课程名称：{course_name}

课程大纲：
{course_context}

章节列表：
{json.dumps(nodes_summary, ensure_ascii=False, indent=2)}
"""
        
        # Get the knowledge graph prompt template
        prompt_template = get_prompt("generate_knowledge_graph")
        system_prompt = prompt_template.format(
            course_name=course_name,
            course_context=context_text
        )
        
        user_prompt = f"""请基于以下课程内容生成知识图谱：

课程名称：{course_name}

主要章节：
{chr(10).join([f"- {n.get('node_name', '')}: {n.get('node_content', '')[:50]}..." for n in nodes_summary[:15]])}

请生成包含节点和关系的知识图谱JSON。"""
        
        response = await self._call_llm(user_prompt, system_prompt)
        
        if response:
            result = self._extract_json(response)
            if result and "nodes" in result and "edges" in result and len(result["nodes"]) > 0:
                # Self-Healing: Validate and fix chapter_ids
                valid_chapter_ids = {n.get("node_id") for n in nodes}
                
                for graph_node in result["nodes"]:
                    chapter_id = graph_node.get("chapter_id")
                    
                    # If invalid or missing
                    if not chapter_id or chapter_id not in valid_chapter_ids:
                        # Try to find a match by name similarity (simple substring check for now)
                        node_label = graph_node.get("label", "")
                        best_match_id = None
                        
                        # Priority 1: Exact match
                        for n in nodes:
                            if n.get("node_name", "") == node_label:
                                best_match_id = n.get("node_id")
                                break
                                
                        # Priority 2: Substring match
                        if not best_match_id:
                            for n in nodes:
                                if node_label in n.get("node_name", "") or n.get("node_name", "") in node_label:
                                    best_match_id = n.get("node_id")
                                    break
                        
                        # Fallback to the first available node if no match found
                        if not best_match_id and nodes:
                            best_match_id = nodes[0].get("node_id")
                            
                        if best_match_id:
                            graph_node["chapter_id"] = best_match_id
                            
                return result
        
        # Fallback: Generate a simple graph based on node hierarchy
        logger.warning("Knowledge graph generation failed, using fallback")
        return self._generate_fallback_knowledge_graph(nodes)
    
    def _generate_fallback_knowledge_graph(self, nodes: List[Dict]) -> Dict:
        """
        Generate a simple fallback knowledge graph based on node hierarchy.
        """
        graph_nodes = []
        graph_edges = []
        
        # Create nodes
        for node in nodes[:15]:
            node_id = node.get("node_id", str(uuid.uuid4()))
            node_level = node.get("node_level", 1)
            
            # Determine node type based on level
            if node_level == 1:
                node_type = "module"
            else:
                node_type = "concept"
            
            graph_nodes.append({
                "id": node_id,
                "label": node.get("node_name", "Unknown"),
                "type": node_type,
                "description": node.get("node_content", "")[:50],
                "chapter_id": node_id
            })
        
        # Add Root Node
        root_id = "root_" + str(uuid.uuid4())[:8]
        graph_nodes.insert(0, {
            "id": root_id,
            "label": "课程核心",
            "type": "root",
            "description": "课程根节点",
            "chapter_id": nodes[0].get("node_id") if nodes else ""
        })
        
        # Connect Root to Level 1 Modules
        for node in graph_nodes:
             if node["type"] == "module":
                graph_edges.append({
                    "source": root_id,
                    "target": node["id"],
                    "relation": "contains",
                    "label": "包含"
                })

        # Create edges based on parent-child relationships
        node_map = {n["id"]: n for n in graph_nodes}
        for node in nodes[:15]:
            node_id = node.get("node_id", "")
            parent_id = node.get("parent_node_id", "")
            
            if parent_id and parent_id in node_map and node_id in node_map:
                graph_edges.append({
                    "source": parent_id,
                    "target": node_id,
                    "relation": "contains",
                    "label": "包含"
                })
        
        # Add some cross-references between same-level nodes
        level_groups = {}
        for node in graph_nodes:
            level = node.get("type", "basic")
            if level not in level_groups:
                level_groups[level] = []
            level_groups[level].append(node)
        
        # Connect nodes within same level
        for level, group in level_groups.items():
            for i in range(len(group) - 1):
                if len(graph_edges) < 30:  # Limit total edges
                    graph_edges.append({
                        "source": group[i]["id"],
                        "target": group[i + 1]["id"],
                        "relation": "related",
                        "label": "关联"
                    })
        
        return {
            "nodes": graph_nodes,
            "edges": graph_edges
        }

    def locate_node(self, keyword: str, all_nodes: List[Dict]) -> Dict:
        # Simple mock search - Semantic search requires embedding, sticking to keyword match for now
        # Or could use LLM to pick from list if list is small, but for MVP keyword is safer/faster
        for node in all_nodes:
            if keyword in node['node_name']:
                return {
                    "match_node_id": node['node_id'],
                    "match_node_name": node['node_name'],
                    "node_path": "Path/To/Node" # Mock path
                }
        return {}


ai_service = AIService()
