"""
视频分析 ReAct Agent。

system prompt 通用（从 prompt.md 加载），各模块分析通过 user prompt 的 task 传入。
入口为 stream()，支持流式返回 final_answer。
"""

import json
import re
from typing import AsyncIterator, Any

from agents.llm import stream_chat
from agents.prompt_manager import PromptManager
from common.utils.logger import get_logger

from .tool import fetch_transcript_ranges

logger = get_logger(__name__)

_TOOLS_SPEC = """[
  {
    "name": "fetch_transcript_ranges",
    "description": "根据时间段列表批量提取转录文本原文。",
    "parameters": {
      "type": "object",
      "properties": {
        "ranges": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "start": {"type": "number", "description": "开始时间（秒）"},
              "end": {"type": "number", "description": "结束时间（秒）"}
            },
            "required": ["start", "end"]
          },
          "description": "时间段列表，如 [{\"start\": 31, \"end\": 245}]"
        }
      },
      "required": ["ranges"]
    }
  }
]"""


async def stream(
    task: str,
    segments: list[dict],
    transcript_data: dict,
    *,
    max_rounds: int = 3,
) -> AsyncIterator[str]:
    """
    视频分析 ReAct Agent 流式入口。

    system prompt 通用（从 prompt.md 加载），各模块分析通过 task 传入。
    模型可自主调用 fetch_transcript_ranges 工具获取原文，边分析边选片段。
    """
    system_prompt = PromptManager.get_prompt("video_analyzer", tools=_TOOLS_SPEC)

    compact_segments = [
        {
            "start_time": s.get("start_time"),
            "end_time": s.get("end_time"),
            "type": s.get("type"),
            "content": (s.get("content") or "")[:100],
        }
        for s in segments
    ]

    initial_user = (
        f"分析任务：{task}\n\n"
        f"课程环节时序标注：\n{json.dumps(compact_segments, ensure_ascii=False, indent=2)}"
    )

    # history 中只保留 user/assistant，system prompt 每次通过参数传入
    history = [{"role": "user", "content": initial_user}]

    for i in range(max_rounds):
        content = ""
        async for chunk in stream_chat(
            system_prompt=system_prompt,
            user_prompt="",
            history=history,
            enable_thinking=False,
        ):
            content += chunk

        try:
            parsed = _parse_react_output(content)
        except Exception as e:
            logger.error(f"解析 ReAct 输出失败: {e}, content={content[:500]}")
            yield f"解析模型输出失败: {e}"
            return

        thought = parsed.get("thought", "")
        actions = parsed.get("actions", [])
        final_answer = parsed.get("final_answer")

        if final_answer and not actions:
            yield final_answer
            return

        if actions:
            observations = []
            for action in actions:
                tool_name = action.get("tool_name", "")
                args = action.get("args", {})

                try:
                    if tool_name == "fetch_transcript_ranges":
                        result = await fetch_transcript_ranges(
                            transcript_data, args.get("ranges", [])
                        )
                        observations.append({
                            "tool_name": tool_name,
                            "status": "success",
                            "result": result,
                        })
                    else:
                        observations.append({
                            "tool_name": tool_name,
                            "status": "error",
                            "result": f"未知工具: {tool_name}",
                        })
                except Exception as e:
                    logger.exception(f"工具 {tool_name} 执行失败")
                    observations.append({
                        "tool_name": tool_name,
                        "status": "error",
                        "result": str(e),
                    })

            history.append({
                "role": "assistant",
                "content": json.dumps(
                    {"thought": thought, "actions": actions}, ensure_ascii=False
                ),
            })
            history.append({
                "role": "user",
                "content": f"Observation: {json.dumps(observations, ensure_ascii=False)}",
            })
        else:
            logger.warning(f"模型未给出有效响应: {parsed}")
            break

    yield "抱歉，分析需要更多步骤，请稍后重试。"


async def analyze_introduction(segments: list[dict], transcript_data: dict) -> dict:
    """对课程导入环节进行大模型评判（包装 stream）。"""
    chunks = []
    async for chunk in stream(
        "分析课程导入环节质量，包括吸引注意力、知识衔接、目标明确、激发动机等维度",
        segments,
        transcript_data,
    ):
        chunks.append(chunk)
    return _parse_final_answer("".join(chunks))


async def analyze_conclusion(segments: list[dict], transcript_data: dict) -> dict:
    """对课程总结环节进行大模型评判（包装 stream）。"""
    chunks = []
    async for chunk in stream(
        "分析课程总结环节质量，包括重点回顾、知识结构化、承上启下、后续任务等维度",
        segments,
        transcript_data,
    ):
        chunks.append(chunk)
    return _parse_final_answer("".join(chunks))


# ---------------------------------------------------------------------------
# 私有辅助函数
# ---------------------------------------------------------------------------


def _parse_react_output(content: str) -> dict[str, Any]:
    """解析模型返回的 ReAct JSON，兼容 markdown 代码块包裹。"""
    content = content.strip()
    if content.startswith("```"):
        lines = content.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        content = "\n".join(lines).strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(content[start:end + 1])
            except json.JSONDecodeError:
                pass
        # 兜底：将原始文本包装为最小 ReAct 结构，避免上层崩溃
        return {"thought": "", "actions": [], "final_answer": content}


def _parse_final_answer(text: str) -> dict:
    """把 stream 输出的 final_answer 解析为结构化 dict，兼容瑕疵 JSON。"""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # 1. 尝试直接解析
    try:
        return json.loads(text)
    except Exception:
        pass

    # 2. 尝试提取花括号内的 JSON
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            pass

    # 3. 兜底：正则提取关键字段（兼容新旧两种结构）
    result: dict[str, Any] = {"score": 0, "evaluation": "", "exists": False}

    score_m = re.search(r'"score"\s*:\s*(\d+)', text)
    if score_m:
        result["score"] = int(score_m.group(1))

    eval_m = re.search(r'"evaluation"\s*:\s*"((?:\\.|[^"\\])*)"', text)
    if eval_m:
        result["evaluation"] = eval_m.group(1).replace('\\"', '"').replace('\\n', '\n')

    desc_m = re.search(r'"description"\s*:\s*"((?:\\.|[^"\\])*)"', text)
    if desc_m:
        result["description"] = desc_m.group(1).replace('\\"', '"').replace('\\n', '\n')

    time_m = re.search(r'"time_range"\s*:\s*"((?:\\.|[^"\\])*)"', text)
    if time_m:
        result["time_range"] = time_m.group(1)

    exists_m = re.search(r'"exists"\s*:\s*(true|false)', text, re.IGNORECASE)
    if exists_m:
        result["exists"] = exists_m.group(1).lower() == "true"

    # 兼容旧结构
    strengths: list[str] = []
    suggestions: list[str] = []
    for key, target in (("strengths", strengths), ("suggestions", suggestions)):
        m = re.search(rf'"{key}"\s*:\s*\[(.*?)\]', text, re.DOTALL)
        if m:
            items = re.findall(r'"((?:\\.|[^"\\])*)"', m.group(1))
            target.extend(i.replace('\\"', '"').replace('\\n', '\n') for i in items)
    if strengths:
        result["strengths"] = strengths
    if suggestions:
        result["suggestions"] = suggestions

    if not result.get("evaluation"):
        result["evaluation"] = text[:500]

    return result
