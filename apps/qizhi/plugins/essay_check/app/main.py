import logging

from fastapi import FastAPI

from app.api.router import router
from app.logger import _console_formatter
from app.scheduler import lifespan

app = FastAPI(
    title="浙江大学本科毕业论文检查系统",
    description="接收毕业论文PDF，逐页检查规范性，生成审查报告",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router)

# 压制 noisy 日志源
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)

# 根 logger：console + SLS
root = logging.getLogger()
if not root.handlers:
    root.setLevel(logging.INFO)
    console = logging.StreamHandler()
    console.setFormatter(_console_formatter)
    root.addHandler(console)

    from app.logger import _get_sls_handler
    sls = _get_sls_handler()
    if sls:
        root.addHandler(sls)


@app.get("/health")
async def health():
    return {"status": "ok"}
