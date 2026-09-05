import os
from dotenv import load_dotenv

load_dotenv()


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required essay service configuration: {name}")
    return value

# 环境标识: "dev" 或 "prod"，可通过环境变量 ENV 覆盖
ENV = os.getenv("ENV", "prod")

# 本地图片存储目录（仅 PROD 环境使用）
LOCAL_IMAGE_DIR = os.getenv("LOCAL_IMAGE_DIR", "/data/essay_images")

DATABASE_PASSWORD = os.getenv("DATABASE_PASSWORD", "")

DATABASE_URL = _required_env("DATABASE_URL")

# 阿里云 OSS
OSS_ACCESS_KEY_ID = os.getenv("OSS_ACCESS_KEY_ID", "")
OSS_ACCESS_KEY_SECRET = os.getenv("OSS_ACCESS_KEY_SECRET", "")
OSS_BUCKET_NAME = "edu-ai-essay-check"
OSS_ENDPOINT = "https://oss-cn-hangzhou.aliyuncs.com"
OSS_URL_PREFIX = ""

# DashScope (Qwen-VL)
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
LLM_MODEL = "qwen3.6-plus"
LLM_MODEL_SUMMARY = "qwen3.6-plus"

# SLS 日志服务配置
SLS_ENDPOINT = "cn-hangzhou.log.aliyuncs.com"
SLS_PROJECT = "mentor-ai"
SLS_APP_LOGSTORE = "app-log"
ALIBABA_CLOUD_ACCESS_KEY_ID = os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID", "")
ALIBABA_CLOUD_ACCESS_KEY_SECRET = os.getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET", "")

# 服务配置
MAX_CONCURRENT_PAGES = os.getenv("MAX_CONCURRENT_PAGES", 60)

SCAN_INTERVAL_SECONDS = 3
MAX_PDF_PAGES = 200

# 汇总报告：页数 <= SINGLE 时一次 LLM；否则按 BATCH 页分批汇总再二次合并
SUMMARY_SINGLE_PASS_MAX_PAGES = int(os.getenv("SUMMARY_SINGLE_PASS_MAX_PAGES", "100"))
SUMMARY_BATCH_PAGE_SIZE = int(os.getenv("SUMMARY_BATCH_PAGE_SIZE", "100"))
# summarizing 状态最长等待时间（分钟），长论文分批汇总需更久
SUMMARY_TIMEOUT_MINUTES = int(os.getenv("SUMMARY_TIMEOUT_MINUTES", "20"))

SERVER_HOST = "0.0.0.0"
SERVER_PORT = 8000

# 本地图片签名密钥（PROD 环境图片 URL 签名用）
IMAGE_SIGN_SECRET = _required_env("IMAGE_SIGN_SECRET")

# 图片 URL 前缀（用于拼接 image_url，末尾不要带 /）
IMAGE_BASE_URL = os.getenv("IMAGE_BASE_URL", "http://jsfzai.zju.edu.cn/essay")

# vLLM 配置（PROD 环境使用）
VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://127.0.0.1:30938/v1")
VLLM_API_KEY = os.getenv("VLLM_API_KEY", "")
VLLM_MODEL = os.getenv("VLLM_MODEL", "qwen3.6-35b-a3b")
