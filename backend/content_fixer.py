"""
内容修正器模块

自动修正生成内容中的常见问题：
- 章节编号错误
- 缺失的可视化元素
- 格式规范化
- 内容结构补全
"""

import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from discipline_config import DisciplineType, get_discipline_config
from content_validator import ContentValidator, ValidationResult


@dataclass
class FixResult:
    """修正结果"""
    original: str
    fixed: str
    changes: List[str]
    needs_regenerate: bool = False
    
    def to_dict(self) -> Dict:
        return {
            "original_length": len(self.original),
            "fixed_length": len(self.fixed),
            "changes": self.changes,
            "needs_regenerate": self.needs_regenerate
        }


class ContentFixer:
    """内容修正器"""
    
    def __init__(self):
        self.validator = ContentValidator()
        
        self.chinese_nums = {
            "一": "1", "二": "2", "三": "3", "四": "4", "五": "5",
            "六": "6", "七": "7", "八": "8", "九": "9", "十": "10"
        }
    
    def fix_node(
        self, 
        node: Dict, 
        discipline_type: DisciplineType,
        parent_chapter: str = None
    ) -> Tuple[Dict, FixResult]:
        """
        修正节点内容
        
        Args:
            node: 节点数据
            discipline_type: 学科类型
            parent_chapter: 父章节编号
            
        Returns:
            (修正后的节点, 修正结果)
        """
        original_node = node.copy()
        changes = []
        
        node_level = node.get("node_level", 1)
        
        if node_level == 1:
            node, l1_changes = self._fix_l1_node(node)
            changes.extend(l1_changes)
        elif node_level == 2:
            node, l2_changes = self._fix_l2_node(node, discipline_type, parent_chapter)
            changes.extend(l2_changes)
        
        fix_result = FixResult(
            original=str(original_node),
            fixed=str(node),
            changes=changes,
            needs_regenerate=self._needs_regenerate(node, discipline_type)
        )
        
        return node, fix_result
    
    def _fix_l1_node(self, node: Dict) -> Tuple[Dict, List[str]]:
        """修正 L1 章节节点"""
        changes = []
        
        if node.get("node_content") and len(node["node_content"].strip()) > 50:
            node["node_content"] = ""
            changes.append("清空 L1 章节的 node_content")
        
        node_name = node.get("node_name", "")
        if not re.match(r"^第[一二三四五六七八九十]+章\s+.+", node_name):
            if not node_name.startswith("第"):
                node["node_name"] = f"第{self._num_to_chinese(node.get('_index', 1))}章 {node_name}"
                changes.append(f"修正章节命名格式：{node_name} → {node['node_name']}")
        
        return node, changes
    
    def _fix_l2_node(
        self, 
        node: Dict, 
        discipline_type: DisciplineType,
        parent_chapter: str
    ) -> Tuple[Dict, List[str]]:
        """修正 L2 子章节节点"""
        changes = []
        
        if parent_chapter:
            node, numbering_changes = self._fix_chapter_numbering(node, parent_chapter)
            changes.extend(numbering_changes)
        
        content = node.get("node_content", "")
        if content:
            fixed_content, content_changes = self._fix_content(content, discipline_type)
            node["node_content"] = fixed_content
            changes.extend(content_changes)
        
        return node, changes
    
    def _fix_chapter_numbering(self, node: Dict, parent_chapter: str) -> Tuple[Dict, List[str]]:
        """修正章节编号"""
        changes = []
        node_name = node.get("node_name", "")
        expected_prefix = f"{parent_chapter}."
        
        match = re.match(r'^(\d+)\.(\d+)\s+(.+)', node_name)
        if match:
            current_chapter = match.group(1)
            section_num = match.group(2)
            title = match.group(3)
            
            if current_chapter != parent_chapter:
                new_name = f"{expected_prefix}{section_num} {title}"
                node["node_name"] = new_name
                changes.append(f"修正章节编号：{node_name} → {new_name}")
        else:
            match = re.match(r'^(\d+)\.(\d+)?\s*(.*)', node_name)
            if match:
                section_num = match.group(2) or "1"
                title = match.group(3) or node_name
                new_name = f"{expected_prefix}{section_num} {title}"
                node["node_name"] = new_name
                changes.append(f"添加章节编号前缀：{node_name} → {new_name}")
        
        return node, changes
    
    def _fix_content(self, content: str, discipline_type: DisciplineType) -> Tuple[str, List[str]]:
        """修正内容"""
        changes = []
        config = get_discipline_config(discipline_type)
        
        content, latex_changes = self._fix_latex_syntax(content)
        changes.extend(latex_changes)
        
        content, mermaid_changes = self._fix_mermaid_syntax(content)
        changes.extend(mermaid_changes)
        
        content, section_changes = self._ensure_required_sections(content, config)
        changes.extend(section_changes)
        
        return content, changes
    
    def _fix_latex_syntax(self, content: str) -> Tuple[str, List[str]]:
        """修正 LaTeX 语法"""
        changes = []
        
        content = re.sub(r'\\\[(.+?)\\\]', r'\n$$\n\1\n$$\n', content, flags=re.DOTALL)
        changes.append("转换 \\[...\\] 为 $$...$$")
        
        content = re.sub(r'\\\((.+?)\\\)', r'$\1$', content, flags=re.DOTALL)
        changes.append("转换 \\(...\\) 为 $...$")
        
        def fix_broken_aligned(match):
            full_match = match.group(0)
            inner = match.group(1) if match.lastindex else ''
            
            inner = re.sub(r'\$\s*$', '', inner)
            inner = re.sub(r'^\s*\$', '', inner)
            inner = re.sub(r'\$\$', '', inner)
            inner = re.sub(r'\\\$', '\\\\', inner)
            inner = re.sub(r'\\\s*$', '\\\\', inner, flags=re.MULTILINE)
            inner = re.sub(r'\\\s*\n', '\\\\\n', inner)
            
            return f'$$\n\\begin{{aligned}}\n{inner}\n\\end{{aligned}}\n$$'
        
        content = re.sub(
            r'\\begin\{aligned\}(.*?)(?:\\end\{aligned\}|$)',
            fix_broken_aligned,
            content,
            flags=re.DOTALL
        )
        changes.append("修复 \\begin{aligned} 格式")
        
        def fix_broken_env(match):
            env_name = match.group(1)
            inner = match.group(2) if match.lastindex and match.lastindex >= 2 else ''
            
            inner = re.sub(r'\$\s*$', '', inner)
            inner = re.sub(r'^\s*\$', '', inner)
            inner = re.sub(r'\$\$', '', inner)
            inner = re.sub(r'\\\$', '\\\\', inner)
            inner = re.sub(r'\\\s*$', '\\\\', inner, flags=re.MULTILINE)
            
            return f'$$\n\\begin{{{env_name}}}\n{inner}\n\\end{{{env_name}}}\n$$'
        
        content = re.sub(
            r'\\begin\{(matrix|pmatrix|bmatrix|vmatrix|cases|eqnarray|gather|split)\}(.*?)(?:\\end\{\1\}|$)',
            fix_broken_env,
            content,
            flags=re.DOTALL
        )
        changes.append("修复 LaTeX 环境格式")
        
        content = re.sub(r'\$\s+', '$', content)
        content = re.sub(r'\s+\$', '$', content)
        changes.append("清理公式内空格")
        
        return content, changes
    
    def _fix_mermaid_syntax(self, content: str) -> Tuple[str, List[str]]:
        """修正 Mermaid 语法"""
        changes = []
        
        def fix_mermaid_block(match):
            mermaid_content = match.group(1)
            original = mermaid_content
            
            def safe_quote(text):
                text = text.strip()
                if not text.startswith('"'):
                    inner = text.replace('"', '\\"')
                    return f'"{inner}"'
                return text
            
            mermaid_content = re.sub(
                r'(\w+)\[([^\]"]+)\]',
                lambda m: f'{m.group(1)}[{safe_quote(m.group(2))}]',
                mermaid_content
            )
            
            if mermaid_content != original:
                changes.append("修正 Mermaid 节点引号")
            
            return f'```mermaid{mermaid_content}```'
        
        content = re.sub(r'```mermaid(.*?)```', fix_mermaid_block, content, flags=re.DOTALL)
        
        return content, changes
    
    def _ensure_required_sections(self, content: str, config) -> Tuple[str, List[str]]:
        """确保必填板块存在"""
        changes = []
        existing_sections = self.validator.extract_sections(content)
        
        for section in config.content_sections:
            if section.required and section.emoji.strip() not in existing_sections:
                placeholder = self._generate_section_placeholder(section)
                content += f"\n\n{placeholder}"
                changes.append(f"添加缺失板块：{section.emoji} {section.name}")
        
        return content, changes
    
    def _generate_section_placeholder(self, section) -> str:
        """生成板块占位符"""
        placeholders = {
            "💡 核心定义与物理意义": "### 💡 核心定义与物理意义\n\n[待补充：核心概念定义与物理/几何意义]",
            "🔍 定理陈述与证明推导": "### 🔍 定理陈述与证明推导\n\n[待补充：定理陈述与完整证明/推导过程]",
            "🛠️ 算法步骤与计算方法": "### 🛠️ 算法步骤与计算方法\n\n[待补充：具体算法步骤或计算方法]",
            "🎨 可视化图解": "### 🎨 可视化图解\n\n```mermaid\ngraph TD\n    A[\"概念\"] --> B[\"应用\"]\n```",
            "🏭 工程与科研应用": "### 🏭 工程与科研应用\n\n[待补充：工程应用或科研案例]",
            "✅ 推导题与证明题": "### ✅ 推导题与证明题\n\n[待补充：基于本节内容的练习题]",
            "💡 核心概念与技术背景": "### 💡 核心概念与技术背景\n\n[待补充：技术背景与核心概念]",
            "🔍 技术原理与底层机制": "### 🔍 技术原理与底层机制\n\n[待补充：底层原理与机制]",
            "🛠️ 代码实现与架构设计": "### 🛠️ 代码实现与架构设计\n\n```python\n# 待补充：代码示例\n```",
            "🏭 工程实践与最佳实践": "### 🏭 工程实践与最佳实践\n\n[待补充：工程实践案例与最佳实践]",
            "✅ 思考与实战挑战": "### ✅ 思考与实战挑战\n\n[待补充：思考题与实战练习]",
        }
        
        key = f"{section.emoji} {section.name}"
        return placeholders.get(key, f"### {section.emoji} {section.name}\n\n[待补充内容]")
    
    def _needs_regenerate(self, node: Dict, discipline_type: DisciplineType) -> bool:
        """判断是否需要重新生成"""
        content = node.get("node_content", "")
        
        if len(content) < 200:
            return True
        
        validation = self.validator.validate_node(node, discipline_type)
        
        error_count = sum(1 for i in validation.issues if i.severity.value == "error")
        
        return error_count >= 3
    
    def _num_to_chinese(self, num: int) -> str:
        """数字转中文"""
        chinese_nums_rev = {v: k for k, v in self.chinese_nums.items()}
        return chinese_nums_rev.get(str(num), "一")
    
    def fix_chapter_numbers_in_course(self, course_data: Dict) -> Dict:
        """
        修正整个课程的章节编号
        
        Args:
            course_data: 课程数据
            
        Returns:
            修正后的课程数据
        """
        nodes = course_data.get("nodes", [])
        
        l1_nodes = [n for n in nodes if n.get("node_level") == 1]
        l2_nodes = [n for n in nodes if n.get("node_level") == 2]
        
        l1_id_to_chapter = {}
        for i, l1 in enumerate(l1_nodes, 1):
            l1_id_to_chapter[l1["node_id"]] = str(i)
            
            node_name = l1.get("node_name", "")
            if not re.match(r"^第[一二三四五六七八九十]+章", node_name):
                title = re.sub(r'^第?\d*章?\s*', '', node_name)
                l1["node_name"] = f"第{self._num_to_chinese(i)}章 {title}"
        
        for l2 in l2_nodes:
            parent_id = l2.get("parent_node_id")
            if parent_id in l1_id_to_chapter:
                chapter_num = l1_id_to_chapter[parent_id]
                
                node_name = l2.get("node_name", "")
                match = re.match(r'^(\d+)\.(\d+)\s+(.+)', node_name)
                if match:
                    section_num = match.group(2)
                    title = match.group(3)
                    new_name = f"{chapter_num}.{section_num} {title}"
                    if new_name != node_name:
                        l2["node_name"] = new_name
        
        return course_data


__all__ = ["ContentFixer", "FixResult"]
