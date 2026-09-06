"""扮演 ``ai_base.py`` 的测试替身。

埋点的调用帧归因要跳过 LLM 库层去找业务帧。用真实的独立模块来扮演这个
库层，比 monkeypatch 测试文件自身更贴近真实结构——后者会把测试里的业务
函数一起跳过，测不出想测的东西。
"""

from __future__ import annotations

import asyncio

import generation_telemetry as gt


async def call_llm() -> None:
    """模拟 ``AIBase._call_llm``：在库层内部打点。"""
    await asyncio.sleep(0)
    gt.record_call(model_id="m", status="completed", stream=False)
