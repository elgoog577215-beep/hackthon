import logging
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

from aliyun.log.logitem import LogItem
from aliyun.log.putlogsrequest import PutLogsRequest
from aliyun.log.logclient import LogClient

from app.config import SLS_ENDPOINT, SLS_PROJECT, SLS_APP_LOGSTORE, \
    ALIBABA_CLOUD_ACCESS_KEY_ID, ALIBABA_CLOUD_ACCESS_KEY_SECRET

SERVICE_TAG = "essay-check"

# 公共线程池，用于异步发送日志
_log_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="sls-log-")

# 全局共享 SLS handler
_sls: "SLSLogHandler | None" = None
_sls_lock = threading.Lock()
_sls_pid: int = 0


class SLSLogHandler(logging.Handler):
    """阿里云 SLS 日志 Handler。"""

    def __init__(self, endpoint: str, access_key_id: str, access_key_secret: str,
                 project: str, logstore: str):
        super().__init__()
        self.client = LogClient(endpoint, access_key_id, access_key_secret)
        self.project = project
        self.logstore = logstore

    def emit(self, record: logging.LogRecord):
        log_item = LogItem()
        log_item.set_time(int(record.created))

        contents = [
            ("service", SERVICE_TAG),
            ("level", record.levelname),
            ("logger", record.name),
            ("message", self.format(record)),
            ("module", record.module),
            ("function", record.funcName),
            ("line", str(record.lineno)),
        ]
        if record.exc_text:
            contents.append(("exception", record.exc_text[:2000]))
        log_item.set_contents(contents)

        _log_executor.submit(self._send_log, log_item)

    def _send_log(self, log_item: LogItem):
        try:
            req = PutLogsRequest(
                self.project, self.logstore,
                topic="", source="",
                logitems=[log_item],
            )
            self.client.put_logs(req)
        except Exception:
            pass


def _sls_ready() -> bool:
    return bool(SLS_ENDPOINT and SLS_PROJECT and ALIBABA_CLOUD_ACCESS_KEY_ID)


def _get_sls_handler() -> SLSLogHandler | None:
    global _sls, _sls_pid
    current_pid = os.getpid()

    with _sls_lock:
        if _sls_pid != current_pid:
            _sls = None
            _sls_pid = current_pid

        if _sls is not None:
            return _sls

        if _sls_ready():
            _sls = SLSLogHandler(
                endpoint=SLS_ENDPOINT,
                access_key_id=ALIBABA_CLOUD_ACCESS_KEY_ID,
                access_key_secret=ALIBABA_CLOUD_ACCESS_KEY_SECRET,
                project=SLS_PROJECT,
                logstore=SLS_APP_LOGSTORE,
            )
        return _sls


_console_formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def get_logger(name: str) -> logging.Logger:
    """获取应用 logger，同时输出到 console 和 SLS。

    from app.logger import get_logger
    logger = get_logger(__name__)
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(_console_formatter)
        logger.addHandler(console)

        sls = _get_sls_handler()
        if sls:
            logger.addHandler(sls)

        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger
