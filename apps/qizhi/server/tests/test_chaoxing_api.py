"""
超星接口交互式测试脚本。

使用示例:
    cd server && python -m tests.test_chaoxing_api

或直接运行:
    cd server && python tests/test_chaoxing_api.py

脚本支持交互式输入 object_id（带示例的项可直接回车采用示例值），可选择只查询转写接口、只查询分析接口、或同时查询两者。
查询结果分别覆盖写入 `tests/chaoxing_transcript.json` 与 `tests/chaoxing_analyze.json`，避免控制台过长。
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from hashlib import md5
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import httpx
from dotenv import load_dotenv

# 将 server 目录加入路径，以便复用项目配置
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# 加载 .env 文件，使 os.getenv 能读取到配置
load_dotenv(os.path.join(BASE_DIR, ".env"))

from common.config import settings
from common.models.constants import CHAOXING_ANALYZE_URL, CHAOXING_TRANSCRIPT_URL

# 与提示中「示例」一致，回车未输入时使用
DEFAULT_OBJECT_ID = "565369f8f3217c90d8fa42abaaaa0e5c"


def _url_with_query(base_url: str, params: dict) -> str:
    """GET 请求用：将查询参数拼到 URL 上（便于复制到浏览器或 curl）。"""
    qs = urlencode(params)
    return f"{base_url}?{qs}" if qs else base_url


def build_chaoxing_enc(object_id: str) -> str:
    """构建超星 enc 参数（与 service/video/service.py 保持一致）。"""
    enc = md5(
        f"{object_id}{datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d')}{settings.CHAOXING_ENC_KEY}".encode()
    ).hexdigest()
    return enc


def _normalize_analyze_data(data: dict) -> dict:
    """将超星分析接口返回数据中的 JSON 字符串字段反序列化为标准嵌套结构。

    超星接口在 `data` 层级下把 teach_knowledge / teach_summary / teach_wh
    等字段以 JSON 字符串形式返回，直接保存会导致二次转义、可读性差。
    本函数在写入文件前将其解析为原生 list/dict。
    """
    if not isinstance(data, dict):
        return data

    payload = data.get("data")
    if not isinstance(payload, dict):
        return data

    str_json_fields = ("teach_knowledge", "teach_summary", "teach_wh")
    for field in str_json_fields:
        value = payload.get(field)
        if isinstance(value, str):
            try:
                payload[field] = json.loads(value)
            except json.JSONDecodeError:
                # 保留原始字符串，避免解析失败导致数据丢失
                pass

    # 处理多层嵌套：teach_content 可能也是字符串 JSON（历史数据中出现过）
    teach_content = payload.get("teach_content")
    if isinstance(teach_content, str):
        try:
            payload["teach_content"] = json.loads(teach_content)
        except json.JSONDecodeError:
            pass

    return data


def _pretty_print_analyze_summary(data: dict) -> None:
    """在控制台打印分析接口关键字段摘要，方便快速验证。"""
    if not isinstance(data, dict):
        return
    payload = data.get("data")
    if not isinstance(payload, dict):
        return

    print("\n[分析结果摘要]")

    # teach_summary 片段统计
    teach_summary = payload.get("teach_summary")
    if isinstance(teach_summary, list):
        total_seg = sum(len(s.get("file_structure", [])) for s in teach_summary)
        print(f"  teach_summary : {len(teach_summary)} 个片段，共 {total_seg} 个 file_structure 节点")
    elif isinstance(teach_summary, str):
        print(f"  teach_summary : 字符串 (未解析)，长度 {len(teach_summary)}")

    # teach_knowledge 统计
    teach_knowledge = payload.get("teach_knowledge")
    if isinstance(teach_knowledge, list):
        non_empty = [k for k in teach_knowledge if k.get("file_structure")]
        print(f"  teach_knowledge: {len(teach_knowledge)} 个片段，{len(non_empty)} 个含知识结构")
    elif isinstance(teach_knowledge, str):
        print(f"  teach_knowledge: 字符串 (未解析)，长度 {len(teach_knowledge)}")

    # teach_question 统计
    teach_question = payload.get("teach_question")
    if isinstance(teach_question, dict):
        total_q = teach_question.get("total_questions", 0)
        stats = teach_question.get("statistics", {})
        print(f"  teach_question : {total_q} 个问题，{len(stats)} 种布鲁姆分类")

    # teach_wh 统计
    teach_wh = payload.get("teach_wh")
    if isinstance(teach_wh, list):
        print(f"  teach_wh       : {len(teach_wh)} 条 5W2H 标注")
    elif isinstance(teach_wh, str):
        print(f"  teach_wh       : 字符串 (未解析)，长度 {len(teach_wh)}")

    # class_education_summary 统计
    edu = payload.get("class_education_summary")
    if isinstance(edu, dict):
        summary = edu.get("summary", [])
        print(f"  class_education_summary: {len(summary)} 个思政片段")

    # teach_db_result 统计
    db_result = payload.get("teach_db_result")
    if isinstance(db_result, dict):
        db_data = db_result.get("data", {})
        total_sec = db_data.get("total_seconds")
        avg_spl = db_data.get("avg_spl")
        print(f"  teach_db_result: {total_sec} 个采样点，平均音量 {avg_spl} dB")


def _save_result(filename: str, data: dict) -> str:
    """将响应数据保存到 tests 目录下的 JSON 文件，返回文件绝对路径。"""
    output_dir = os.path.join(BASE_DIR, "tests")
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return filepath


async def query_transcript(object_id: str) -> dict:
    """查询超星转写接口（接口 1），结果保存到文件。"""
    params = {
        "objectid": object_id,
        "fid": settings.CHAOXING_FID,
    }
    full_url = _url_with_query(CHAOXING_TRANSCRIPT_URL, params)
    print(f"\n[接口 1] 转写接口请求: {full_url}")

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(CHAOXING_TRANSCRIPT_URL, params=params)
        response.raise_for_status()
        data = response.json()

    filepath = _save_result("chaoxing_transcript.json", data)
    print(f"HTTP 状态码: {response.status_code}")
    print(f"响应内容已保存到: {filepath}")
    return data


async def query_analyze(object_id: str) -> dict:
    """查询超星分析接口（接口 2），结果保存到文件。"""
    params = {
        "objectId": object_id,
        "enc": build_chaoxing_enc(object_id),
    }
    full_url = _url_with_query(CHAOXING_ANALYZE_URL, params)
    print(f"\n[接口 2] 分析接口请求: {full_url}")

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(CHAOXING_ANALYZE_URL, params=params)
        response.raise_for_status()
        data = response.json()

    # 保存原始响应（不做任何反序列化），方便对照真实结构
    # 生产环境中的 _fetch_analyze 会自动处理字符串 JSON 字段

    filepath = _save_result("chaoxing_analyze.json", data)
    print(f"HTTP 状态码: {response.status_code}")
    print(f"响应内容已保存到: {filepath}")

    # 打印关键字段摘要，方便快速验证
    _pretty_print_analyze_summary(data)

    return data


async def test_chaoxing_api():
    """交互式测试超星接口连通性。"""
    # 校验必要配置
    missing = []
    if not settings.CHAOXING_FID:
        missing.append("CHAOXING_FID")
    if not settings.CHAOXING_ENC_KEY:
        missing.append("CHAOXING_ENC_KEY")
    if missing:
        print(f"[错误] 缺少必要的环境变量: {', '.join(missing)}")
        print("请确保已在 .env 文件中配置超星相关参数。")
        return

    # 交互式询问 object_id（回车采用示例值）
    object_id = (
        input(f"请输入 object_id (示例: {DEFAULT_OBJECT_ID}，回车默认): ").strip()
        or DEFAULT_OBJECT_ID
    )
    print(f"  使用 object_id: {object_id}")

    # 交互式选择要查询的接口
    print("\n请选择要查询的接口:")
    print("  1 - 只查询转写接口")
    print("  2 - 只查询分析接口")
    print("  3 - 同时查询两个接口")
    choice = input("请输入选项 (1/2/3): ").strip()

    if choice == "1":
        try:
            await query_transcript(object_id)
            print("\n[成功] 转写接口查询完成")
        except httpx.TimeoutException:
            print("\n[失败] 转写接口请求超时")
        except httpx.HTTPStatusError as e:
            print(f"\n[失败] 转写接口 HTTP 错误: {e.response.status_code}")
            print(f"响应内容: {e.response.text}")
        except Exception as e:
            print(f"\n[失败] 转写接口请求异常: {type(e).__name__}: {e}")

    elif choice == "2":
        try:
            await query_analyze(object_id)
            print("\n[成功] 分析接口查询完成")
        except httpx.TimeoutException:
            print("\n[失败] 分析接口请求超时")
        except httpx.HTTPStatusError as e:
            print(f"\n[失败] 分析接口 HTTP 错误: {e.response.status_code}")
            print(f"响应内容: {e.response.text}")
        except Exception as e:
            print(f"\n[失败] 分析接口请求异常: {type(e).__name__}: {e}")

    elif choice == "3":
        transcript_ok = False
        analyze_ok = False

        try:
            await query_transcript(object_id)
            print("\n[成功] 转写接口查询完成")
            transcript_ok = True
        except httpx.TimeoutException:
            print("\n[失败] 转写接口请求超时")
        except httpx.HTTPStatusError as e:
            print(f"\n[失败] 转写接口 HTTP 错误: {e.response.status_code}")
            print(f"响应内容: {e.response.text}")
        except Exception as e:
            print(f"\n[失败] 转写接口请求异常: {type(e).__name__}: {e}")

        try:
            await query_analyze(object_id)
            print("\n[成功] 分析接口查询完成")
            analyze_ok = True
        except httpx.TimeoutException:
            print("\n[失败] 分析接口请求超时")
        except httpx.HTTPStatusError as e:
            print(f"\n[失败] 分析接口 HTTP 错误: {e.response.status_code}")
            print(f"响应内容: {e.response.text}")
        except Exception as e:
            print(f"\n[失败] 分析接口请求异常: {type(e).__name__}: {e}")

        if transcript_ok and analyze_ok:
            print("\n[全部成功] 两个接口均查询完成")
        elif transcript_ok or analyze_ok:
            print("\n[部分成功] 仅部分接口查询完成")
        else:
            print("\n[全部失败] 两个接口均查询失败")

    else:
        print(f"[错误] 无效选项: {choice}，请输入 1、2 或 3")


if __name__ == "__main__":
    asyncio.run(test_chaoxing_api())
