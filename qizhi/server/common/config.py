import os
from dotenv import load_dotenv
from sqlalchemy.engine import URL
from pydantic import BaseModel, computed_field

load_dotenv()


class Settings(BaseModel):
    # 应用
    APP_NAME: str = "Edu AI Home"
    APP_KEY: str = os.getenv("APP_KEY", "")
    APP_SECRET: str = os.getenv("APP_SECRET", "")
    APP_URL: str = "http://jsfzai.zju.edu.cn"

    # JWT 配置
    SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "")
    ACCESS_TOKEN_EXPIRE_SECONDS: int = 60 * 60 * 24 * 3  # 3 days

    # 数据库连接
    DATABASE_PASSWORD: str = os.getenv("DATABASE_PASSWORD", "")

    @computed_field
    @property
    def SYNC_DATABASE_URL(self) -> str:
        return os.getenv("SYNC_DATABASE_URL") or self._database_url("postgresql+psycopg")

    @computed_field
    @property
    def ASYNC_DATABASE_URL(self) -> str:
        return os.getenv("ASYNC_DATABASE_URL") or self._database_url("postgresql+asyncpg")

    def _database_url(self, driver: str) -> str:
        return URL.create(
            driver,
            username=self._db_user(),
            password=self.DATABASE_PASSWORD,
            host=self._db_host(),
            port=int(self._db_port()),
            database=self._db_name(),
        ).render_as_string(hide_password=False)

    @staticmethod
    def _db_host() -> str:
        return os.getenv("DATABASE_HOST", "127.0.0.1")

    @staticmethod
    def _db_port() -> str:
        return os.getenv("DATABASE_PORT", "5432")

    @staticmethod
    def _db_user() -> str:
        return os.getenv("DATABASE_USER", "postgres")

    @staticmethod
    def _db_name() -> str:
        return os.getenv("DATABASE_NAME", "edu_ai_home")

    # 数据库连接池配置（按 4 worker 设计，总连接需求 <= 4*(12+5)=68，低于 RDS 默认 max_connections=100）
    POOL_SIZE: int = 12
    MAX_OVERFLOW: int = 5
    POOL_RECYCLE: int = 3600

    # 上传文件配置
    UPLOAD_DIR: str = "uploads"
    UPLOAD_MAX_SIZE: int = 1024 * 1024 * 100  # 100MB
    VIDEO_MAX_SIZE: int = 1024 * 1024 * 1024 * 5  # 5GB

    # 百炼 API 配置
    DASHSCOPE_API_KEY: str = os.getenv("DASHSCOPE_API_KEY", "")

    # Alibaba Cloud 配置
    ALIBABA_CLOUD_ACCESS_KEY_ID: str = os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID", "")
    ALIBABA_CLOUD_ACCESS_KEY_SECRET: str = os.getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET", "")

    # SLS 日志服务配置
    SLS_ENDPOINT: str = os.getenv("SLS_ENDPOINT", "cn-hangzhou.log.aliyuncs.com")
    SLS_PROJECT: str = "mentor-ai"
    SLS_APP_LOGSTORE: str = "app-log"
    SLS_ACCESS_LOGSTORE: str = "access-log"

    @computed_field
    @property
    def ENV_TAG(self) -> str:
        env = os.getenv("ENV", "")
        if env in ("LOCAL", "DEV"):
            return "dev"
        return "prod"

    # RAG 配置
    KNOWLEDGEBASE_ID: str = os.getenv("KNOWLEDGEBASE_ID", "")
    WORKSPACE_ID: str = os.getenv("WORKSPACE_ID", "")

    # Coze 配置
    COZE_BOT_ID: str = os.getenv("COZE_BOT_ID", "")
    COZE_API_KEY: str = os.getenv("COZE_API_KEY", "")

    # 超星配置
    CHAOXING_APP_ID: str = os.getenv("CHAOXING_APP_ID", "")
    CHAOXING_APP_SECRET: str = os.getenv("CHAOXING_APP_SECRET", "")
    CHAOXING_ENC_KEY: str = os.getenv("CHAOXING_ENC_KEY", "")
    CHAOXING_PUID: str = os.getenv("CHAOXING_PUID", "")
    CHAOXING_FID: str = os.getenv("CHAOXING_FID", "")
    CHAOXING_CLIENT_IP: str = os.getenv("CHAOXING_CLIENT_IP", "127.0.0.1")

    # 智云课堂配置
    ZHIYUN_APP_ID: str = os.getenv("ZHIYUN_APP_ID", "")
    ZHIYUN_SECRET: str = os.getenv("ZHIYUN_SECRET", "")
    ZHIYUN_APP_KEY: str = os.getenv("ZHIYUN_APP_KEY", "")
    ZHIYUN_TOKEN: str = os.getenv("ZHIYUN_TOKEN", "")

    # 本地视频分析配置（自建 vLLM，OpenAI 兼容；不依赖超星）
    # 支持逗号分隔的多 URL 实现多实例负载均衡，如：
    # VLLM_TEXT_ENDPOINT="http://host:30938/v1,http://host:30939/v1,http://host:30940/v1"
    LOCAL_ANALYSIS_TEXT_BASE_URL: str = os.getenv("VLLM_TEXT_ENDPOINT", "http://127.0.0.1:30938/v1")
    LOCAL_ANALYSIS_ASR_BASE_URL: str = os.getenv("VLLM_ASR_ENDPOINT", "http://127.0.0.1:30026/v1")
    LOCAL_ANALYSIS_MODEL: str = os.getenv("LOCAL_ANALYSIS_MODEL", "qwen3.6-35b-a3b")
    LOCAL_ANALYSIS_ASR_MODEL: str = os.getenv("LOCAL_ANALYSIS_ASR_MODEL", "qwen3-asr-1.7b")
    LOCAL_ANALYSIS_API_KEY: str = os.getenv("LOCAL_ANALYSIS_API_KEY") or os.getenv("VLLM_API_KEY") or ""
    # 仅分析视频前 N 秒（0 表示整段）；联调短片段时设为 120。从 0 开始保证各维度时间轴一致。
    LOCAL_ANALYSIS_MAX_SECONDS: int = int(os.getenv("LOCAL_ANALYSIS_MAX_SECONDS", "0") or "0")
    # 本地分析任务轮询间隔（秒）；本地无超星 1 小时等待，设短一些让结果更快出现。
    LOCAL_ANALYSIS_POLL_INTERVAL: int = int(os.getenv("LOCAL_ANALYSIS_POLL_INTERVAL", "2") or "2")
    # 本地分析最大并发任务数：>1 时允许多个视频同时分析（不再单队列排队）。
    # 受 GPU/vLLM 吞吐约束（别超过 --max-num-seqs 能承载的并发）。默认 1=保持原串行行为，
    # GPU 多卡合并后按可用槽位上调（如 2~4）。每个并发任务用独立 DB 会话，互不干扰。
    LOCAL_ANALYSIS_MAX_CONCURRENCY: int = int(os.getenv("LOCAL_ANALYSIS_MAX_CONCURRENCY", "2") or "2")

    # 论文审查微服务配置
    ESSAY_CHECK_SERVICE_URL: str = os.getenv("ESSAY_CHECK_SERVICE_URL", "http://127.0.0.1:8001")

    # 运营后台管理员白名单（逗号分隔的 ZJU 学工号）
    ADMIN_ZJU_IDS_RAW: str = os.getenv("ADMIN_ZJU_IDS", "")

    @computed_field
    @property
    def ADMIN_ZJU_IDS(self) -> set[str]:
        return {s.strip() for s in self.ADMIN_ZJU_IDS_RAW.split(",") if s.strip()}

    # 审计日志 service-token：外置 agent 通过 X-Audit-Service-Token 上报时使用。
    # 未配置（空串）时 /audit/report 端点关闭；admin JWT 上报路径不受影响。
    AUDIT_SERVICE_TOKEN: str = os.getenv("AUDIT_SERVICE_TOKEN", "")


settings = Settings()
