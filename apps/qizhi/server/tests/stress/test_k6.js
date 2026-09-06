/**
 * k6 压测脚本（高性能，适合极限压测）
 *
 * 安装 k6:
 *   macOS: brew install k6
 *   其他: https://k6.io/docs/get-started/installation/
 *
 * 运行:
 *   export TEST_TOKEN="your_jwt_token"
 *   k6 run --vus 50 --duration 60s tests/stress/test_k6.js
 *
 * 进阶用法（阶梯加压）:
 *   k6 run tests/stress/test_k6.js
 *   （脚本内已配置 stages，会自动按阶梯加压）
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

// 自定义指标
const healthLatency = new Trend('health_latency');
const failRate = new Rate('failed_requests');

export const options = {
  // 阶梯加压场景
  stages: [
    { duration: '10s', target: 10 },   // 10秒 ramp-up 到 10 VU
    { duration: '30s', target: 50 },   // 30秒 ramp-up 到 50 VU
    { duration: '60s', target: 50 },   // 50 VU 持续 60 秒
    { duration: '10s', target: 0 },    // 10秒 ramp-down
  ],
  thresholds: {
    http_req_duration: ['p(95)<2000'],  // 95% 请求延迟 < 2s
    http_req_failed: ['rate<0.1'],      // 错误率 < 10%
    failed_requests: ['rate<0.1'],
  },
};

const BASE_URL = 'http://127.0.0.1:8000';
const TOKEN = __ENV.TEST_TOKEN || '';

export default function () {
  // =====================
  // 1. 无认证接口：健康检查
  // =====================
  const healthRes = http.get(`${BASE_URL}/health`);
  healthLatency.add(healthRes.timings.duration);

  const healthOk = check(healthRes, {
    'health status is 200': (r) => r.status === 200,
    'health response ok': (r) => r.json('status') === 'ok',
  });
  failRate.add(!healthOk);

  sleep(0.5);

  // =====================
  // 2. 认证接口（如果有 Token）
  // =====================
  if (TOKEN) {
    const params = {
      headers: {
        Authorization: `Bearer ${TOKEN}`,
        'Content-Type': 'application/json',
      },
    };

    // 测试用户资料接口
    const profileRes = http.get(`${BASE_URL}/user/profile`, params);
    const profileOk = check(profileRes, {
      'profile status is 200': (r) => r.status === 200,
    });
    failRate.add(!profileOk);

    sleep(1);

    // 测试 AI 聊天接口（非流式，只测服务端接受请求的速度）
    // 注意：SSE 流在 k6 中会等待完整响应，如果流很长会超时
    // 如果需要测试 SSE，建议单独配置 timeout 或只测首字节
    /*
    const chatPayload = JSON.stringify({
      message: '简要介绍一下Python语言的特点',
      session_id: null,
      conversation_id: null,
    });
    const chatRes = http.post(`${BASE_URL}/ai/chat`, chatPayload, params);
    const chatOk = check(chatRes, {
      'chat status is 200': (r) => r.status === 200,
    });
    failRate.add(!chatOk);
    */
  }

  sleep(1);
}
