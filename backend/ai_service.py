import uuid
import random
import os
import json
import re
import logging
from dotenv import load_dotenv
from openai import AsyncOpenAI, APIStatusError
from typing import List, Dict, Optional

# 导入提示模板
from prompts import (
    get_prompt,
    TUTOR_SYSTEM_BASE,
    TUTOR_METADATA_RULE,
)

# 配置日志记录
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 加载环境变量
load_dotenv()

# 具有切换到真实 API 功能的模拟 AI 服务
class AIService:
    """
    AI 模型交互的抽象层。
    支持根据任务复杂性在不同模型之间切换。
    支持多 Token 自动故障转移（Auto-Failover）。
    """
    def __init__(self):
        # 1. 优先加载 Token 列表（支持多 Token 轮询）
        keys_str = os.getenv("AI_API_KEYS", "")
        if keys_str:
            self.api_keys = [k.strip() for k in keys_str.split(",") if k.strip()]
        else:
            # 2. 回退到单 Token 模式
            single_key = os.getenv("AI_API_KEY")
            self.api_keys = [single_key] if single_key else []

        self.current_key_index = 0
        self.api_base = os.getenv("AI_API_BASE", "https://api-inference.modelscope.cn/v1")
        
        # 混合模型策略
        self.model_smart = os.getenv("AI_MODEL", "Qwen/Qwen3-32B")
        self.model_fast = os.getenv("AI_MODEL_FAST", "Qwen/Qwen3-32B")
        
        self.client = None
        self._refresh_client()

    def _refresh_client(self):
        """根据当前索引刷新 OpenAI 客户端"""
        if not self.api_keys:
            self.client = None
            logger.warning("No API Keys configured.")
            return

        current_key = self.api_keys[self.current_key_index]
        # logger.info(f"Using API Key index: {self.current_key_index} (Ends with {current_key[-4:]})")
        
        self.client = AsyncOpenAI(
            base_url=self.api_base,
            api_key=current_key,
        )

    def _rotate_key(self):
        """切换到下一个 API Key"""
        if len(self.api_keys) <= 1:
            return False # 只有一个 key，无法切换

        old_index = self.current_key_index
        self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
        logger.warning(f"⚠️ Switching API Key: {old_index} -> {self.current_key_index}")
        self._refresh_client()
        return True

    def _extract_json(self, text: str) -> Optional[Dict]:
        """
        从 LLM 响应中稳健地提取 JSON。
        处理 Markdown 块、纯文本和潜在的干扰信息。
        """
        # logger.info(f"Raw AI Response for JSON extraction: {text[:200]}...")

        try:
            # 首先尝试直接解析
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 尝试在 markdown 中查找 JSON 块
        # 宽松的正则表达式以捕获 ```json 和 ``` 之间的内容
        json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError as e:
                logger.warning(f"Markdown JSON decode error: {e}")
                pass

        # 尝试查找任何代码块
        code_match = re.search(r'```\s*(.*?)\s*```', text, re.DOTALL)
        if code_match:
            try:
                return json.loads(code_match.group(1))
            except json.JSONDecodeError:
                pass

        # 尝试查找第一个 '{' 和最后一个 '}'
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
        
        # 调试：将失败的文本写入文件
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
            # Exclude content starting with {{Hexagon}}
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
        Supports Auto-Failover for Rate Limits (429) or Auth Errors (401/403).
        """
        if not self.client:
            return None 
        
        max_retries = len(self.api_keys)
        # 如果只有一个 key，重试一次即可（或者不重试，直接报错）
        # 这里设置为 max(1, len) 确保至少尝试一次
        attempts = 0
        
        while attempts < max_retries:
            attempts += 1
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
                                # Log thinking process to console
                                print(reasoning, end='', flush=True)
                                
                        delta = chunk.choices[0].delta
                        if delta.content:
                            full_content += delta.content
                
                logger.info(f"AI Response Complete (Model: {model_id})")
                return full_content

            except APIStatusError as e:
                # 只在遇到限流(429)或权限(401/403)错误时切换 Token
                if e.status_code in [429, 401, 403]:
                    logger.error(f"⚠️ API Error ({e.status_code}): {e.message}. Trying next token...")
                    if self._rotate_key():
                        continue # Retry with new key
                    else:
                        logger.error("❌ All tokens exhausted or only one token available.")
                        raise e # No more tokens to try
                else:
                    # 其他错误（如 500, 400）直接抛出，不浪费 Token
                    logger.error(f"AI API Call Error (Non-retryable): {e}")
                    raise e
            except Exception as e:
                logger.error(f"AI API Unexpected Error: {e}")
                return None
        
        return None

    async def generate_course(self, keyword: str, difficulty: str = "medium", style: str = "academic", requirements: str = "") -> Dict:
        system_prompt = get_prompt("generate_course").format(
            difficulty=difficulty,
            style=style,
            requirements=requirements if requirements else "无"
        )
        prompt = f"用户想要学习“{keyword}”，请生成一份专业且系统的课程大纲。"
        
        try:
            response = await self._call_llm(prompt, system_prompt)
            if response:
                data = self._extract_json(response)
                if data and "nodes" in data:
                    # Ensure unique UUIDs for nodes to prevent collision between courses
                    for node in data["nodes"]:
                        node["node_id"] = str(uuid.uuid4())
                return data
        except Exception:
            pass
            
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
        
        try:
            response = await self._call_llm(prompt, system_prompt)
            if response:
                result = self._extract_json(response)
                if result:
                    return result
        except Exception:
            pass

        
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

    async def generate_sub_nodes(self, node_name: str, node_level: int, node_id: str, course_name: str = "", parent_context: str = "", course_outline: str = "") -> List[Dict]:
        system_prompt = get_prompt("generate_sub_nodes").format(
            course_name=course_name if course_name else "未知课程",
            parent_context=parent_context if parent_context else "无",
            course_outline=course_outline if course_outline else "无"
        )
        prompt = f"当前节点信息：名称={node_name}，层级={node_level}。请列出该章节下的所有子小节，确保结构完整且具备专业性。"
        
        try:
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
        except Exception:
            pass

        new_level = node_level + 1
        return [
            {"node_id": str(uuid.uuid4()), "parent_node_id": node_id, "node_name": f"{node_name} - 子节点 1", "node_level": new_level, "node_content": "", "node_type": "custom"},
            {"node_id": str(uuid.uuid4()), "parent_node_id": node_id, "node_name": f"{node_name} - 子节点 2", "node_level": new_level, "node_content": "", "node_type": "custom"}
        ]

    async def _stream_llm(self, prompt: str, system_prompt: str = "You are a helpful assistant.", use_fast_model: bool = False):
        """
        Generator function to stream LLM response chunks.
        Supports Auto-Failover.
        """
        if not self.client:
            yield "AI Service not configured."
            return

        max_retries = len(self.api_keys)
        attempts = 0

        while attempts < max_retries:
            attempts += 1
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
                
                # Success! Break loop.
                return 

            except APIStatusError as e:
                # 只在遇到限流(429)或权限(401/403)错误时切换 Token
                if e.status_code in [429, 401, 403]:
                    logger.error(f"⚠️ Stream API Error ({e.status_code}): {e.message}. Trying next token...")
                    if self._rotate_key():
                        continue # Retry with new key
                    else:
                        yield f"\n[Error: Token Exhausted - {str(e)}]"
                        return
                else:
                    logger.error(f"Stream API Error (Non-retryable): {e}")
                    yield f"\n[Error: {str(e)}]"
                    return
            except Exception as e:
                logger.error(f"Stream Error: {e}")
                yield f"\n[Error: {str(e)}]"
                return

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
        # 如果可能，从需求字符串中注入样式和难度上下文
        # 由于 'requirement' 只是一个字符串，我们直接附加它。
        
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

    async def chat_with_tutor(self, message: str, history: List[Dict], context: str = "", user_notes: str = "", selection: str = "", user_persona: str = "") -> str:
        """
        Chat with AI tutor.
        """
        system_prompt = TUTOR_SYSTEM_BASE.format(
            user_persona=user_persona if user_persona else "通用学习者"
        )
        
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

用户问题：{message}

请开始回答（记得在最后附加元数据）：
"""
        async for chunk in self._stream_llm(prompt, system_prompt):
            yield chunk

    async def generate_knowledge_graph(self, course_name: str, course_context: str, nodes: List[Dict]) -> Dict:
        """
        Generate a knowledge graph for the course.
        """
        system_prompt = """
你是一个知识图谱专家。请根据提供的课程内容，构建一个结构化的知识图谱。
输出必须是合法的 JSON 格式，包含 'nodes' 和 'edges' 两个数组。

Nodes 格式: { "id": "uuid", "label": "概念名称", "category": "概念类型", "chapter_id": "对应章节ID" }
Edges 格式: { "source": "source_id", "target": "target_id", "relation": "关系描述" }

重要：
1. 尽量复用已有的章节作为核心节点。
2. 自动提取章节内容中的关键概念作为子节点。
3. 确保 JSON 格式正确，不要包含 Markdown 标记。
"""
        
        # Simplify nodes for context to save tokens
        nodes_summary = []
        for n in nodes:
            nodes_summary.append({
                "node_id": n.get("node_id"),
                "node_name": n.get("node_name"),
                "node_content": n.get("node_content", "")[:100]
            })
            
        user_prompt = f"""请基于以下课程内容生成知识图谱：

课程名称：{course_name}

主要章节：
{chr(10).join([f"- {n.get('node_name', '')}: {n.get('node_content', '')[:50]}..." for n in nodes_summary[:15]])}

请生成包含节点和关系的知识图谱JSON。"""
        
        try:
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
                            
                            # If match found, update chapter_id
                            if best_match_id:
                                graph_node["chapter_id"] = best_match_id
                            # If still no match, maybe it's a sub-concept, link to nearest parent? 
                            # For now, leave as is or assign to root? 
                            # Let's leave it, frontend handles missing links gracefully.

                    return result
        except Exception:
            pass
            
        return {"nodes": [], "edges": []}

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
