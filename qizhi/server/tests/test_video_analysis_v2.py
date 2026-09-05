"""
视频五维度分析（V2 新链路）测试脚本。

使用示例:
    cd server && PYTHONPATH=/Users/qyao/Code/edu_ai_home/server uv run python tests/test_video_analysis_v2.py

脚本读取 tests/chaoxing_analyze.json 与 tests/chaoxing_transcript.json，
调用 analyze_video_parallel() 生成五维度分析结果，验证：
1. 返回结构完整性（5 维度 + scores + radar_data + ai_summary）
2. 各维度评分范围 0-100
3. 雷达图数据结构
4. 输出结果保存到 tests/analysis_v2_result.json 供前端调试
"""

import asyncio
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from common.utils.logger import init_root_logger

init_root_logger()

from service.video.analysis.orchestrator import analyze_video_parallel


def load_json(filename: str) -> dict:
    filepath = BASE_DIR / "tests" / filename
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(filename: str, data: dict) -> str:
    filepath = BASE_DIR / "tests" / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return str(filepath)


async def test_analyze_video_parallel():
    """测试五维度并行分析入口。"""
    print("=" * 60)
    print("【测试】视频五维度分析 V2")
    print("=" * 60)

    # 1. 加载超星原始数据
    transcript_raw = load_json("chaoxing_transcript.json")
    analyze_raw = load_json("chaoxing_analyze.json")

    transcript_data = transcript_raw.get("result", {})
    analyze_data = analyze_raw.get("data", {})

    # 解析可能为 JSON 字符串的字段
    for field in ("teach_knowledge", "teach_summary", "teach_wh", "teach_question"):
        val = analyze_data.get(field)
        if isinstance(val, str):
            try:
                analyze_data[field] = json.loads(val)
            except Exception:
                pass

    print(f"\n[输入数据]")
    print(f"  transcript 条数: {len(transcript_data.get('transcript', []))}")
    print(f"  audioDuration: {transcript_data.get('audioDuration')} 秒")
    print(f"  analyze 字段数: {len(analyze_data)}")

    # 2. 执行分析
    print("\n[执行分析] 启动五维度并行分析...")
    result = await analyze_video_parallel(transcript_data, analyze_data)
    print("[执行分析] 完成")

    # 3. 验证结构完整性
    print("\n[结构验证]")
    required_top_keys = {
        "teaching_expression",
        "teaching_design",
        "knowledge_presentation",
        "interaction_quality",
        "ideological_integration",
        "scores",
        "radar_data",
        "ai_summary",
    }
    missing = required_top_keys - set(result.keys())
    assert not missing, f"缺少顶层字段: {missing}"
    print(f"  ✓ 顶层字段完整: {required_top_keys}")

    # 4. 验证评分
    print("\n[评分验证]")
    scores = result["scores"]
    score_keys = ["expression", "design", "knowledge", "interaction", "ideology", "overall"]
    for key in score_keys:
        val = scores.get(key)
        assert isinstance(val, int), f"scores.{key} 应为 int, 实际是 {type(val)}"
        assert 0 <= val <= 100, f"scores.{key} 应在 0-100 之间, 实际是 {val}"
        print(f"  ✓ {key:12s}: {val:3d} 分")

    # 5. 验证雷达图
    print("\n[雷达图验证]")
    radar = result["radar_data"]
    assert isinstance(radar, list) and len(radar) == 5, "radar_data 应为 5 项列表"
    for item in radar:
        assert "dimension" in item and "score" in item
        print(f"  ✓ {item['dimension']}: {item['score']} 分")

    # 6. 验证 AI 总评
    print("\n[AI 总评验证]")
    ai_summary = result["ai_summary"]
    assert isinstance(ai_summary, str) and len(ai_summary) > 0, "ai_summary 应为非空字符串"
    print(f"  ✓ 长度: {len(ai_summary)} 字符")
    print(f"  ✓ 预览: {ai_summary[:80]}...")

    # 7. 验证各维度子结构
    print("\n[子结构验证]")
    te = result["teaching_expression"]
    assert "volume_analysis" in te
    assert "speech_rate_analysis" in te
    assert "language_conciseness" in te
    print("  ✓ teaching_expression: volume / speech_rate / conciseness")

    td = result["teaching_design"]
    assert "segments" in td
    assert "type_distribution" in td
    assert "information_density" in td
    assert "introduction_analysis" in td
    assert "conclusion_analysis" in td
    print("  ✓ teaching_design: segments / type_distribution / density / intro / conclusion")

    kp = result["knowledge_presentation"]
    assert "knowledge_tree" in kp
    assert "word_cloud" in kp
    print("  ✓ knowledge_presentation: knowledge_tree / word_cloud")

    iq = result["interaction_quality"]
    assert "interaction_events" in iq
    assert "type_statistics" in iq
    assert "interaction_gaps" in iq
    assert "wh_distribution" in iq
    print("  ✓ interaction_quality: events / type_statistics / gaps / wh")

    ii = result["ideological_integration"]
    assert "ideological_events" in ii
    print("  ✓ ideological_integration: ideological_events")

    # 8. 保存结果供前端调试
    filepath = save_json("analysis_v2_result.json", result)
    print(f"\n[输出] 完整结果已保存: {filepath}")

    print("\n" + "=" * 60)
    print("【测试通过】所有验证项均通过")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_analyze_video_parallel())
