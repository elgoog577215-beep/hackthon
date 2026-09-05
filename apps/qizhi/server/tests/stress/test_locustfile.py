"""
Locust 压力测试脚本

Locust 优势：
- Web UI 实时监控（http://localhost:8089）
- 支持复杂场景编排（登录→操作→登出）
- 自动统计 RPS、延迟分布、失败率
- 支持分布式压测（多机部署）

安装:
    cd /Users/qyao/Code/edu_ai_home/server
    uv add --dev locust

运行（Web 模式）:
    cd /Users/qyao/Code/edu_ai_home/server
    PYTHONPATH=/Users/qyao/Code/edu_ai_home/server uv run locust -f tests/stress/test_locustfile.py --host=http://127.0.0.1:8000

运行（无头模式，命令行直接跑）:
    PYTHONPATH=/Users/qyao/Code/edu_ai_home/server uv run locust -f tests/stress/test_locustfile.py \
        --host=http://127.0.0.1:8000 \
        --headless -u 50 -r 10 -t 60s \
        --html report.html \
        --csv=stress_result

参数说明:
    -u 50      : 并发用户数
    -r 10      : 每秒启动用户数
    -t 60s     : 运行总时长
    --html     : 生成 HTML 报告
    --csv      : 导出 CSV 原始数据
"""

import os
from locust import HttpUser, task, between, events

# 从环境变量读取测试 Token
TEST_TOKEN = os.getenv("TEST_TOKEN", "")


class HealthCheckUser(HttpUser):
    """无认证接口压测用户"""
    wait_time = between(0.5, 2)

    @task(3)
    def health_check(self):
        with self.client.get("/health", catch_response=True) as resp:
            if resp.status_code == 200 and resp.json().get("status") == "ok":
                resp.success()
            else:
                resp.failure(f"Unexpected response: {resp.text}")


class AuthenticatedUser(HttpUser):
    """认证接口压测用户（需要有效 Token）"""
    wait_time = between(1, 3)
    host = "http://127.0.0.1:8000"

    def on_start(self):
        """每个虚拟用户启动时执行（类似 setUp）"""
        self.headers = {}
        if TEST_TOKEN:
            self.headers["Authorization"] = f"Bearer {TEST_TOKEN}"
        else:
            # 尝试自动登录获取 token（需要实现具体逻辑）
            pass

    @task(1)
    def ai_chat(self):
        """测试 AI 聊天接口（SSE）—— 这里只测连接建立"""
        if not self.headers:
            return
        payload = {
            "message": "简要介绍一下Python语言的特点",
            "session_id": None,
            "conversation_id": None,
        }
        # Locust 对 SSE 支持有限，这里用普通 POST 测服务端响应
        # 如果要测完整 SSE 流，需要自定义 client
        with self.client.post(
            "/ai/chat",
            json=payload,
            headers=self.headers,
            catch_response=True,
            timeout=60,
        ) as resp:
            # SSE 接口返回 200 后持续推送，Locust 默认会等待完整响应
            # 如果流很长可能超时，这里仅验证能正确响应
            if resp.status_code == 200:
                resp.success()
            elif resp.status_code == 401:
                resp.failure("Unauthorized - Token expired")
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(2)
    def get_user_profile(self):
        """测试用户资料接口"""
        if not self.headers:
            return
        with self.client.get("/user/profile", headers=self.headers, catch_response=True) as resp:
            if resp.status_code == 200:
                resp.success()
            elif resp.status_code == 401:
                resp.failure("Unauthorized")
            else:
                resp.failure(f"HTTP {resp.status_code}")


# ============ 事件监听（可选） ============

@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    print(f"🚀 压测开始 | 目标: {environment.host}")
    if not TEST_TOKEN:
        print("⚠️  未设置 TEST_TOKEN，认证接口任务将被跳过")
        print("   设置方式: export TEST_TOKEN='your_jwt_token'")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    print("✅ 压测结束")
    stats = environment.runner.stats
    print(f"   总请求: {stats.total.num_requests}")
    print(f"   失败数: {stats.total.num_failures}")
    if stats.total.num_requests > 0:
        print(f"   平均 RPS: {stats.total.total_rps:.2f}")
        print(f"   平均延迟: {stats.total.avg_response_time:.1f}ms")
