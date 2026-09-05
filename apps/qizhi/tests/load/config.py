"""
Locust load test configuration for MentorAI (启智).

All tunables in one place: target host, auth headers, and sample test data.
"""

import os

# ---------------------------------------------------------------------------
# Target
# ---------------------------------------------------------------------------
# The FastAPI backend is accessed directly (no Vite proxy), so routes have
# NO /api prefix.  Example: /ai/chat, /video/analyze, /course/list
TARGET_HOST = "http://127.0.0.1:8000"

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
# The platform uses ZJU OAuth -> JWT.  For load testing we reuse a long-lived
# test token obtained from the /auth/test-login endpoint (DEV env only).
# Replace with a fresh token before each test run.
TEST_TOKEN = (
    os.getenv("QIZHI_TEST_TOKEN", "")
)

def auth_headers(extra: dict | None = None) -> dict:
    """Return common headers including JWT auth and optional extras."""
    headers = {
        "Authorization": f"Bearer {TEST_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    if extra:
        headers.update(extra)
    return headers

# ---------------------------------------------------------------------------
# Test data — Chat
# ---------------------------------------------------------------------------
CHAT_MESSAGES = [
    "你好，请介绍一下教学设计的基本原则。",
    "什么是布鲁姆教学目标分类？",
    "如何提高课堂互动效果？",
    "请帮我设计一个Python编程课的教学活动。",
    "翻转课堂和传统课堂有什么区别？",
    "OBE教学理念的核心是什么？",
    "如何在课堂中融入思政元素？",
    "请简述混合式教学的优势。",
    "怎样设计有效的课堂提问？",
    "请帮我分析一下教学评价的类型。",
]

# ---------------------------------------------------------------------------
# Test data — Outline generation
# ---------------------------------------------------------------------------
OUTLINE_FORM = {
    "course_name": "Python程序设计",
    "course_nature": "专业必修课",
    "course_category": "工学",
    "credits": 3,
    "hours": 48,
    "target_major": "计算机科学与技术",
    "target_grade": "大二",
    "teaching_method": "讲授+实验",
    "offline_hours_ratio": 70,
    "offline_score_ratio": 60,
    "prerequisites": "高等数学、线性代数",
    "course_introduction": "本课程系统讲授Python编程语言基础，涵盖数据类型、控制结构、函数、面向对象编程等。",
    "teaching_objectives": "掌握Python基础编程，能独立完成中等复杂度程序设计。",
    "ideological_political": "培养科学严谨的计算思维和工程伦理意识。",
}

# ---------------------------------------------------------------------------
# Test data — Teaching plan generation
# ---------------------------------------------------------------------------
TEACHING_PLAN_FORM = {
    "chapter_name": "第一章 Python基础与开发环境",
    "supplementary_description": "介绍Python语言特点、安装配置、基本数据类型和运算符。",
    "class_hours": 4,
}

# ---------------------------------------------------------------------------
# Test data — IDs for read-heavy browsing simulation
# These are placeholder IDs; replace with real ones from the database
# or use list endpoints to discover them at runtime.
# ---------------------------------------------------------------------------
SAMPLE_COURSE_IDS = [
    "test-course-001",
    "test-course-002",
]

SAMPLE_VIDEO_IDS = [
    "test-video-001",
    "test-video-002",
]

SAMPLE_RESOURCE_IDS = [
    "test-resource-001",
    "test-resource-002",
]

# ---------------------------------------------------------------------------
# Performance SLOs (documented in test output, not enforced by Locust)
# ---------------------------------------------------------------------------
SLO = {
    "p99_latency_ms": 3000,        # Non-streaming endpoints
    "sse_first_token_ms": 2000,    # SSE streaming first token
    "error_rate_pct": 1.0,         # Maximum acceptable error rate
    "target_users": 400,           # Sustained concurrent users
    "run_time_minutes": 10,        # Sustained duration
}
