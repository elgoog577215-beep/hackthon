"""
AI 图表生成服务模块

负责 Mermaid 图表生成、Mermaid 代码提取和图表专用语法修复。
"""

import re
import logging
from typing import Dict, Any, Optional

from ai_base import AIBase
from prompts import get_prompt

logger = logging.getLogger(__name__)


class AIDiagramService(AIBase):
    """图表生成相关的 AI 服务"""

    async def generate_diagram(
        self,
        description: str,
        diagram_type: str = "flowchart",
        context: str = ""
    ) -> Dict[str, Any]:
        """
        生成 Mermaid 图表
        """
        prompt_template = get_prompt("generate_diagram")
        system_prompt = prompt_template.format(
            description=description,
            diagram_type=diagram_type,
            context=context or "无额外上下文"
        )
        
        user_prompt = f"""请根据以下描述生成一个 {diagram_type} 类型的 Mermaid 图表：

描述：{description}

{context if context else ""}

请只返回 Mermaid 代码块，不要包含任何解释。"""
        
        try:
            response = await self._call_llm(user_prompt, system_prompt)
            
            if not response:
                return {
                    "success": False,
                    "error": "AI服务未返回响应",
                    "diagram_code": None
                }
            
            # Extract Mermaid code from response
            diagram_code = self._extract_mermaid_code(response)
            
            if not diagram_code:
                return {
                    "success": False,
                    "error": "无法从AI响应中提取有效的Mermaid代码",
                    "raw_response": response[:500] if response else None
                }
            
            # Clean up the diagram code using diagram-specific cleaner
            diagram_code = self._clean_diagram_mermaid(diagram_code)
            
            return {
                "success": True,
                "diagram_code": diagram_code,
                "diagram_type": diagram_type,
                "description": description
            }
            
        except Exception as e:
            logger.error(f"Error generating diagram: {e}")
            return {
                "success": False,
                "error": f"生成图表时出错: {str(e)}",
                "diagram_code": None
            }
    
    def _extract_mermaid_code(self, response: str) -> Optional[str]:
        """
        从 AI 响应中提取 Mermaid 代码

        支持多种代码块格式和直接图表语法识别。
        """
        # Try to find code block with mermaid
        patterns = [
            r'```mermaid\s*\n(.*?)```',
            r'```\s*\n(graph|flowchart|sequenceDiagram|classDiagram|stateDiagram|erDiagram|gantt|pie|mindmap)\s+(.*?)```',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, response, re.DOTALL | re.IGNORECASE)
            if match:
                code = match.group(0)
                # Remove the ```mermaid and ``` markers
                code = re.sub(r'^```mermaid\s*\n', '', code, flags=re.IGNORECASE)
                code = re.sub(r'```\s*$', '', code)
                return code.strip()
        
        # If no code block found, check if response starts with graph or other diagram keywords
        lines = response.strip().split('\n')
        diagram_keywords = ['graph ', 'flowchart ', 'sequenceDiagram', 'classDiagram', 
                           'stateDiagram', 'erDiagram', 'gantt', 'pie ', 'mindmap']
        
        for i, line in enumerate(lines):
            stripped = line.strip().lower()
            if any(stripped.startswith(kw.lower()) for kw in diagram_keywords):
                # Found the start of diagram code
                return '\n'.join(lines[i:]).strip()
        
        return None
    
    def _clean_diagram_mermaid(self, code: str) -> str:
        """
        清理和修复常见的 Mermaid 语法问题（图表生成专用）

        处理特殊字符、HTML 标签、箭头格式等常见问题。
        与 ai_base.py 中的 _clean_mermaid_syntax 不同，此方法处理的是
        独立的 Mermaid 代码字符串，而非嵌入在 Markdown 文本中的代码块。

        Args:
            code: 原始 Mermaid 代码

        Returns:
            清理后的 Mermaid 代码
        """
        # Remove any markdown formatting that might have been included
        code = re.sub(r'^```.*\n?', '', code, flags=re.MULTILINE)
        code = re.sub(r'```\s*$', '', code)
        
        # Fix common issues with node labels
        # Ensure node text with special characters is properly quoted
        def fix_node_labels(match):
            node_id = match.group(1)
            node_text = match.group(2)
            brackets = match.group(3)
            
            # If text already has quotes, keep them
            if node_text.startswith('"') and node_text.endswith('"'):
                return f'{node_id}[{node_text}]'
            
            # If text has special characters, wrap in quotes
            if any(c in node_text for c in ['[', ']', '(', ')', '{', '}', '|', '"', ',', ';']):
                # Escape any existing double quotes
                node_text = node_text.replace('"', '\\"')
                return f'{node_id}["{node_text}"]'
            
            return match.group(0)
        
        # Fix square bracket nodes
        code = re.sub(r'(\w+)\[(.+?)\](\[|\(|\{)', fix_node_labels, code)
        
        # Remove any HTML tags that might break rendering
        code = re.sub(r'<[^>]+>', '', code)
        
        # Fix arrow spacing
        code = re.sub(r'--\s*>', '-->', code)
        code = re.sub(r'<-\s*--', '<--', code)
        code = re.sub(r'==\s*>', '==>', code)
        
        return code.strip()
