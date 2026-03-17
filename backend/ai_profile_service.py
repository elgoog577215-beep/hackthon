"""
学习者画像 AI 服务

提供画像生成（全量/增量）、Agent 评论、精简摘要三个核心方法。
全部使用 fast model 以节省 token。
"""

import logging
import sys
import os

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from ai_base import AIBase
from prompts import (
    GENERATE_LEARNER_PROFILE,
    GENERATE_LEARNER_PROFILE_INCREMENTAL,
    GENERATE_AGENT_COMMENTARY,
    GENERATE_PERSONA_SUMMARY,
)

logger = logging.getLogger(__name__)


class AIProfileService(AIBase):
    """学习者画像 AI 服务"""

    async def generate_profile(
        self,
        wrong_answers: list,
        notes: list,
        chat_summary: str,
        self_evaluation: str,
        current_profile: str | None = None,
        mode: str = "full",
        new_content: str | None = None,
    ) -> str | None:
        """
        生成或增量更新学习者画像。

        Args:
            wrong_answers: 错题列表
            notes: 笔记列表
            chat_summary: 聊天摘要
            self_evaluation: 用户自评
            current_profile: 当前画像（增量模式）
            mode: "full" 全量 | "incremental" 增量
            new_content: 新增内容描述（增量模式）
        """
        if mode == "incremental" and current_profile:
            prompt = f"""## 当前画像
{current_profile}

## 新增内容
{new_content or '无'}

## 用户自我评价
{self_evaluation or '无'}"""
            system = GENERATE_LEARNER_PROFILE_INCREMENTAL.system_prompt
        else:
            # 全量模式：组装所有学习数据
            wa_text = self._format_wrong_answers(wrong_answers)
            notes_text = self._format_notes(notes)
            prompt = f"""## 错题记录
{wa_text or '暂无错题记录'}

## 笔记内容
{notes_text or '暂无笔记'}

## 问答历史摘要
{chat_summary or '暂无问答记录'}

## 用户自我评价
{self_evaluation or '无'}"""
            system = GENERATE_LEARNER_PROFILE.system_prompt

        result = await self._call_llm(prompt, system_prompt=system, use_fast_model=True)
        return result

    async def generate_commentary(self, ai_profile: str) -> str | None:
        """基于 AI 画像生成系统独立评论。"""
        prompt = f"""## AI 画像分析
{ai_profile}"""
        result = await self._call_llm(
            prompt,
            system_prompt=GENERATE_AGENT_COMMENTARY.system_prompt,
            use_fast_model=True,
        )
        return result

    async def generate_persona_summary(
        self, ai_profile: str, self_evaluation: str = ""
    ) -> str | None:
        """将完整画像压缩为精简版（<200字），用于注入 prompt。"""
        prompt = f"""## 学习者画像
{ai_profile}

## 用户自我评价
{self_evaluation or '无'}"""
        result = await self._call_llm(
            prompt,
            system_prompt=GENERATE_PERSONA_SUMMARY.system_prompt,
            use_fast_model=True,
        )
        return result

    # ------------------------------------------------------------------
    # 内部工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _format_wrong_answers(wrong_answers: list) -> str:
        """将错题列表格式化为文本，按知识点（节点）分组。"""
        if not wrong_answers:
            return ""
        # 按节点分组
        by_node: dict[str, list] = {}
        for wa in wrong_answers:
            node = wa.get("nodeName", "未知")
            by_node.setdefault(node, []).append(wa)

        lines = []
        for node, items in by_node.items():
            lines.append(f"【{node}】共 {len(items)} 题错误：")
            for wa in items:
                q = wa.get("question", "")
                correct = wa.get("correctIndex", -1)
                user = wa.get("userIndex", -1)
                options = wa.get("options", [])
                correct_text = options[correct] if 0 <= correct < len(options) else "?"
                user_text = options[user] if 0 <= user < len(options) else "?"
                lines.append(f"  - {q} (正确: {correct_text} / 选了: {user_text})")
        return "\n".join(lines)

    @staticmethod
    def _format_notes(notes: list) -> str:
        """将笔记列表格式化为文本，区分 AI 笔记和用户笔记。"""
        if not notes:
            return ""

        ai_notes = [n for n in notes if n.get("sourceType") == "ai"]
        user_notes = [n for n in notes if n.get("sourceType") in (None, "user")]

        lines = []
        if user_notes:
            lines.append("【用户手写笔记】")
            for i, note in enumerate(user_notes, 1):
                content = note.get("content", "")
                lines.append(f"{i}. {content}")

        if ai_notes:
            if lines:
                lines.append("")
            lines.append("【用户困惑并提问AI的内容】")
            for i, note in enumerate(ai_notes, 1):
                quote = note.get("quote", "")
                lines.append(f"{i}. {quote}" if quote else f"{i}. (无引用内容)")

        return "\n".join(lines)
