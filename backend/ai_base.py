"""
AI 基础服务模块 - LLM 调用层

提供与大语言模型交互的基础能力：
- AsyncOpenAI 客户端初始化与模型配置
- 通用 LLM 调用（含重试、流式聚合）
- 流式 LLM 调用（生成器）
- JSON 提取、Mermaid/LaTeX 语法修复等工具方法
- 学科类型检测、章节编号提取等辅助方法

所有 AI 子服务均继承此基类。
"""

import os
import re
import json
import logging
import sys
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from openai import AsyncOpenAI
from typing import List, Dict, Optional

# 加载环境变量（必须在读取环境变量之前调用）
load_dotenv()

# 添加项目根目录到系统路径以导入共享配置
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
from shared.prompt_config import DIFFICULTY_LEVELS, TEACHING_STYLES, DifficultyLevel, TeachingStyle

# ============================================================================
# 配置与常量
# ============================================================================

# 配置日志记录
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# API密钥加载与验证
api_key = os.getenv("AI_API_KEY")
if api_key:
    masked_key = f"{api_key[:8]}...{api_key[-4:]}"
    logger.info(f"Loaded AI_API_KEY: {masked_key}")
else:
    logger.error("AI_API_KEY not found in environment variables")


# ============================================================================
# AI 基础服务类
# ============================================================================

class AIBase:
    """
    AI 模型交互的基础抽象层。
    支持根据任务复杂性在不同模型之间切换。
    所有 AI 子服务均继承此类。
    """
    def __init__(self):
        # 通过环境变量配置 API 密钥
        self.api_key = os.getenv("AI_API_KEY")
        self.api_base = os.getenv("AI_API_BASE", "https://api-inference.modelscope.cn/v1")
        
        # 混合模型策略
        # 智能模型：用于复杂推理、创意写作和详细解释。
        self.model_smart = os.getenv("AI_MODEL", "Qwen/Qwen3-32B")
        
        # 快速模型：用于摘要、分类和简单任务。
        # 如果未指定，默认使用更小、更快的模型。
        self.model_fast = os.getenv("AI_MODEL_FAST", "Qwen/Qwen3-32B")
        
        if self.api_key:
            self.client = AsyncOpenAI(
                base_url=self.api_base,
                api_key=self.api_key,
            )
        else:
            self.client = None
            logger.warning("AI_API_KEY not found. AI features will be disabled.")

    # ============================================================================
    # 辅助工具方法
    # ============================================================================

    def _detect_discipline_type(self, course_name: str, keyword: str = "") -> str:
        """
        根据课程名称和关键词自动识别学科类型
        
        Args:
            course_name: 课程名称
            keyword: 课程关键词
            
        Returns:
            学科类型: "natural_science", "humanities", "skill_based"
        """
        text = f"{course_name} {keyword}".lower()
        
        natural_science_keywords = [
            "量子", "力学", "物理", "化学", "代数", "几何", "数学", "算法", 
            "统计", "机器学习", "深度学习", "编程", "计算机", "工程", "电子",
            "热力", "量子力学", "线性代数", "微积分", "概率", "数据结构",
            "神经网络", "优化", "计算", "科学", "技术"
        ]
        
        humanities_keywords = [
            "哲学", "伦理", "历史", "文学", "艺术", "社会学", "政治", "思想",
            "文化", "宗教", "美学", "逻辑", "认识论", "本体论", "形而上学",
            "辩证", "存在主义", "现象学", "诠释学"
        ]
        
        skill_based_keywords = [
            "辩论", "演讲", "写作", "设计", "实践", "沟通", "谈判", "领导力",
            "项目管理", "创业", "营销", "销售", "面试", "职场", "技能",
            "口才", "表达", "演示", "汇报"
        ]
        
        natural_score = sum(1 for kw in natural_science_keywords if kw in text)
        humanities_score = sum(1 for kw in humanities_keywords if kw in text)
        skill_score = sum(1 for kw in skill_based_keywords if kw in text)
        
        if skill_score > natural_score and skill_score > humanities_score:
            return "skill_based"
        elif humanities_score > natural_score:
            return "humanities"
        else:
            return "natural_science"

    def _extract_chapter_number(self, node_name: str) -> str:
        """
        从节点名称中提取章节编号
        
        Args:
            node_name: 节点名称，如"第三章 热力学定律"
            
        Returns:
            章节编号，如"3"
        """
        chinese_nums = {
            "一": "1", "二": "2", "三": "3", "四": "4", "五": "5",
            "六": "6", "七": "7", "八": "8", "九": "9", "十": "10"
        }
        
        patterns = [
            r"第([一二三四五六七八九十]+)章",
            r"第(\d+)章",
            r"^(\d+)\.",
            r"^(\d+) "
        ]
        
        for pattern in patterns:
            match = re.search(pattern, node_name)
            if match:
                result = match.group(1)
                if result in chinese_nums:
                    return chinese_nums[result]
                return result
        
        return "1"

    def _extract_used_cases(self, existing_content: str) -> List[str]:
        """
        从已有内容中提取已使用的案例
        
        Args:
            existing_content: 已生成的课程内容
            
        Returns:
            已使用的案例列表
        """
        used_cases = []
        
        case_patterns = [
            r"案例[：:]\s*([^\n]+)",
            r"例如[：:，]?\s*([^\n]+)",
            r"实例[：:]\s*([^\n]+)",
            r"应用场景[：:]\s*([^\n]+)",
        ]
        
        for pattern in case_patterns:
            matches = re.findall(pattern, existing_content)
            used_cases.extend(matches)
        
        return list(set(used_cases))[:10]

    # ============================================================================
    # 内容解析工具方法
    # ============================================================================
    
    def _extract_json(self, text: str) -> Optional[Dict]:
        """
        从 LLM 响应中稳健地提取 JSON。
        
        提取策略（按优先级）：
        1. 直接解析完整响应
        2. 从 markdown JSON 代码块提取
        3. 从任意代码块提取
        4. 从文本中查找 JSON 对象边界
        
        Args:
            text: LLM 原始响应文本
            
        Returns:
            解析后的字典，失败返回 None
        """
        logger.info(f"Raw AI Response for JSON extraction: {text[:200]}...")

        # 策略1: 直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 策略2: 从 markdown JSON 代码块提取
        json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError as e:
                logger.warning(f"Markdown JSON decode error: {e}")
                pass

        # 策略3: 从任意代码块提取
        code_match = re.search(r'```\s*(.*?)\s*```', text, re.DOTALL)
        if code_match:
            try:
                return json.loads(code_match.group(1))
            except json.JSONDecodeError:
                pass

        # 策略4: 从文本边界提取
        try:
            start_idx = text.find('{')
            end_idx = text.rfind('}')
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                json_str = text[start_idx:end_idx+1]
                return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(f"Substring JSON decode error: {e}")
            pass

        # 所有策略失败
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
        修复 Mermaid 图表语法错误。
        
        主要修复：
        - 节点标签引号转义
        - 特殊字符处理
        - 不同图表类型的适配
        
        Args:
            text: 包含 Mermaid 图表的文本
            
        Returns:
            修复后的文本
        """
        pattern = r'```mermaid(.*?)```'
        
        def fix_mermaid_block(match):
            content = match.group(1)
            
            # 检测图表类型
            clean_lines = [line.strip() for line in content.split('\n') 
                           if line.strip() and not line.strip().startswith('%%')]
            
            if not clean_lines:
                return f'```mermaid{content}```'
                
            first_word = clean_lines[0].split(' ')[0]
            
            # 仅对流程图应用节点标签修复
            # 其他图表类型（序列图、类图等）的括号有特殊含义
            if first_word not in ['graph', 'flowchart']:
                return f'```mermaid{content}```'

            def safe_quote(text):
                """确保文本被双引号包裹，内部引号转义。"""
                text = text.strip()
                inner = text
                # 转义现有双引号
                inner = inner.replace('"', '\\"')
                return f'"{inner}"'

            # 修复各种节点形状的标签
            # 1. 方括号: [Text] -> ["Text"]
            content = re.sub(r'(?<!\[)\[(?![\[])([^\[\]]+?)(?<!\])\](?!\])', 
                             lambda m: f'[{safe_quote(m.group(1))}]', 
                             content)
            
            # 2. 圆括号: (Text) -> ("Text")
            content = re.sub(r'(?<!\()(\()(?![(\[])([^()]+?)(?<!\))(\))(?![\)])', 
                             lambda m: f'({safe_quote(m.group(2))})', 
                             content)
            
            # 3. 花括号: {Text} -> {"Text"}
            content = re.sub(r'(?<!\{)\{(?![{!])([^{}]+?)(?<!\})\}(?!\})', 
                             lambda m: f'{{{safe_quote(m.group(1))}}}', 
                             content)
            
            # 4. 双花括号: {{Text}} -> {{"Text"}}
            content = re.sub(r'\{\{([^{}]+?)\}\}', 
                             lambda m: f'{{{{{safe_quote(m.group(1))}}}}}', 
                             content)
            
            # 5. 双圆括号: ((Text)) -> (("Text"))
            content = re.sub(r'\(\(([^()]+?)\)\)', 
                             lambda m: f'(({safe_quote(m.group(1))}))', 
                             content)
            
            return f'```mermaid{content}```'

        return re.sub(pattern, fix_mermaid_block, text, flags=re.DOTALL)

    def _clean_latex_syntax(self, text: str) -> str:
        """
        修复和规范化 LaTeX 语法。
        
        转换规则：
        1. \\[ ... \\] -> $ ... $ (块级公式)
        2. \\( ... \\) -> $ ... $ (行内公式)
        3. 复杂环境自动包裹在 $ 中
        4. 清理多余空行
        
        Args:
            text: 包含 LaTeX 的文本
            
        Returns:
            规范化后的文本
        """
        # 1. 转换块级公式标记
        text = re.sub(r'\\\[(.*?)\\\]', r'\n$\n\1\n$\n', text, flags=re.DOTALL)
        
        # 2. 转换行内公式标记
        text = re.sub(r'\\\((.*?)\\\)', r'$\1$', text, flags=re.DOTALL)
        
        # 3. 确保复杂环境被 $ 包裹
        envs = r"matrix|pmatrix|bmatrix|vmatrix|Vmatrix|array|align|align\*|equation|equation\*|cases|gather|gather\*|alignat|alignat\*"
        pattern = fr'(\$\$)?\s*(\\begin{{({envs})}}.*?\\end{{\3}})\s*(\$\$)?'
        
        def fix_latex_block(match):
            content = match.group(2)
            return f"\n$\n{content.strip()}\n$\n"

        text = re.sub(pattern, fix_latex_block, text, flags=re.DOTALL)
        
        # 4. 清理多余空行（最多保留2个）
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text

    def clean_response_text(self, text: str) -> str:
        """
        清理 LLM 响应文本。
        
        处理流程：
        1. 去除 markdown 代码块包装
        2. 修复 LaTeX 语法
        3. 修复 Mermaid 语法
        
        Args:
            text: 原始响应文本
            
        Returns:
            清理后的文本
        """
        clean_text = text.strip()
        
        # 去除 ```markdown 包装
        if clean_text.startswith("```markdown") and clean_text.endswith("```"):
            clean_text = clean_text[11:-3].strip()
            
        # 修复 LaTeX
        clean_text = self._clean_latex_syntax(clean_text)
        
        # 修复 Mermaid
        clean_text = self._clean_mermaid_syntax(clean_text)
        
        return clean_text

    # ============================================================================
    # 核心 LLM 调用方法
    # ============================================================================
    
    async def _call_llm(
        self, 
        prompt: str, 
        system_prompt: str = "You are a helpful assistant.", 
        use_fast_model: bool = False,
        retry_count: int = 3
    ) -> str:
        """
        通用 LLM 调用函数。
        
        特性：
        - 支持模型路由（智能模型 vs 快速模型）
        - 支持流式响应
        - 自动处理推理内容日志
        - 包含重试机制
        
        Args:
            prompt: 用户输入提示
            system_prompt: 系统指令
            use_fast_model: 是否使用轻量/快速模型
            retry_count: 最大重试次数
            
        Returns:
            LLM 完整响应文本，失败返回 None
        """
        if not self.api_key:
            return None
        
        for attempt in range(retry_count):
            try:
                extra_body = {"enable_thinking": False}
                
                # 模型选择
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
                
                # 聚合流式响应
                full_content = ""
                async for chunk in response:
                    if chunk.choices:
                        # 处理推理内容（用于日志/调试）
                        if hasattr(chunk.choices[0].delta, 'reasoning_content'):
                            reasoning = chunk.choices[0].delta.reasoning_content
                            if reasoning:
                                print(reasoning, end='', flush=True)
                                
                        delta = chunk.choices[0].delta
                        if delta.content:
                            full_content += delta.content
                
                if not full_content:
                    logger.warning(f"Empty response from AI (Attempt {attempt+1}/{retry_count})")
                    if attempt < retry_count - 1:
                        await asyncio.sleep(1)
                        continue
                    return None

                logger.info(f"AI Response Complete (Model: {model_id})")
                return full_content

            except Exception as e:
                logger.error(f"AI API Call Error (Attempt {attempt+1}/{retry_count}): {e}")
                if attempt < retry_count - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
        
        return None

    async def _stream_llm(
        self,
        prompt: str,
        system_prompt: str = "You are a helpful assistant.",
        use_fast_model: bool = False
    ):
        """
        流式 LLM 调用 - 生成器函数

        以流式方式调用LLM，逐块返回生成的内容，
        适用于实时显示长文本生成过程。

        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词
            use_fast_model: 是否使用快速模型

        Yields:
            生成的文本块
        """
        if not self.api_key:
            yield "AI Service not configured."
            return

        try:
            extra_body = {"enable_thinking": False}

            # 选择模型
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
                    # 处理推理内容（用于日志/调试）
                    if hasattr(chunk.choices[0].delta, 'reasoning_content'):
                        reasoning = chunk.choices[0].delta.reasoning_content
                        if reasoning:
                            # 可以记录思考过程或暂时忽略
                            pass

                    delta = chunk.choices[0].delta
                    if delta.content:
                        yield delta.content
        except Exception as e:
            logger.error(f"Stream Error: {e}")
            yield f"\n[Error: {str(e)}]"
