from enum import Enum
from typing import Final


class UserRole(str, Enum):
    """用户角色（RBAC）：值与 DB users.role 字符串一致，便于直接比较。"""
    ADMIN = "admin"
    TEACHER = "teacher"
    STUDENT = "student"


# 调用智能体 / 外部插件时透传调用者身份的 HTTP 头规范
# 仅含 ASCII 安全字段；姓名等可读标识不入头（头值须 Latin-1，中文会编码失败）
ACTOR_HEADER_ID: Final[str] = "X-Actor-Id"
ACTOR_HEADER_ROLE: Final[str] = "X-Actor-Role"
ACTOR_HEADER_ZJU_ID: Final[str] = "X-Actor-Zju-Id"


# 时区
TIMEZONE_SHANGHAI: Final[str] = "Asia/Shanghai"

# HTTP 超时（秒）
DEFAULT_HTTP_TIMEOUT: Final[float] = 60.0
COZE_UPLOAD_TIMEOUT: Final[float] = 120.0
VIDEO_DOWNLOAD_TIMEOUT: Final[float] = 600.0
PANDOC_TIMEOUT: Final[int] = 30

# 流式分片大小（字节）
VIDEO_DOWNLOAD_CHUNK_SIZE: Final[int] = 1024 * 1024 * 10  # 10MB
DEFAULT_HTTP_CHUNK_SIZE: Final[int] = 1024 * 256  # 256KB

# 上传限制
VIDEO_MAX_CHUNKS: Final[int] = 10000

# 智能对话：上传附件解析后注入对话上下文的长度上限（字符数，按需调整）
# 单个附件超出按上限截断；多附件累计超出总上限后停止追加。防止超长文档撑爆模型上下文。
CHAT_ATTACHMENT_MAX_CHARS_PER_FILE: Final[int] = 20000
CHAT_ATTACHMENT_MAX_CHARS_TOTAL: Final[int] = 40000

# 文件大小换算
BYTES_PER_MB: Final[int] = 1024 * 1024
BYTES_PER_GB: Final[int] = 1024 * 1024 * 1024

# 随机数范围
NONCE_MAX: Final[int] = 999999

# 第三方 API URL
COZE_API_BASE: Final[str] = "https://api.coze.cn"

ZJU_OAUTH_AUTHORIZE_URL: Final[str] = "https://zjuam.zju.edu.cn/cas/oauth2.0/authorize"
ZJU_OAUTH_ACCESS_TOKEN_URL: Final[str] = "https://zjuam.zju.edu.cn/cas/oauth2.0/accessToken"
ZJU_OAUTH_PROFILE_URL: Final[str] = "https://zjuam.zju.edu.cn/cas/oauth2.0/profile"

CHAOXING_TRANSCRIPT_URL: Final[str] = "http://ocr-zelda.chaoxing.com/deepspeech-zelda/api/transcript"
CHAOXING_ANALYZE_URL: Final[str] = "http://ocr-zelda.chaoxing.com/deepspeech-zelda/api/get-open-ai-analyze"
CHAOXING_UPLOAD_URL: Final[str] = "https://pan-yz.chaoxing.com/upload/v2"

ZHIYUN_REQTOKEN_URL: Final[str] = "https://api.zju.edu.cn/api/reqtoken"
ZHIYUN_COURSE_DETAIL_URL: Final[str] = "https://api.zju.edu.cn/api/zyktcosinfo/online"
ZHIYUN_COURSE_LIST_URL: Final[str] = "https://api.zju.edu.cn/api/zyktcoslist/online"
