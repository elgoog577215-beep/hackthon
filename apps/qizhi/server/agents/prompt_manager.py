from pathlib import Path

from common.models import SystemException
from common.utils.logger import get_logger

logger = get_logger(__name__)


class PromptManager:
    """
    提示词管理器
    """

    _prompt_dir = Path(__file__).resolve().parent
    # 进程内缓存：避免每次请求都读磁盘
    _prompts: dict[str, str] | None = None

    @staticmethod
    def get_prompt(name: str, **placeholders: str) -> str:
        """获取提示词"""
        if PromptManager._prompts is None:
            # 从 agents/ 目录递归加载所有 .md 提示词文件
            prompts: dict[str, str] = {}
            for md_file in PromptManager._prompt_dir.rglob("*.md"):
                rel_path = md_file.relative_to(PromptManager._prompt_dir)
                if rel_path.name == "prompt.md":
                    # 统一命名为 prompt.md 时，用所在目录的最深层名作为 key
                    key = rel_path.parent.parts[-1] if rel_path.parent.parts else rel_path.stem
                else:
                    key = rel_path.stem
                prompts[key] = md_file.read_text(encoding="utf-8")
            PromptManager._prompts = prompts

        prompt = PromptManager._prompts.get(name, "")
        if not prompt:
            logger.error(f"[prompt_manager.py] 未找到提示词: {name}")
            raise SystemException(f"未找到提示词: {name}")
        # 注意：模板中的字面量花括号必须写成 {{ }}，否则会被 format 当占位符
        return prompt.format(**placeholders)
