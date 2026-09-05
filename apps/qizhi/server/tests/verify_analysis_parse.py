"""
快速验证：用本地 chaoxing JSON 文件跑分析模块，检查输出是否非空。
"""
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))


def main():
    # 加载本地 JSON（测试脚本已保存的原始数据）
    transcript_path = BASE_DIR / "tests" / "chaoxing_transcript.json"
    analyze_path = BASE_DIR / "tests" / "chaoxing_analyze.json"

    with open(transcript_path, encoding="utf-8") as f:
        transcript_raw = json.load(f)
    with open(analyze_path, encoding="utf-8") as f:
        analyze_raw = json.load(f)

    # 模拟完整的生产链路：
    # _fetch_transcript 返回 resp.get("result")
    transcript_data = transcript_raw.get("result", {})

    # _fetch_analyze 返回 resp.get("data") 并解析 JSON 字符串字段
    analyze_data = analyze_raw.get("data", {})
    _json_string_fields = ["teach_knowledge", "teach_summary", "teach_wh", "teach_question"]
    for field in _json_string_fields:
        val = analyze_data.get(field)
        if isinstance(val, str):
            try:
                analyze_data[field] = json.loads(val)
            except Exception:
                pass

    print("=" * 60)
    print("transcript_data keys:", list(transcript_data.keys())[:5])
    print("analyze_data keys:", list(analyze_data.keys()))
    print("=" * 60)

    # 1. expression
    from service.video.analysis.expression import (
        extract_volume_analysis,
        analyze_speech_rate,
        analyze_language_conciseness,
    )
    vol = extract_volume_analysis(analyze_data)
    print(f"volume_analysis: keys={list(vol.keys())}, has_data={bool(vol)}")

    speech = analyze_speech_rate(transcript_data, analyze_data)
    print(f"speech_rate: avg_cpm={speech.get('avg_cpm')}, result_len={len(speech.get('result', []))}")

    conciseness = analyze_language_conciseness(transcript_data)
    print(f"conciseness: total_word_count={conciseness.get('total_word_count')}, ratio={conciseness.get('filler_word_ratio')}")

    # 2. design
    from service.video.analysis.design import (
        flatten_segments,
        compute_type_distribution,
        compute_information_density,
    )
    segments = flatten_segments(analyze_data)
    print(f"segments: count={len(segments)}")
    if segments:
        print(f"  first={segments[0]}")

    type_dist = compute_type_distribution(segments)
    print(f"type_distribution: count={len(type_dist)}")

    density = compute_information_density(transcript_data, segments, analyze_data)
    print(f"information_density: avg={density.get('avg_density')}, result_len={len(density.get('result', []))}")

    # 3. knowledge
    from service.video.analysis.knowledge import (
        extract_knowledge_tree,
        generate_word_cloud,
    )
    kt = extract_knowledge_tree(analyze_data)
    print(f"knowledge_tree: count={len(kt)}")

    wc = generate_word_cloud(transcript_data, analyze_data)
    print(f"word_cloud: count={len(wc)}")
    if wc:
        print(f"  top3={wc[:3]}")

    # 4. interaction
    from service.video.analysis.interaction import (
        extract_interaction_events,
        compute_interaction_gaps,
        analyze_wh_distribution,
    )
    events = extract_interaction_events(analyze_data)
    print(f"interaction_events: count={len(events.get('interaction_events', []))}, stats={events.get('type_statistics')}")

    gaps = compute_interaction_gaps(analyze_data, transcript_data)
    print(f"interaction_gaps: count={len(gaps)}")

    wh = analyze_wh_distribution(analyze_data)
    print(f"wh_distribution: keys={list(wh.keys())}")

    # 5. ideology（异步）
    import asyncio
    from service.video.analysis.ideology import analyze_ideological_events
    ideology_events = asyncio.run(analyze_ideological_events(transcript_data, analyze_data))
    print(f"ideological_events: count={len(ideology_events)}")
    if ideology_events:
        print(f"  first={ideology_events[0]}")

    print("=" * 60)
    print("验证完成！如果上面 count 都是 0，说明还有解析问题。")


if __name__ == "__main__":
    main()
