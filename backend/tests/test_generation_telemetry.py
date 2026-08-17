"""A-1 埋点的回归测试。

重点覆盖真实跑课时暴露出来的那个坑：并行生成（``asyncio.gather`` /
``create_task``）下帧链会穿进 asyncio 内部，阶段归因必须仍然落在业务模块上，
不能变成 ``runners.run``。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import generation_telemetry as gt
from tests import telemetry_fake_ai_layer as fake_ai_layer


@pytest.fixture
def telemetry_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("LINGZHI_GENERATION_TELEMETRY", "1")
    monkeypatch.setenv("LINGZHI_GENERATION_TELEMETRY_DIR", str(tmp_path))
    return tmp_path


def _read(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_disabled_by_default_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv("LINGZHI_GENERATION_TELEMETRY", raising=False)
    monkeypatch.setenv("LINGZHI_GENERATION_TELEMETRY_DIR", str(tmp_path))
    with gt.generation_run("off") as path:
        gt.record_call(model_id="m", status="completed", stream=False)
    assert not path.exists()


def test_records_stage_and_section(telemetry_dir):
    with gt.generation_run("r1") as path:
        with gt.stage("教案生成"):
            with gt.section("第1章第2节", purpose="lesson_plan"):
                gt.record_call(
                    model_id="m",
                    status="completed",
                    stream=False,
                    duration_ms=120,
                )
    record = _read(path)[0]
    assert record["stage"] == "教案生成"
    assert record["section"] == "第1章第2节"
    assert record["purpose"] == "lesson_plan"
    assert record["duration_ms"] == 120


def test_nested_stage_does_not_leak_after_exit(telemetry_dir):
    with gt.generation_run("r2") as path:
        with gt.stage("大纲"):
            gt.record_call(model_id="m", status="completed", stream=False)
        gt.record_call(model_id="m", status="completed", stream=False)
    outer, after = _read(path)
    assert outer["stage"] == "大纲"
    # 退出上下文后不应还挂着上一个阶段名。
    assert after["stage"] != "大纲"


def test_parallel_sections_do_not_cross_contaminate(telemetry_dir):
    """并行生成的每个小节必须各自持有自己的标签。"""

    async def one(index: int) -> None:
        with gt.section(f"第{index}节"):
            await asyncio.sleep(0)
            gt.record_call(model_id="m", status="completed", stream=False)

    async def main() -> None:
        with gt.stage("正文生成"):
            await asyncio.gather(*[one(i) for i in range(5)])

    with gt.generation_run("r3") as path:
        asyncio.run(main())

    records = _read(path)
    assert len(records) == 5
    assert {r["stage"] for r in records} == {"正文生成"}
    assert {r["section"] for r in records} == {f"第{i}节" for i in range(5)}


def test_attribution_survives_asyncio_task_boundary(telemetry_dir, monkeypatch):
    """``gather`` 直接包住库层协程时，不能把阶段名归到 asyncio 内部。

    真实跑一门课时这里挂过。要复现必须还原真实结构：``record_call`` 是从
    ``ai_base.py`` 里发出的，而 ``ai_base.py`` 在跳过名单里；并行生成又把
    ``_call_llm`` 的协程直接交给 ``gather``，所以业务帧根本不在这个 task 的
    ``f_back`` 链上——链条第二格直接就是 ``events.py``。

    旧实现会继续往上走到 ``runners.run`` 并把它当阶段名，8 节正文于是全部
    归到同一个假阶段，账单的阶段维度失效。正确行为是宁可留空、交给显式
    标注兜底，也不能编造一个 asyncio 内部名。
    """
    monkeypatch.setattr(
        gt,
        "_SELF_FILES",
        gt._SELF_FILES | {"telemetry_fake_ai_layer.py"},
    )

    async def main() -> None:
        # gather 直接包库层协程：这个 task 的帧链和协程链上都没有业务帧。
        await asyncio.gather(fake_ai_layer.call_llm(), fake_ai_layer.call_llm())

    with gt.generation_run("r4") as path:
        asyncio.run(main())

    for record in _read(path):
        assert record["stage"] not in {
            "runners",
            "base_events",
            "events",
            "tasks",
            "futures",
        }, f"阶段名被归到了 asyncio 内部：{record['caller']}"


def test_attribution_recovered_from_coroutine_chain(
    telemetry_dir, monkeypatch
):
    """``gather(业务协程)`` 时，帧链断了但协程链还留着业务名。

    这是并行生成最常见的形态：``gather`` 包的是 ``generate_lesson_plan``
    这样的业务协程，它再去 await 库层。``f_back`` 在 task 边界处就断了，
    但 ``cr_await`` 链仍然记录着「谁 await 了谁」，阶段名要从那里捞回来。
    """
    monkeypatch.setattr(
        gt,
        "_SELF_FILES",
        gt._SELF_FILES | {"telemetry_fake_ai_layer.py"},
    )

    async def generate_lesson_plan() -> None:
        await fake_ai_layer.call_llm()

    async def main() -> None:
        await asyncio.gather(generate_lesson_plan(), generate_lesson_plan())

    with gt.generation_run("r4c") as path:
        asyncio.run(main())

    for record in _read(path):
        assert "generate_lesson_plan" in record["caller"], record["caller"]


def test_explicit_stage_wins_when_frames_are_unavailable(
    telemetry_dir, monkeypatch
):
    """帧归因拿不到业务名时，显式标注必须仍然生效。

    这正是 ``course_*.py`` 加上 ``with stage(...)`` 之后的兜底路径。
    """
    monkeypatch.setattr(
        gt,
        "_SELF_FILES",
        gt._SELF_FILES | {"telemetry_fake_ai_layer.py"},
    )

    async def main() -> None:
        with gt.stage("正文生成"):
            await asyncio.gather(
                fake_ai_layer.call_llm(),
                fake_ai_layer.call_llm(),
            )

    with gt.generation_run("r4b") as path:
        asyncio.run(main())

    records = _read(path)
    assert len(records) == 2
    assert {r["stage"] for r in records} == {"正文生成"}


def test_markdown_sections_are_split_into_separate_blocks(telemetry_dir):
    """真实 prompt 是「Markdown 小节标题 + 内容」，必须按小节切开。

    只按空行切的话，复用的小节（课程账本）和每次都变的小节（当前小节契约）
    会被并成一块，重复量严重低估；小节又常只有二三十字，分块下限定太高会
    把它们全丢掉——真实跑一门课时账单里 ``context_blocks`` 全空就是这么来的。
    """
    shared = (
        "## 课程上下文账本\n"
        "本课程共 8 课时，面向大学一年级学生，主题是线性代数入门。\n"
    )
    with gt.generation_run("r10") as path:
        for index in range(3):
            gt.record_call(
                model_id="m",
                status="completed",
                stream=False,
                prompt=(
                    f"{shared}\n"
                    "## 当前小节契约\n"
                    f"本节要讲第 {index} 个主题，与其他小节不同。\n"
                ),
            )
    records = _read(path)
    # 每条至少切出两块：共享的账本 + 各自不同的小节契约。
    assert all(len(r["context_blocks"]) >= 2 for r in records)

    from collections import Counter

    sends = Counter(
        digest
        for record in records
        for digest, _ in record["context_blocks"]
    )
    # 共享小节被发了 3 次，独有小节各 1 次。
    assert 3 in sends.values()
    assert list(sends.values()).count(1) >= 3


def test_repeated_context_blocks_share_digest(telemetry_dir):
    shared = "这是一段足够长的共享上下文，会被反复发送给模型用于生成练习题。" * 3
    with gt.generation_run("r5") as path:
        for index in range(3):
            gt.record_call(
                model_id="m",
                status="completed",
                stream=False,
                prompt=f"{shared}\n\n请回答第 {index} 题。",
            )
    records = _read(path)
    digests = [r["context_blocks"][0][0] for r in records]
    # 同一份上下文在三次调用里必须是同一个指纹，否则统计不出重复量。
    assert len(set(digests)) == 1


def test_prompt_text_is_not_persisted(telemetry_dir):
    secret = "学习者张三的隐私档案内容，不应出现在账单里。" * 5
    with gt.generation_run("r6") as path:
        gt.record_call(
            model_id="m",
            status="completed",
            stream=False,
            prompt=secret,
            system_prompt=secret,
        )
    assert secret[:20] not in path.read_text(encoding="utf-8")


def test_provider_tokens_take_precedence_over_estimate(telemetry_dir):
    with gt.generation_run("r7") as path:
        gt.record_call(
            model_id="m",
            status="completed",
            stream=False,
            prompt="x" * 4000,
            input_tokens=123,
            output_tokens=45,
            tokens_source="provider",
        )
    record = _read(path)[0]
    assert record["input_tokens"] == 123
    assert record["output_tokens"] == 45
    assert record["tokens_source"] == "provider"


def test_record_never_raises_on_bad_input(telemetry_dir):
    """埋点失败绝不能影响业务调用。"""

    class Exploding:
        def __str__(self) -> str:
            raise RuntimeError("boom")

    with gt.generation_run("r8"):
        gt.record_call(
            model_id="m",
            status="completed",
            stream=False,
            extra={"bad": Exploding()},
        )


def test_retry_is_flagged(telemetry_dir):
    with gt.generation_run("r9") as path:
        gt.record_call(
            model_id="m",
            status="failed",
            stream=False,
            attempt=2,
            retry_reason="AIResponseTruncated",
        )
    record = _read(path)[0]
    assert record["is_retry"] is True
    assert record["retry_reason"] == "AIResponseTruncated"
