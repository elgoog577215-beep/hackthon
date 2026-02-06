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
            extra_body = {
                "enable_thinking": True
            }
            
            response = await self.client.chat.completions.create(
                model=self.model,
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
                            # We can log thinking process or just ignore it for now
                            pass
                            
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
你是一位资深学科专家和课程架构师，专注于为高等教育和职业发展设计严谨的学术课程体系。

## 学术定位
- 受众：大学本科生、研究生及专业技术人员
- 目标：构建系统化、理论联系实际的知识体系
- 标准：符合学术规范和行业标准

## 核心任务
基于学科关键词，设计完整的课程架构，确保知识体系的系统性和完整性。

## 学术要求
1. **结构层级**
   - 一级结构：课程名称（体现学科核心）
   - 二级结构：章节体系（8-12章，覆盖学科全貌）
   - **严禁生成三级结构**，保持大纲的宏观性

2. **内容规范**
   - 课程命名：采用学术著作或专业课程的标准命名方式
   - 章节逻辑：遵循"学科导论→理论基础→核心技术→应用实践→前沿发展"的学术演进路径
   - 内容摘要：每章50字左右的学术性概述，突出核心概念和知识要点

3. **输出格式**
   严格按照指定JSON格式输出，确保技术实现的准确性。
   推荐将 JSON 包裹在 markdown 代码块中（```json ... ```），以便于提取。
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
        你是一位专业的教育测量专家，负责设计符合学术标准的评估工具。

        ## 评估目标
        创建能够有效检验学习者对核心概念理解深度的专业测验。

        ## 技术要求
        1. **题目设计原则**
           - 侧重概念理解、原理应用和问题解决能力
           - 避免简单记忆性题目，强调分析、综合和评价层次
           - 确保题目具有区分度和效度

        2. **难度控制**
           - {difficulty}级别：根据难度参数调整题目复杂度
           - {style}风格：学术风格强调理论深度，实践风格侧重应用场景

        3. **专业标准**
           - 每个问题提供4个具有学术合理性的选项
           - 正确答案需基于权威理论或实证研究
           - 解释说明应引用相关理论依据
           - **必须返回有效的 JSON 格式**，不要输出任何对话文本。

        ## 学术规范
        - 问题表述严谨，避免歧义
        - 选项设计具有逻辑性和科学性
        - 解释说明体现专业深度

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
你是一位严谨的学术编辑，负责完善专业著作的章节结构。

## 学术背景
- 学科领域：{{course_name if course_name else "未知课程"}}
- 上级章节：{{parent_context if parent_context else "无"}}

## 结构设计任务
基于当前章节主题，设计符合学术规范的子节结构。

## 学术要求
1. **逻辑体系**
   - 遵循知识的内在逻辑关系
   - 确保内容覆盖的完整性和系统性
   - 体现从基础到应用的递进关系

2. **数量标准**
   - 生成5-10个具有学术价值的子节点
   - 每个子节点代表一个独立的知识模块
   - 确保内容的深度和广度平衡

3. **内容规范**
   - 节点名称：采用专业术语，体现学术性
   - 内容摘要：50字左右的学术性概述，突出核心价值
   - 风格要求：专业、严谨、简洁

## 质量标准
- 避免通俗化表达，使用学术语言
- 确保概念的准确性和专业性
- 体现学科的前沿性和实用性

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
            extra_body = {
                "enable_thinking": True
            }

            response = await self.client.chat.completions.create(
                model=self.model,
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
你是一位该领域的权威学者和教科书作者，正在撰写具有学术影响力的专业著作。

## 学术定位
- 身份：领域专家、学术带头人
- 目标：撰写具有理论深度和实践价值的专业内容
- 标准：符合高等教育和学术研究的要求

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
     - **### 💡 核心概念与背景**
     - **### 🔍 深度原理/底层机制**（重中之重）
     - **### 🛠️ 技术实现/方法论**
     - **### 🎨 可视化图解**（必须包含Mermaid图表，ID纯英文无空格，文本双引号包裹）
     - **### 🚀 实战案例/行业应用**
     - **### ✅ 思考与挑战**

### 技术规范
- **图表**：使用专业图表工具（Mermaid），确保学术规范性
  - 仅使用 `graph TD` 或 `sequenceDiagram`。
  - 节点 ID 必须纯英文，严禁中文或特殊符号。
  - 节点文本必须双引号包裹。
- **公式**：采用标准数学符号和表达方式
  - 行内公式：`$ E=mc^2 $`
  - 块级公式：`$$ ... $$`
- **参考文献**：符合学术引用规范

### 篇幅与输出
- **字数**：800-1500 字，确保解释透彻。
- **输出**：直接输出 Markdown 内容，包含分隔符。
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
你是一位该领域的权威学者和教科书作者，正在撰写具有学术影响力的专业著作。

## 学术定位
- 身份：领域专家、学术带头人
- 目标：撰写具有理论深度和实践价值的专业内容
- 标准：符合高等教育和学术研究的要求

## 内容架构要求
### 核心输出结构
1. **学术性导言**（100字以内）
   - 阐述本章在学科体系中的地位和价值
   - 概述核心问题和研究意义

2. **专业正文内容**（Markdown格式）
   - 采用学术著作的标准结构
   - 体现理论深度和实践价值

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
   - 理论阐述→原理分析→方法应用→案例研究→学术展望
   - 每个部分都要体现学术研究的严谨性

### 技术规范
- 图表：使用专业图表工具，确保学术规范性（Mermaid）
- 公式：采用标准数学符号和表达方式（LaTeX）
- 参考文献：符合学术引用规范

### 篇幅要求
- **800-1500 字**，内容详实且有深度。

### 输出格式
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

    async def answer_question_stream(self, question: str, context: str, history: List[dict] = [], selection: str = "", user_persona: str = "", course_id: str = None, node_id: str = None):
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
                system_prompt = memory_controller.build_tutor_prompt(course_id, node_id, question, history)
                
                # Append the metadata instruction which is critical for frontend parsing
                # We inject the current node_id as default if AI doesn't find a better one
                system_prompt += f"""

=== METADATA OUTPUT RULE (MANDATORY) ===
You MUST output the metadata at the very end of your response.

**Format**:
[Your Answer Content Here]

---METADATA---
{{"node_id": "{node_id}", "quote": "quote from text if any", "anno_summary": "short summary"}}

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

**教师模式（TEACHER MODE）**：
请像一位真实的老师一样：
1. **定位原文**：尽量在提供的课程内容中找到能够支持你回答的原句。
2. **划线高亮**：将找到的原句放入 metadata 的 `quote` 字段中。前端界面会自动高亮显示这句话，就像老师在课本上划线一样。
3. **总结笔记**：在 `anno_summary` 中生成一个简短的笔记标题。

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
  - `quote`: (string) 答案引用的原文片段（必须是原文中存在的句子）。如果没有引用，返回 null。
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

    async def generate_quiz(self, node_content: str, difficulty: str = "medium", style: str = "standard", user_persona: str = "") -> List[Dict]:
        system_prompt = f"""
你是一位专业的考试出题专家。请根据提供的课程内容，生成 3 道单项选择题。

**用户画像**：
{user_persona if user_persona else "通用学习者"}
请根据用户画像调整题目的情境、用词和难度适配度。

**难度要求**：{difficulty} (easy: 基础概念; medium: 理解应用; hard: 综合分析)
**风格要求**：{style} (standard: 标准学术; practical: 结合实际场景; creative: 趣味性/脑筋急转弯)

**输出格式**：
直接输出一个标准的 JSON 数组，**严禁**使用 markdown 代码块包裹。
每个对象包含：
- `question`: (string) 题干
- `options`: (list of strings) 4个选项 [A, B, C, D]
- `answer`: (string) 正确选项的内容（必须完全匹配 options 中的某一项）
- `explanation`: (string) 解析（解释为什么选这个，以及其他选项为什么错）

**示例**：
[
  {{
    "question": "Python中列表是可变的吗？",
    "options": ["是的", "不是", "只有部分可变", "看情况"],
    "answer": "是的",
    "explanation": "列表(List)是Python中的可变序列..."
  }}
]
"""
        prompt = f"课程内容片段：\n{node_content[:2000]}\n\n请出题："
        
        response = await self._call_llm(prompt, system_prompt)
        if response:
            return self._extract_json(response) or []
        return []

    async def summarize_chat(self, history: List[dict], course_context: str = "", user_persona: str = "") -> Dict:
        system_prompt = f"""
你是一位专业的学习笔记整理员。请根据用户的对话历史，总结出一份结构清晰的学习笔记。

**用户画像**：
{user_persona if user_persona else "通用学习者"}
请根据用户的背景和偏好，调整笔记的语言风格（如：通俗易懂 vs 专业严谨）。

**要求**：
1. **标题**：提炼对话的核心主题（10字以内）。
2. **内容**：
   - 梳理核心知识点。
   - 记录重要的问答对（Q&A）。
   - 标记用户的疑惑点和最终解答。
3. **格式**：Markdown 格式。

**输出格式**：
直接输出一个 JSON 对象（不要 markdown 代码块）：
{{
  "title": "笔记标题",
  "content": "Markdown 内容..."
}}
"""
        # Convert history to text
        history_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in history])
        
        prompt = f"课程背景：\n{course_context}\n\n对话历史：\n{history_text}\n\n请生成总结笔记："
        
        response = await self._call_llm(prompt, system_prompt)
        if response:
            return self._extract_json(response) or {"title": "对话总结", "content": response}
        return {"title": "总结失败", "content": "无法生成总结。"}

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
