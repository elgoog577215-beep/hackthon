import re
import subprocess
from enum import Enum
from pathlib import Path

from markitdown import MarkItDown

from common.models import BizException, SystemException
from common.models.constants import (
    CHAT_ATTACHMENT_MAX_CHARS_PER_FILE,
    CHAT_ATTACHMENT_MAX_CHARS_TOTAL,
    PANDOC_TIMEOUT,
)
from common.utils.logger import get_logger


logger = get_logger(__name__)


def convert_markdown_to_word(markdown_content: str) -> bytes:
    """将 Markdown 字符串转换为 docx 文件"""
    result = subprocess.run(
        ["pandoc", "-f", "markdown", "-t", "docx", "-o", "-"],
        input=markdown_content.encode("utf-8"),
        capture_output=True,
        timeout=PANDOC_TIMEOUT,
    )
    if result.returncode != 0:
        logger.error(f"[file.py] markdown 转换为 docx 失败 (exit {result.returncode}): {result.stderr.decode('utf-8', errors='replace')}")
        raise SystemException(
            f"markdown 转换为 docx 失败 (exit {result.returncode}): {result.stderr.decode('utf-8', errors='replace')}",
        )
    return result.stdout


def convert_file_to_markdown(path: str | Path) -> str:
    """使用 markitdown 将文件转换为 Markdown 文本"""
    try:
        md = MarkItDown()
        result = md.convert(str(path))
        return result.text_content
    except Exception as e:
        logger.error(f"[file.py] markitdown 转换失败: {path}, error={e}")
        raise BizException(f"文件转换失败: {e}")


def convert_file_to_markdown_safe(path: str | Path) -> str:
    """转换附件为 Markdown 文本；失败（解析异常 / 文件缺失）只告警并返回空串，
    不抛出——避免单个坏附件导致整个对话请求 500 或历史加载失败。"""
    try:
        return convert_file_to_markdown(path)
    except Exception as e:
        logger.warning(f"[file.py] 附件解析失败，已跳过: {path}, error={e}")
        return ""


def build_attachment_text(file_paths: list[str] | None) -> str:
    """把上传的附件批量解析为可注入对话上下文的纯文本块。

    - 每个附件转成 Markdown，超过单文件上限按字符截断；
    - 多附件累计超过总上限后停止追加；
    - 解析失败的附件自动跳过；
    - 无可用内容时返回空串。
    """
    if not file_paths:
        return ""
    logger.info(f"[file.py] 开始解析对话附件 {len(file_paths)} 个: {file_paths}")
    blocks: list[str] = []
    total = 0
    for index, path in enumerate(file_paths, start=1):
        if not Path(path).exists():
            # 多副本部署/上传与对话不在同一文件系统时最常见：上传成功但对话进程读不到文件
            logger.warning(f"[file.py] 附件文件不存在（上传与对话是否共享存储？）: {path}")
            continue
        text = convert_file_to_markdown_safe(path)
        if not text.strip():
            # markitdown 未报错但没取到文字：多为扫描件/图片型 PDF 或空文档
            logger.warning(f"[file.py] 附件解析结果为空（疑似扫描件/图片型 PDF 或空文档）: {path}")
            continue
        if len(text) > CHAT_ATTACHMENT_MAX_CHARS_PER_FILE:
            text = text[:CHAT_ATTACHMENT_MAX_CHARS_PER_FILE] + "\n…（该附件内容过长，已截断）"
        ext = Path(path).suffix.lstrip(".").lower() or "file"
        block = f"=== 附件{index}（{ext}） ===\n{text}"
        if total + len(block) > CHAT_ATTACHMENT_MAX_CHARS_TOTAL:
            remaining = CHAT_ATTACHMENT_MAX_CHARS_TOTAL - total
            if remaining > 0:
                blocks.append(block[:remaining] + "\n…（附件内容过多，已截断）")
            break
        blocks.append(block)
        total += len(block)
    logger.info(f"[file.py] 对话附件解析完成: 注入 {len(blocks)}/{len(file_paths)} 个, 共 {total} 字符")
    return "\n\n".join(blocks)


def compose_user_message(query: str, attachment_text: str | None) -> str:
    """把附件文本拼到用户问题后面，作为真正喂给 LLM 的 user 消息内容。
    无附件文本时原样返回 query（保持气泡/历史干净）。"""
    if not attachment_text:
        return query
    return (
        f"{query}\n\n"
        "【以下是用户上传的附件内容，请结合附件作答】\n"
        f"{attachment_text}"
    )


def extract_video_cover(video_path: str | Path) -> str:
    """使用 ffmpeg 从视频提取第一帧作为封面。"""
    cover_path = str(Path(video_path).with_suffix(".jpg"))
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(video_path),
            "-ss", "00:00:01", "-vframes", "1",
            cover_path,
        ],
        check=True,
        capture_output=True,
    )
    return cover_path


def count_text_words(content: str) -> int:
    """统计字数（中文按字计数，英文/数字按词计数）"""
    pattern = re.compile(r"[\u4e00-\u9fff]|[A-Za-z0-9]+(?:[._'-][A-Za-z0-9]+)*")
    return len(pattern.findall(content))


class FileFormatEnum(str, Enum):
    """
    文件格式枚举
    """
    WORD = "docx"  # DOCX
    MARKDOWN = "md"  # Markdown
