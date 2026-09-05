import contextvars
import logging
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

from aliyun.log.logitem import LogItem
from aliyun.log.putlogsrequest import PutLogsRequest
from aliyun.log.logclient import LogClient

from common.config import settings

# 公共线程池，用于异步发送日志
_log_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="sls-log-")

# 请求上下文：在 middleware 中设置，logger 中自动读取
_request_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)

# 全局共享 SLS handler，每个 logstore 仅一个实例
_app_sls: "SLSLogHandler | None" = None
_access_sls: "SLSLogHandler | None" = None
_sls_lock = threading.Lock()
_sls_pid: int = 0


def _sls_ready() -> bool:
    return bool(settings.SLS_ENDPOINT and settings.SLS_PROJECT
                and settings.ALIBABA_CLOUD_ACCESS_KEY_ID)


def _get_app_sls_handler() -> SLSLogHandler | None:
    """获取全局唯一的 app-log SLS handler。"""
    global _app_sls, _sls_pid
    current_pid = os.getpid()

    with _sls_lock:
        if _sls_pid != current_pid:
            _app_sls = None
            _sls_pid = current_pid

        if _app_sls is not None:
            return _app_sls

        if _sls_ready():
            _app_sls = SLSLogHandler(
                endpoint=settings.SLS_ENDPOINT,
                access_key_id=settings.ALIBABA_CLOUD_ACCESS_KEY_ID,
                access_key_secret=settings.ALIBABA_CLOUD_ACCESS_KEY_SECRET,
                project=settings.SLS_PROJECT,
                logstore=settings.SLS_APP_LOGSTORE,
            )
        return _app_sls


def _get_access_sls_handler() -> SLSLogHandler | None:
    """获取全局唯一的 access-log SLS handler。"""
    global _access_sls, _sls_pid
    current_pid = os.getpid()

    with _sls_lock:
        if _sls_pid != current_pid:
            _access_sls = None
            _sls_pid = current_pid

        if _access_sls is not None:
            return _access_sls

        if _sls_ready():
            _access_sls = SLSLogHandler(
                endpoint=settings.SLS_ENDPOINT,
                access_key_id=settings.ALIBABA_CLOUD_ACCESS_KEY_ID,
                access_key_secret=settings.ALIBABA_CLOUD_ACCESS_KEY_SECRET,
                project=settings.SLS_PROJECT,
                logstore=settings.SLS_ACCESS_LOGSTORE,
            )
        return _access_sls


_SUPPRESSED_LOGGERS = {
    "sqlalchemy.engine",
    "sqlalchemy.engine.Engine",
    "sqlalchemy.pool",
    "asyncpg",
}

_console_formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s [%(request_id)s] - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def get_logger(name: str) -> logging.Logger:
    """获取应用 logger。

    from common.utils.logger import get_logger
    logger = get_logger(__name__)
    """
    logger = logging.getLogger(name)
    # 不加 handler，让日志传播到 root（root 有 console + SLS）
    logger.setLevel(logging.INFO)
    logger.propagate = True
    return logger


def get_access_logger() -> logging.Logger:
    """获取 API 访问日志 logger，SLS 写入 access-log。"""
    logger = logging.getLogger("access")
    if not logger.handlers:
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(_console_formatter)
        console.addFilter(_RequestIdFilter())
        logger.addHandler(console)

        sls = _get_access_sls_handler()
        if sls:
            logger.addHandler(sls)

        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def set_request_id(value: str | None, token=None):
    """设置当前协程的 request_id。"""
    return _request_id_ctx.set(value)


def log_access(
    method: str,
    path: str,
    query_params: str,
    request_body: str,
    status_code: int,
    response_body: str,
    elapsed_ms: float,
    client_ip: str,
    request_id: str,
):
    """写入结构化 API 访问日志。"""
    logger = get_access_logger()
    msg = f"API {method} {path} {status_code} {elapsed_ms}ms ip={client_ip} request_id={request_id}"

    record = logger.makeRecord(
        logger.name, logging.INFO, "", 0, msg, (), None,
    )
    record._access_fields = {
        "method": method,
        "path": path,
        "query_params": query_params,
        "request_body": request_body,
        "status_code": str(status_code),
        "response_body": response_body,
        "elapsed_ms": str(elapsed_ms),
        "client_ip": client_ip,
        "request_id": request_id,
    }
    logger.handle(record)


def init_root_logger():
    """初始化根 logger，供 main.py 启动时调用。"""
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # 检查是否已有 SLS handler
    has_sls = any(isinstance(h, SLSLogHandler) for h in root.handlers)
    if has_sls:
        return

    level_filter = _LevelFilter()

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(_console_formatter)
    console.addFilter(_RequestIdFilter())
    console.addFilter(level_filter)
    root.addHandler(console)

    sls = _get_app_sls_handler()
    if sls:
        sls.addFilter(level_filter)
        root.addHandler(sls)

    # 压制数据库引擎和驱动的详细日志
    for _logger_name in ("sqlalchemy.engine", "sqlalchemy.engine.Engine", "sqlalchemy.pool", "asyncpg"):
        logging.getLogger(_logger_name).setLevel(logging.WARNING)


class SLSLogHandler(logging.Handler):
    """阿里云 SLS 日志 Handler，同步攒批发送。

    每条日志立即发送到 SLS，简单可靠。
    """

    def __init__(self, endpoint: str, access_key_id: str, access_key_secret: str,
                 project: str, logstore: str):
        super().__init__()
        self._sls_handler = True
        self.client = LogClient(endpoint, access_key_id, access_key_secret)
        self.project = project
        self.logstore = logstore
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord):
        log_item = LogItem()
        log_item.set_time(int(record.created))

        access_fields = getattr(record, "_access_fields", None)
        request_id = _request_id_ctx.get()
        if access_fields:
            contents = [("env", settings.ENV_TAG)] + [
                (k, v) for k, v in access_fields.items()
            ]
        else:
            contents = [
                ("env", settings.ENV_TAG),
                ("level", record.levelname),
                ("logger", record.name),
                ("message", self.format(record)),
                ("module", record.module),
                ("function", record.funcName),
                ("line", str(record.lineno)),
            ]
            if request_id:
                contents.append(("request_id", request_id))
        if record.exc_text:
            contents.append(("exception", record.exc_text[:2000]))
        log_item.set_contents(contents)

        # 异步发送日志到 SLS
        _log_executor.submit(self._send_log, log_item)

    def _send_log(self, log_item: LogItem):
        """线程池中执行的日志发送方法。"""
        try:
            req = PutLogsRequest(
                self.project, self.logstore,
                topic="", source="",
                logitems=[log_item],
            )
            self.client.put_logs(req)
        except Exception:
            pass


class _RequestIdFilter(logging.Filter):
    """在 log record 上注入 request_id，供 console formatter 使用。"""

    def filter(self, record):
        record.request_id = _request_id_ctx.get() or "-"
        return True


class _LevelFilter(logging.Filter):
    """过滤掉已知 noisy 日志源的 INFO 级别日志。"""

    def filter(self, record: logging.LogRecord):
        if record.levelno < logging.WARNING and record.name in _SUPPRESSED_LOGGERS:
            return False
        return True
