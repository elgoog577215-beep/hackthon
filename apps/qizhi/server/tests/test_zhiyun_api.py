"""
智云课堂开放平台接口交互式测试脚本。

使用示例:
    cd server && python -m tests.test_zhiyun_api

或直接运行:
    cd server && python tests/test_zhiyun_api.py

需配置: ZHIYUN_APP_ID、ZHIYUN_SECRET；ZHIYUN_TOKEN 与 ZHIYUN_APP_KEY 二选一
（未配 token 时通过 GET /api/reqtoken 获取调试授权码）。

无法连接 api.zju.edu.cn（如 DNS 报错）时脚本会提示连接浙江大学 VPN，不会打印长 traceback。

支持交互式选择:
  1 - 只调用课程列表 zyktcoslist（日期、offset、pageSize 用脚本默认）
  2 - 只调用章节详情 zyktcosinfo
  3 - 先拉课程列表并展示摘要，再输入 courseId/subId 请求详情

接口响应直接在命令行打印 JSON；选项 3 下列表会额外打印摘要便于复制 courseId/subId。

学工号 xgh 带示例，可直接回车采用默认示例值；未在提示中给出示例的输入项仍须手动填写（或回车表示跳过，行为与原先一致）。
"""

import asyncio
import base64
import hashlib
import hmac
import json
import os
import sys
from datetime import datetime, timedelta

import httpx
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

load_dotenv(os.path.join(BASE_DIR, ".env"))

from common.config import settings
from common.models.constants import (
    ZHIYUN_COURSE_DETAIL_URL,
    ZHIYUN_COURSE_LIST_URL,
    ZHIYUN_REQTOKEN_URL,
)

# 与提示中「示例」一致，回车未输入时使用
DEFAULT_ZHIYUN_XGH = "0010759"


def _print_zju_vpn_hint(exc: BaseException) -> None:
    """浙大开放平台 host 多在校园网/VPN 内可解析，连接失败时提示用户。"""
    print(f"\n[失败] 无法连接浙大开放平台: {exc}")
    print("提示: 若 DNS 报错或超时，请先连接浙江大学 VPN（或校内网络）后再试。")


def _print_response_json(data: object) -> None:
    if isinstance(data, dict):
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(json.dumps({"_raw": data}, indent=2, ensure_ascii=False))


def extract_reqtoken(body: dict) -> str:
    data = body.get("data")
    if isinstance(data, dict):
        inner = data.get("data")
        if isinstance(inner, dict):
            t2 = inner.get("token")
            if isinstance(t2, str) and t2:
                return t2
        t = data.get("token")
        if isinstance(t, str) and t:
            return t
    t0 = body.get("token")
    if isinstance(t0, str) and t0:
        return t0
    print(f"[test_zhiyun_api.py] 响应中未找到 token: {body}")
    raise ValueError(f"响应中未找到 token: {body}")


async def ensure_token(client: httpx.AsyncClient) -> str:
    if settings.ZHIYUN_TOKEN:
        return settings.ZHIYUN_TOKEN
    r = await client.get(
        ZHIYUN_REQTOKEN_URL,
        params={"appid": settings.ZHIYUN_APP_ID, "appkey": settings.ZHIYUN_APP_KEY},
    )
    r.raise_for_status()
    return extract_reqtoken(r.json())


def build_zhiyun_code_signature(*, token: str, parameter: dict[str, str]) -> tuple[str, str]:
    """与 VideoService._build_zhiyun_code_signature 一致。"""
    payload = {"token": token, "parameter": parameter}
    json_str = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    code = base64.b64encode(json_str.encode("utf-8")).decode("ascii")
    sig = hmac.new(
        settings.ZHIYUN_SECRET.encode("utf-8"),
        code.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    signature = base64.b64encode(sig).decode("ascii")
    return code, signature


async def query_course_list(
    client: httpx.AsyncClient,
    token: str,
    *,
    xgh: str,
    sdate: str,
    edate: str,
    offset: int,
    page_size: int,
) -> dict:
    """接口 1：课程列表 POST zyktcoslist。"""
    parameter = {
        "appid": settings.ZHIYUN_APP_ID,
        "xgh": xgh,
        "offset": str(offset),
        "pageSize": str(page_size),
        "sdate": sdate,
        "edate": edate,
    }
    code, signature = build_zhiyun_code_signature(token=token, parameter=parameter)
    print(f"\n[接口 1] 课程列表 POST {ZHIYUN_COURSE_LIST_URL}")
    print(f"  parameter: {json.dumps(parameter, ensure_ascii=False)}")

    response = await client.post(
        ZHIYUN_COURSE_LIST_URL,
        data={"code": code, "signature": signature},
    )
    response.raise_for_status()
    data = response.json()
    print(f"HTTP 状态码: {response.status_code}")
    print("响应内容:")
    _print_response_json(data)
    return data if isinstance(data, dict) else {}


async def query_course_detail(
    client: httpx.AsyncClient,
    token: str,
    *,
    course_id: str,
    sub_id: str,
) -> dict:
    """接口 2：章节详情 POST zyktcosinfo。"""
    parameter = {
        "appid": settings.ZHIYUN_APP_ID,
        "courseId": str(course_id),
        "subId": str(sub_id),
    }
    code, signature = build_zhiyun_code_signature(token=token, parameter=parameter)
    print(f"\n[接口 2] 章节详情 POST {ZHIYUN_COURSE_DETAIL_URL}")
    print(f"  parameter: {json.dumps(parameter, ensure_ascii=False)}")

    response = await client.post(
        ZHIYUN_COURSE_DETAIL_URL,
        data={"code": code, "signature": signature},
    )
    response.raise_for_status()
    data = response.json()
    print(f"HTTP 状态码: {response.status_code}")
    print("响应内容:")
    _print_response_json(data)
    return data if isinstance(data, dict) else {}


DEFAULT_LIST_OFFSET = 0
DEFAULT_LIST_PAGE_SIZE = 20


def _default_date_range() -> tuple[str, str]:
    end_date = datetime.now()
    begin_date = end_date - timedelta(days=14)
    return begin_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")


def _extract_list_rows(resp: dict) -> list[dict]:
    block = resp.get("data")
    if not isinstance(block, dict):
        return []
    raw = block.get("list")
    ent = block.get("entity")
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if isinstance(ent, dict):
        return [ent]
    return []


def _print_list_summary(rows: list[dict], max_rows: int = 20) -> None:
    print(f"\n课程列表摘要（共 {len(rows)} 条，最多展示 {max_rows} 条）:")
    for i, row in enumerate(rows[:max_rows], start=1):
        cid = row.get("courseId") or row.get("course_id") or ""
        sid = row.get("subId") or row.get("sub_id") or ""
        name = row.get("courseName") or row.get("course_name") or ""
        sub = row.get("subTitle") or row.get("sub_title") or ""
        print(f"  {i}. courseId={cid!r} subId={sid!r} | {name} | {sub}")
    if len(rows) > max_rows:
        print(f"  ... 其余 {len(rows) - max_rows} 条见上方完整响应")


async def test_zhiyun_api():
    missing = []
    if not settings.ZHIYUN_APP_ID:
        missing.append("ZHIYUN_APP_ID")
    if not settings.ZHIYUN_SECRET:
        missing.append("ZHIYUN_SECRET")
    if missing:
        print(f"[错误] 缺少必要的环境变量: {', '.join(missing)}")
        print("请在 .env 中配置 ZHIYUN_APP_ID、ZHIYUN_SECRET。")
        return
    if not settings.ZHIYUN_TOKEN and not settings.ZHIYUN_APP_KEY:
        print("[错误] 未配置 ZHIYUN_TOKEN 且缺少 ZHIYUN_APP_KEY，无法调用 GET /api/reqtoken")
        return

    print("\n请选择要调用的接口:")
    print("  1 - 只调用课程列表 (zyktcoslist)")
    print("  2 - 只调用章节详情 (zyktcosinfo)")
    print("  3 - 先课程列表，再根据结果输入参数调章节详情")
    choice = input("请输入选项 (1/2/3): ").strip()

    if choice == "1":
        xgh = (
            input(f"请输入学工号 xgh (示例: {DEFAULT_ZHIYUN_XGH}，回车默认): ").strip()
            or DEFAULT_ZHIYUN_XGH
        )
        print(f"  使用 xgh: {xgh}")
        sdate, edate = _default_date_range()
        offset, page_size = DEFAULT_LIST_OFFSET, DEFAULT_LIST_PAGE_SIZE
        print(f"  使用默认: sdate={sdate}, edate={edate}, offset={offset}, pageSize={page_size}")
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                token = await ensure_token(client)
                await query_course_list(
                    client, token, xgh=xgh, sdate=sdate, edate=edate, offset=offset, page_size=page_size
                )
            print("\n[成功] 课程列表调用完成")
        except httpx.ConnectError as e:
            _print_zju_vpn_hint(e)
        except httpx.TimeoutException:
            print("\n[失败] 课程列表请求超时")
        except httpx.HTTPStatusError as e:
            print(f"\n[失败] 课程列表 HTTP 错误: {e.response.status_code}")
            print(f"响应内容: {e.response.text}")
        except Exception as e:
            print(f"\n[失败] 课程列表请求异常: {type(e).__name__}: {e}")

    elif choice == "2":
        course_id = input("请输入 courseId: ").strip()
        sub_id = input("请输入 subId: ").strip()
        if not course_id or not sub_id:
            print("[错误] courseId 与 subId 不能为空")
            return
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                token = await ensure_token(client)
                await query_course_detail(client, token, course_id=course_id, sub_id=sub_id)
            print("\n[成功] 章节详情调用完成")
        except httpx.ConnectError as e:
            _print_zju_vpn_hint(e)
        except httpx.TimeoutException:
            print("\n[失败] 章节详情请求超时")
        except httpx.HTTPStatusError as e:
            print(f"\n[失败] 章节详情 HTTP 错误: {e.response.status_code}")
            print(f"响应内容: {e.response.text}")
        except Exception as e:
            print(f"\n[失败] 章节详情请求异常: {type(e).__name__}: {e}")

    elif choice == "3":
        xgh = (
            input(f"请输入学工号 xgh (示例: {DEFAULT_ZHIYUN_XGH}，回车默认): ").strip()
            or DEFAULT_ZHIYUN_XGH
        )
        print(f"  使用 xgh: {xgh}")
        sdate, edate = _default_date_range()
        offset, page_size = DEFAULT_LIST_OFFSET, DEFAULT_LIST_PAGE_SIZE
        print(f"  列表默认: sdate={sdate}, edate={edate}, offset={offset}, pageSize={page_size}")

        list_ok = False
        detail_ok = False

        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                token = await ensure_token(client)
            except httpx.ConnectError as e:
                _print_zju_vpn_hint(e)
                print("\n[中止] 未取得 token，跳过列表与章节详情")
            else:
                list_resp: dict = {}
                try:
                    list_resp = await query_course_list(
                        client, token, xgh=xgh, sdate=sdate, edate=edate, offset=offset, page_size=page_size
                    )
                    print("\n[成功] 课程列表调用完成")
                    list_ok = True
                except httpx.ConnectError as e:
                    _print_zju_vpn_hint(e)
                    print("\n[失败] 课程列表网络连接失败")
                except httpx.TimeoutException:
                    print("\n[失败] 课程列表请求超时")
                except httpx.HTTPStatusError as e:
                    print(f"\n[失败] 课程列表 HTTP 错误: {e.response.status_code}")
                    print(f"响应内容: {e.response.text}")
                except Exception as e:
                    print(f"\n[失败] 课程列表请求异常: {type(e).__name__}: {e}")

                if not list_ok:
                    print("\n[中止] 列表未成功，跳过章节详情")
                else:
                    rows = _extract_list_rows(list_resp)
                    if list_resp.get("result") == "success" and rows:
                        _print_list_summary(rows)
                    elif list_resp.get("result") == "success":
                        print("\n[提示] 列表成功但 data 中无 list/entity 行，请根据上方完整响应填写 courseId/subId。")
                    else:
                        print(f"\n[提示] 列表业务未成功: result={list_resp.get('result')!r} info={list_resp.get('info')!r}")

                    course_id = input("\n请输入章节详情的 courseId: ").strip()
                    sub_id = input("请输入章节详情的 subId: ").strip()
                    if not course_id or not sub_id:
                        print("[提示] 未输入 courseId/subId，跳过章节详情")
                    else:
                        try:
                            await query_course_detail(client, token, course_id=course_id, sub_id=sub_id)
                            print("\n[成功] 章节详情调用完成")
                            detail_ok = True
                        except httpx.ConnectError as e:
                            _print_zju_vpn_hint(e)
                            print("\n[失败] 章节详情网络连接失败")
                        except httpx.TimeoutException:
                            print("\n[失败] 章节详情请求超时")
                        except httpx.HTTPStatusError as e:
                            print(f"\n[失败] 章节详情 HTTP 错误: {e.response.status_code}")
                            print(f"响应内容: {e.response.text}")
                        except Exception as e:
                            print(f"\n[失败] 章节详情请求异常: {type(e).__name__}: {e}")

        if list_ok and detail_ok:
            print("\n[全部成功] 两个接口均调用完成")
        elif list_ok or detail_ok:
            print("\n[部分成功] 仅部分接口调用完成")
        else:
            print("\n[全部失败] 两个接口均未成功完成")

    else:
        print(f"[错误] 无效选项: {choice}，请输入 1、2 或 3")


if __name__ == "__main__":
    asyncio.run(test_zhiyun_api())
