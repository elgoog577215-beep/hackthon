"""大纲 / 教案 共享的 4 步生成流水线：分析 → 生成 → 事实核查 → 再优化。

设计要点：
- 第 1~3 步只发 ``loading`` 进度事件（不流正文），匹配前端「进度事件 + 只流最终稿」。
- 第 4 步（再优化）流式 yield 纯文本（最终稿），与旧实现的 SSE 字节流一致，
  因此前端取增量逻辑无需改动即可工作。
- 事实核查（第 3 步）当前为 ``verify_mode="llm"`` 的合理性核查，重点针对参考文献；
  预留 ``verify_mode="tool"`` 以便日后接入联网检索工具做「真验证」。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from typing import Any

from agents.llm import complete_chat, stream_chat
from agents.prompt_manager import PromptManager
from common.models import BizException
from common.utils import SseEventEnum, build_sse_response
from common.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class PipelineConfig:
    """4 步流水线的资源类型相关配置。"""

    doc_type: str             # 文档类型中文名，如「教学大纲」「教案」
    generate_prompt_key: str  # 第 2 步生成所用提示词 key（沿用现有 outline / teaching_plan）
    verify_mode: str = "llm"  # 事实核查方式；预留 "tool"（联网工具核验）


def _loading(stage: str, message: str) -> dict[str, Any]:
    return build_sse_response(SseEventEnum.LOADING, {"stage": stage, "message": message})


def _strip_code_fence(text: str) -> str:
    """去除 ```/```markdown 代码围栏，与前端 stripMarkdownCodeFence 对齐。"""
    t = (text or "").strip()
    if t.startswith("```"):
        lines = t.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    return t


def _chunks(text: str, size: int = 80) -> Iterator[str]:
    """把整段文本切成小块，模拟流式输出（用于「无需修订、直接定稿」分支）。"""
    for i in range(0, len(text), size):
        yield text[i : i + size]


def _parse_issues(findings: str) -> list[Any] | None:
    """解析核查输出的 issues。

    - 返回 ``[]``：明确无问题（可跳过修订，直接定稿）。
    - 返回非空 ``list``：发现问题，需修订。
    - 返回 ``None``：解析失败但有文本，按「需修订、数量未知」处理。
    """
    text = _strip_code_fence(findings)
    if not text:
        return []
    try:
        data = json.loads(text)
    except Exception:
        return None
    if isinstance(data, dict) and isinstance(data.get("issues"), list):
        return data["issues"]
    return None


async def run(
    cfg: PipelineConfig,
    *,
    task_description: str,
    reference_content: str,
    user_prompt: str,
) -> AsyncIterator[Any]:
    """执行 4 步流水线，yield 进度事件（dict）与最终稿文本块（str）。"""

    # ---- 1. 分析需求 / 建议改动 ----
    yield _loading("analyze", "正在分析需求…")
    analysis = ""
    try:
        analyze_prompt = PromptManager.get_prompt(
            "analyze",
            doc_type=cfg.doc_type,
            task_description=task_description,
            reference_content=reference_content,
        )
        analysis = (await complete_chat(system_prompt=analyze_prompt, user_prompt=user_prompt)).strip()
    except Exception as exc:  # 分析失败不致命：降级为空分析，继续生成
        logger.warning(f"[refine_pipeline] 分析步骤失败，降级为空分析：{exc}")

    # ---- 2. 生成初稿 ----
    yield _loading("generate", f"正在生成{cfg.doc_type}初稿…")
    gen_reference = reference_content
    if analysis:
        gen_reference = f"{reference_content}\n\n## 写作分析（请严格遵循）\n\n{analysis}"
    generate_prompt = PromptManager.get_prompt(
        cfg.generate_prompt_key,
        task_description=task_description,
        reference_content=gen_reference,
    )
    draft = _strip_code_fence(await complete_chat(system_prompt=generate_prompt, user_prompt=user_prompt))
    if not draft:
        raise BizException(f"{cfg.doc_type}生成失败：模型未返回内容")

    # ---- 3. 事实核查（重点：参考文献）----
    # 当前仅实现 llm 合理性核查；"tool"（联网工具核验）为 P3 预留，未接入前显式回退并告警，避免静默空转。
    if cfg.verify_mode != "llm":
        logger.warning(f"[refine_pipeline] verify_mode={cfg.verify_mode!r} 暂未实现，回退到 LLM 合理性核查")
    yield _loading("verify", "正在核查参考文献与事实…")
    findings_raw = ""
    try:
        verify_prompt = PromptManager.get_prompt("verify", doc_type=cfg.doc_type)
        findings_raw = (await complete_chat(
            system_prompt=verify_prompt,
            user_prompt=f"待核查的{cfg.doc_type}如下：\n\n{draft}",
        )).strip()
    except Exception as exc:  # 核查失败不致命：跳过 findings，直接定稿
        logger.warning(f"[refine_pipeline] 核查步骤失败，跳过：{exc}")

    issues = _parse_issues(findings_raw)

    # ---- 4. 再优化（流式最终稿）----
    if issues == []:
        # 明确无问题：直接把初稿作为最终稿流式输出，省去一次 LLM 调用
        yield _loading("refine", "未发现参考文献 / 事实问题，正在定稿…")
        for piece in _chunks(draft):
            yield piece
        return

    count_hint = f"发现 {len(issues)} 处问题，" if isinstance(issues, list) else ""
    yield _loading("refine", f"{count_hint}正在结合核查结果优化定稿…")
    try:
        refine_prompt = PromptManager.get_prompt(
            "refine",
            doc_type=cfg.doc_type,
            draft=draft,
            findings=findings_raw,
        )
    except Exception as exc:  # 拿不到 refine 提示词：兜底输出初稿，保证有结果
        logger.warning(f"[refine_pipeline] refine 提示词加载失败，输出初稿：{exc}")
        for piece in _chunks(draft):
            yield piece
        return

    streamed_any = False
    async for chunk in stream_chat(
        system_prompt=refine_prompt,
        user_prompt=user_prompt or "请根据上述核查结果完成定稿修订。",
    ):
        streamed_any = True
        yield chunk
    if not streamed_any:
        # 修订无输出：兜底输出初稿
        for piece in _chunks(draft):
            yield piece
