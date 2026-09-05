"""雷达图算法验证脚本。

使用示例:
    cd server && uv run python tests/test_radar_chart.py

脚本读取 tests/chaoxing_analyze.json 与 tests/chaoxing_transcript.json，
组装为 VideoAnalysisResult 的字典格式后调用 calculate_radar_chart，
打印六维得分及各维度的中间指标。
"""

import importlib.util
import json
import sys
from pathlib import Path

# 将 server 目录加入路径
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# 直接加载 algorithm.py，避免 service.video 包触发大量连锁导入
_algo_path = BASE_DIR / "service" / "video" / "algorithm.py"
_spec = importlib.util.spec_from_file_location("algorithm", str(_algo_path))
_algorithm = importlib.util.module_from_spec(_spec)
sys.modules["algorithm"] = _algorithm
_spec.loader.exec_module(_algorithm)
calculate_radar_chart = _algorithm.calculate_radar_chart


def load_json(filename: str) -> dict:
    filepath = BASE_DIR / "tests" / filename
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    analyze = load_json("chaoxing_analyze.json")
    transcript = load_json("chaoxing_transcript.json")

    # 组装为 service 层传入 algorithm 的 result 字典格式
    data = analyze.get("data", {})
    result = {
        "transcript": transcript.get("result", {}).get("transcript", []),
        "audio_duration": transcript.get("result", {}).get("audioDuration"),
        "teach_content": data.get("teach_content"),
        "teach_question": data.get("teach_question"),
        "class_summary": data.get("class_summary"),
        "class_education_summary": data.get("class_education_summary"),
        "knowledge_graph": data.get("knowledge_graph"),
        "teach_db_result": data.get("teach_db_result"),
        "teach_knowledge": data.get("teach_knowledge"),
        "teach_summary": data.get("teach_summary"),
        "teach_wh": data.get("teach_wh"),
    }

    radar = calculate_radar_chart(result)

    print("=" * 50)
    print("六维雷达图得分")
    print("=" * 50)
    for dim, score in radar.items():
        print(f"  {dim}: {score}")
    print("=" * 50)
    print(f"  总时长: {result['audio_duration'] / 60:.1f} 分钟")


if __name__ == "__main__":
    main()
