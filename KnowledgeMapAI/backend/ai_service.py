import uuid
import random
import os
import json
import re
import logging
from dotenv import load_dotenv
from openai import AsyncOpenAI
from typing import List, Dict, Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Mock AI Service with capabilities to switch to Real API
class AIService:
    def __init__(self):
        # Configure API Key via environment variable
        self.api_key = os.getenv("AI_API_KEY")
        self.api_base = os.getenv("AI_API_BASE", "https://api-inference.modelscope.cn/v1")
        self.model = os.getenv("AI_MODEL", "Qwen/Qwen2.5-72B-Instruct")
        
        self.client = AsyncOpenAI(
            base_url=self.api_base,
            api_key=self.api_key,
        )

    def _extract_json(self, text: str) -> Optional[Dict]:
        """
        Robust JSON extraction from LLM response.
        Handles Markdown blocks, plain text, and potential noise.
        """
        try:
            # First try direct parsing
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to find JSON block in markdown
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find any code block
        code_match = re.search(r'```\s*(\{.*?\})\s*```', text, re.DOTALL)
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
        except json.JSONDecodeError:
            pass

        logger.warning(f"Failed to extract JSON from: {text[:100]}...")
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

    async def _call_llm(self, prompt: str, system_prompt: str = "You are a helpful assistant.") -> str:
        """
        Generic function to call LLM using OpenAI client.
        """
        if not self.api_key:
            return None # Signal to use mock fallback
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                stream=True, 
            )
            
            full_content = ""
            async for chunk in response:
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        full_content += delta.content
            
            logger.info("AI Response Complete")
            return full_content
        except Exception as e:
            logger.error(f"AI API Call Error: {e}")
            return None

    async def generate_course(self, keyword: str) -> Dict:
        system_prompt = """
你是资深大学教授和课程架构师，专注于为大学生和专业人士设计高水准的专业课程。
任务：根据用户输入的关键词，生成课程大纲骨架（仅包含书名和章）。

要求：
1. **仅生成大纲骨架**：
   - **严禁生成任何三级子节点（节）**。
   - **只生成 1 级（课程名）和 2 级（章）**。
   - 2 级章节（章）数量：**8-12 章**，覆盖全书内容。
   - **内容摘要**：为每一章生成简短的导读（50字左右），语言简洁精炼，概括核心要点。

2. **逻辑与结构**：
   - **学术严谨性**：确保内容覆盖该学科的核心知识点，体系完整，无重大遗漏。
   - **逻辑递进**：章节顺序必须遵循“基础理论 -> 核心机制 -> 高阶应用 -> 前沿拓展”的学术逻辑。
   - **导论先行**：第一章必须是该学科的导论或系统性概述。

3. **层级规范**：
   - 1 级（课程名称）：标准教科书书名或专业课程名称。
   - 2 级（章）：主要知识模块。

4. **受众定位**：
   - 目标用户：大学生及专业领域学习者。
   - 风格：专业、简洁、流畅，避免低幼化的比喻，使用规范的学术或行业术语，但保持解释清晰。

5. **输出格式**：
   - 请返回标准的 JSON 格式。
   - 推荐将 JSON 包裹在 markdown 代码块中（```json ... ```），以便于提取。
{
"course_name":"《关键词：原理与实践》",
"nodes":[
{"node_id":"id_1","parent_node_id":"root","node_name":"《计算机科学导论》","node_level":1,"node_content":"前言与课程综述","node_type":"original"},
{"node_id":"id_2","parent_node_id":"id_1","node_name":"第一章 基础理论","node_level":2,"node_content":"本章阐述...","node_type":"original"},
{"node_id":"id_3","parent_node_id":"id_1","node_name":"第二章 核心机制","node_level":2,"node_content":"本章深入分析...","node_type":"original"}
]
}
"""
        prompt = f"用户想要学习“{keyword}”，请生成一份专业且系统的课程大纲。"
        
        response = await self._call_llm(prompt, system_prompt)
        if response:
            return self._extract_json(response)
        return {"course_name": keyword, "nodes": []}

    async def generate_quiz(self, content: str, node_name: str = "", difficulty: str = "medium", style: str = "standard") -> List[Dict]:
        system_prompt = """
        You are an expert educator creating a quiz to test understanding of the provided content or topic.
        Create 5 multiple-choice questions based on the key concepts in the text or the topic provided.
        
        Requirements:
        1. Questions should challenge the learner's understanding, not just memory.
        2. Difficulty level: {difficulty}
        3. Style: {style} (if 'creative', use scenarios; if 'practical', use real-world problems; if 'standard', use academic style).
        4. Provide 4 options for each question.
        5. Provide the correct answer index (0-3).
        6. Provide a brief explanation for why the answer is correct.
        7. IMPORTANT: You MUST return valid JSON. Do not output conversational text.
        
        Output JSON format:
        [
            {{
                "id": 1,
                "question": "What is ...?",
                "options": ["Option A", "Option B", "Option C", "Option D"],
                "correct_index": 2,
                "explanation": "Because ..."
            }}
        ]
        """
        
        content_text = content
        if not content or len(content) < 50:
            content_text = f"Topic: {node_name}\n(The detailed content is missing, please generate general questions based on this topic)"
        
        prompt = f"Content:\n{content_text}\n\nPlease generate the quiz JSON."
        
        response = await self._call_llm(prompt, system_prompt.format(difficulty=difficulty, style=style))
        if response:
            result = self._extract_json(response)
            if result:
                return result
        
        # Hard Fallback: If AI fails or returns empty, generate template questions
        # This ensures the user NEVER sees "Cannot generate" error.
        logger.warning(f"Quiz generation failed for {node_name}. Using hard fallback.")
        fallback_topic = node_name if node_name else "此主题"
        return [
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
                    "基于此概念的高阶应用与扩展",
                    "与此完全无关的娱乐内容",
                    "重复死记硬背基础定义"
                ],
                "correct_index": 1,
                "explanation": f"在打好{fallback_topic}的基础后，进阶学习通常涉及将其应用于更复杂的场景或进行理论扩展。"
            }
        ]

    async def generate_sub_nodes(self, node_name: str, node_level: int, node_id: str, course_name: str = "", parent_context: str = "") -> List[Dict]:
        system_prompt = f"""
你是严谨的学术助教，需完善当前章节的详细目录结构。
当前课程主题：《{{course_name if course_name else "未知课程"}}》
上级章节摘要：{{parent_context if parent_context else "无"}}
任务：基于当前节点（章或节），生成下级子节点（目录）。

要求：
1. **逻辑严密**：按照循序渐进的学习逻辑，补充该主题下必须包含的所有子话题。
2. **数量强制**：**必须生成 5-10 个子节点**，严禁只生成 2-3 个。
3. **内容风格**：摘要内容要简洁流畅，适合大学生和专业人士阅读，体现学术深度。
4. **输出格式**：
   - 请返回标准的 JSON 格式。
   - 推荐将 JSON 包裹在 markdown 代码块中（```json ... ```），以便于提取。
{{
"sub_nodes":[
{{"node_name":"下级节点名 1","node_content":"本节摘要（简洁专业）"}},
{{"node_name":"下级节点名 2","node_content":"本节摘要"}},
{{"node_name":"下级节点名 3","node_content":"本节摘要"}},
{{"node_name":"下级节点名 4","node_content":"本节摘要"}},
{{"node_name":"下级节点名 5","node_content":"本节摘要"}}
]
}}
"""
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

    async def _stream_llm(self, prompt: str, system_prompt: str = "You are a helpful assistant."):
        """
        Generator function to stream LLM response chunks.
        """
        if not self.api_key:
            yield "AI Service not configured."
            return

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                stream=True
            )
            
            async for chunk in response:
                if chunk.choices:
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
你是该领域的资深专家和金牌大学讲师，正在撰写一本专业教科书。
任务：为当前章节撰写**章节简介**和**正文内容**。

### 核心输出结构（必须严格遵守）
你的输出必须包含两部分，并用 `<!-- BODY_START -->` 分隔：
1. **第一部分：章节简介（Annotation）**
   - 简短的导读或批注（100字以内）。
   - 必须放在 `<!-- BODY_START -->` 之前。
2. **分隔符**
   - 必须严格输出 `<!-- BODY_START -->` 字符串。
3. **第二部分：教科书正文（Main Body）**
   - 详细的教科书内容（Markdown格式）。
   - 必须放在 `<!-- BODY_START -->` 之后。

### 1. 核心基调与风格
- **深度与启发**：拒绝照本宣科。在给出定义前，先阐述“为什么需要这个概念”或“它解决了什么核心问题”。
- **专业且生动**：使用学术术语，但配合直观的类比（Analogy）辅助理解。
- **全书连贯性**：必须承接上文逻辑，避免孤立写作。

### 2. 动态结构化写作（正文部分）
正文部分（`<!-- BODY_START -->` 之后）必须包含以下核心模块：
- **### 💡 核心概念与背景**：清晰定义 + 产生背景/核心价值。
- **### 🔍 深度原理/底层机制**：剖析工作原理、数学模型或演化逻辑（重中之重）。
- **### 🛠️ 技术实现/方法论**：具体的推导、算法步骤或执行细节。
- **### 🎨 可视化图解**：**必须**包含至少一个 Mermaid 图表。
  - **Mermaid 规范**：
    - 仅使用 `graph TD` (流程图) 或 `sequenceDiagram` (时序图)。
    - **节点 ID 规范**：必须是纯英文且无空格（如 `NodeA`），**严禁使用中文或特殊符号作为 ID**。
    - **节点文本规范**：**必须**使用双引号包裹所有文本内容，例如 `A["文本"]`，以防止特殊符号导致语法错误。
    - 严禁在节点 ID 中使用 `(` `)` `[` `]`。
- **### 🚀 实战案例/行业应用**：结合真实产业界的落地案例分析。
- **### ✅ 思考与挑战**：提供 1-2 个能引发深度思考的问题。

### 3. 严格格式规范（关键！）
- **公式排版**：
  - 行内公式：仅使用 `$ E=mc^2 $`（前后保留空格）。
  - 块级公式：仅使用 `$$` 包裹。
  - **严禁使用** `\( ... \)` 或 `\[ ... \]`。
  - 所有 LaTeX 环境（如 `\\begin{matrix}`）必须包裹在 `$$` 中。
- **排版细节**：关键术语使用 **加粗**；重要结论使用 > 引用块。

### 4. 篇幅与输出
- **字数**：800-1500 字，确保解释透彻。
- **输出**：直接输出 Markdown 内容，包含分隔符。**严禁**使用 ```markdown 包裹全文。
"""
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
        你是该领域的资深专家和金牌大学讲师。
        任务：为当前节点撰写一段**适合大学生和专业人士阅读的教科书正文**。

        要求：
        1. **核心教学风格**：
           - **简洁流畅**：行文干练，逻辑清晰，拒绝冗余和低幼化表达。
           - **专业严谨**：准确使用学术术语，定义清晰，推导严密。
           - **深度解析**：不仅仅停留在表面定义，要深入剖析背后的原理和机制。
           - **场景化解释**：使用具体的行业应用场景或技术场景来辅助解释，而非简单的生活类比。

        2. **结构化写作**（Markdown 格式）：
           - **### 💡 核心概念**：清晰、专业的定义。必要时补充背景知识。
             - **排版要求**：关键名词使用 **加粗** 强调。
           - **### 🔍 原理与机制**：深入解析工作原理、底层逻辑或数学模型。
           - **### 🛠️ 关键技术/方法**：具体的推导过程、算法步骤或技术细节。
             - **公式规范（绝对严格执行）**：
               - **行内公式**：必须使用 `$公式$` 格式（例如 `$E=mc^2$`）。
               - **块级公式**：必须使用 `$$` 包裹，且独占一行。
               - **LaTeX 环境**：所有矩阵、方程组（如 `\\begin{matrix}`）**必须**包裹在 `$$` 中。
   - **### 🎨 架构/流程图示**：使用 Mermaid 语法绘制专业的流程图或架构图。必须使用 ```mermaid 代码块包裹。
   - **###  行业应用案例**：结合实际产业界的真实应用案例进行分析。
   - **### ✅ 思考与拓展**：提供 1-2 个具有挑战性的思考题或进阶阅读方向。

3. **篇幅要求**：**800-1500 字**，内容详实且有深度。
4. **输出格式**：直接输出 **Markdown 正文**。
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

    async def answer_question_stream(self, question: str, context: str, history: List[dict] = [], selection: str = "", user_persona: str = ""):
        """
        Stream answer with metadata appended at the end.
        Structure: [Answer Content] \n\n---METADATA---\n [JSON Metadata]
        """
        system_prompt = f"""
你是学术助手，请根据提供的课程内容、对话历史和选中的文本回答用户的问题。

**用户画像（个性化设定）**：
{user_persona if user_persona else "通用学习者"}
请根据用户画像调整你的回答风格、深度和举例方式。例如，如果用户是初学者，请多用生活类比；如果是专家，请深入底层原理。

**核心任务**：
1. **回答问题**：直接、专业、简洁地回答用户问题。
2. **定位上下文**：识别答案关联的课程章节或原文。

**输出格式规范（严格执行）**：
为了支持流式输出和后续处理，输出必须分为两部分，用 `---METADATA---` 分隔。

**第一部分：回答正文**
- 直接输出 Markdown 格式的回答内容。
- **严禁**将整个回答包裹在代码块中。但**可以**并在必要时应当使用代码块（如 Python, Mermaid）。
- 若使用 Mermaid，必须遵循：`graph TD`，ID为纯英文，复杂文本用双引号包裹。
- 就像正常聊天一样。

**第二部分：元数据**
- 正文结束后，**另起一行**输出分隔符：`---METADATA---`
- 紧接着输出一个标准的 JSON 对象（不要用 markdown 代码块包裹），包含：
  - `node_id`: (string) 答案主要参考的章节ID。如果无法确定，返回 null。
  - `quote`: (string) 答案引用的原文片段。如果没有引用，返回 null。
  - `anno_summary`: (string) 5-10个字的简短摘要，用于生成笔记标题。

**示例**：
什么是递归？
递归是指函数调用自身的编程技巧...

---METADATA---
{{"node_id": "uuid-123", "quote": "递归是...", "anno_summary": "递归的概念"}}
"""
        # Build prompt
        history_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in history[-5:]])
        
        prompt = f"""
课程内容片段：
{context}

对话历史：
{history_text}

选中内容（用户针对这段文字提问）：
{selection if selection else "无"}

用户问题：{question}

请开始回答（记得在最后附加元数据）：
"""
        async for chunk in self._stream_llm(prompt, system_prompt):
            yield chunk

    async def answer_question_json(self, question: str, context: str, history: List[dict] = [], selection: str = ""):
        # Build Prompt
        prompt_parts = []
        prompt_parts.append(f"课程内容：\n{context}")
        
        if selection:
            prompt_parts.append(f"\n用户选中的内容（重点关注）：\n{selection}")
            
        if history:
            history_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in history[-5:]]) # Limit to last 5 messages
            prompt_parts.append(f"\n对话历史：\n{history_text}")
            
        prompt_parts.append(f"\n用户问题：{question}")
        
        prompt = "\n\n".join(prompt_parts)
        
        response = self._call_llm(prompt, system_prompt)
        if response:
            return self._extract_json(response) or {
                "answer": response,
                "quote": "",
                "anno_summary": "AI 回答"
            }
        return {"answer": "抱歉，无法回答。", "quote": "", "anno_summary": "错误"}

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
