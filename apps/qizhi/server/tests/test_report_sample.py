"""
测试脚本：输入超星 object_id，生成本地视频分析报告 Word 文件。

使用示例:
    cd server && uv run python tests/test_report_sample.py
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from hashlib import md5
from pathlib import Path
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import httpx
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

load_dotenv(os.path.join(BASE_DIR, ".env"))

# ── Mock 模块避免导入链失败 ──
for mod_name in [
    "aliyun", "aliyun.log", "aliyun.log.logitem",
    "aliyun.log.putlogsrequest", "aliyun.log.logclient",
]:
    sys.modules[mod_name] = MagicMock()

import common.utils.logger as _logger_mod
_logger_mod.get_logger = lambda name: MagicMock(
    info=print, warning=print, error=print, exception=print
)

from common.config import settings
from common.models.constants import CHAOXING_ANALYZE_URL, CHAOXING_TRANSCRIPT_URL

DEFAULT_OBJECT_ID = "565369f8f3217c90d8fa42abaaaa0e5c"


def _build_chaoxing_enc(object_id: str) -> str:
    day = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")
    return md5(f"{object_id}{day}{settings.CHAOXING_ENC_KEY}".encode()).hexdigest()


def _parse_json_fields(data: dict) -> dict:
    """解析超星接口中仍是 JSON 字符串的字段（与 service.py 逻辑一致）。"""
    result = dict(data)
    for field in ("teach_knowledge", "teach_summary", "teach_wh"):
        val = result.get(field)
        if isinstance(val, str):
            try:
                result[field] = json.loads(val)
            except Exception:
                result[field] = []
        elif not isinstance(val, list):
            result[field] = []
    return result


async def fetch_data(object_id: str) -> dict:
    """调用超星转写 + 分析接口，组装为 VideoAnalysisResult 格式。"""
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(
            CHAOXING_TRANSCRIPT_URL,
            params={"objectid": object_id, "fid": settings.CHAOXING_FID},
        )
        resp.raise_for_status()
        transcript_data = resp.json()

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(
            CHAOXING_ANALYZE_URL,
            params={"objectId": object_id, "enc": _build_chaoxing_enc(object_id)},
        )
        resp.raise_for_status()
        analyze_data = resp.json()

    # 保存原始响应
    (BASE_DIR / "tests" / "chaoxing_transcript.json").write_text(
        json.dumps(transcript_data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (BASE_DIR / "tests" / "chaoxing_analyze.json").write_text(
        json.dumps(analyze_data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("原始数据已缓存到 tests/chaoxing_transcript.json 和 tests/chaoxing_analyze.json")

    data = analyze_data.get("data", {}) if isinstance(analyze_data, dict) else {}
    data = _parse_json_fields(data)

    return {
        "transcript": transcript_data.get("result", {}).get("transcript", []),
        "audio_duration": transcript_data.get("result", {}).get("audioDuration"),
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


async def generate_report(object_id: str) -> Path:
    print(f"\n正在获取 object_id={object_id} 的分析数据...")
    result = await fetch_data(object_id)

    from service.video.algorithm import calculate_radar_chart
    result["radar_chart"] = calculate_radar_chart(result)
    print("\n雷达图得分:")
    for dim, score in result["radar_chart"].items():
        print(f"  {dim}: {score}")

    print("\n正在生成图文报告...")
    from service.video.export import generate_video_analysis_report
    docx_bytes = await generate_video_analysis_report(
        video_name=f"测试视频_{object_id[:8]}", analysis_result=result
    )

    output_path = BASE_DIR / "tests" / f"report_{object_id[:8]}.docx"
    output_path.write_bytes(docx_bytes)
    print(f"\n报告已生成: {output_path}")
    print(f"文件大小: {len(docx_bytes) / 1024:.1f} KB")
    return output_path


async def main():
    missing = []
    if not settings.CHAOXING_FID:
        missing.append("CHAOXING_FID")
    if not settings.CHAOXING_ENC_KEY:
        missing.append("CHAOXING_ENC_KEY")
    if missing:
        print(f"[错误] 缺少环境变量: {', '.join(missing)}")
        return

    object_id = (
        input(f"请输入 object_id (示例: {DEFAULT_OBJECT_ID}，回车默认): ").strip()
        or DEFAULT_OBJECT_ID
    )
    print(f"  使用 object_id: {object_id}")

    try:
        await generate_report(object_id)
        print("\n[成功] 报告生成完成")
    except httpx.TimeoutException:
        print("\n[失败] 超星接口请求超时")
    except httpx.HTTPStatusError as e:
        print(f"\n[失败] HTTP 错误: {e.response.status_code}")
    except Exception as e:
        print(f"\n[失败] 异常: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
