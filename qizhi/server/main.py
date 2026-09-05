import asyncio
import uvicorn
from contextlib import asynccontextmanager
from pathlib import Path
from common.middleware.cors import CORSMiddleware
from common.middleware.access_log import AccessLogMiddleware
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

# 必须在其他模块导入前初始化日志，确保子模块 get_logger() 能拿到 SLS handler
from common.utils.logger import get_logger, init_root_logger
init_root_logger()

from api import api_router
from common.config import settings
from common.models import ApiResponse, BizException, SystemException, AuthException
from infra.db import init_db

logger = get_logger(__name__)

# 应用生命周期
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("EDU AI HOME应用启动")

    # 初始化数据库
    logger.info("初始化数据库")
    init_db()
    logger.info("数据库初始化完成")

    # 启动任务队列 worker（支持多 Handler 按不同周期独立轮询）
    from infra.task_queue.worker import start_task_worker
    from service.video.analysis_task import LocalVideoAnalysisHandler, VideoAnalysisHandler

    worker_task = asyncio.create_task(
        start_task_worker([
            (VideoAnalysisHandler(), 600),  # 超星视频分析：每 10 分钟（云端串行即可）
            (
                LocalVideoAnalysisHandler(),
                settings.LOCAL_ANALYSIS_POLL_INTERVAL,  # 本地分析：默认 15s
                settings.LOCAL_ANALYSIS_MAX_CONCURRENCY,  # 并发任务数：默认 1，GPU 多卡后上调
            ),
        ])
    )

    yield

    worker_task.cancel()
    logger.info("EDU AI HOME应用关闭")

# 创建应用
app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

# 配置 CORS（跨域资源共享）
# 生产环境应限制具体域名，当前 allow_credentials=False 降低了部分风险
app.add_middleware(CORSMiddleware)

# API 访问日志中间件（原始 ASGI，不阻塞流式响应）
app.add_middleware(AccessLogMiddleware)

# 注册路由
app.include_router(api_router)


@app.get("/api/version")
async def version():
    return {"version": "2026-06-23-streaming-pipeline", "status": "ok"}

# 暴露静态文件
uploads_dir = Path(settings.UPLOAD_DIR)
uploads_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=uploads_dir), name="static")


# 注册异常处理器
# 业务异常
@app.exception_handler(BizException)
async def biz_exception_handler(request: Request, exc: BizException) -> JSONResponse:
    return JSONResponse(
        status_code=200,
        content=ApiResponse.error_response(exc.error).model_dump(),
    )

# 系统异常
@app.exception_handler(SystemException)
async def system_exception_handler(request: Request, exc: SystemException) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content=ApiResponse.error_response(exc.error).model_dump(),
    )

# 认证异常
@app.exception_handler(AuthException)
async def auth_exception_handler(request: Request, exc: AuthException) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content=ApiResponse.error_response(exc.error).model_dump(),
    )

# 未知异常
@app.exception_handler(Exception)
async def exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content=ApiResponse.error_response(str(exc)).model_dump(),
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="EDU AI HOME Server")
    parser.add_argument("--host", default="0.0.0.0", help="绑定地址 (默认: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="监听端口 (默认: 8000)")
    parser.add_argument("--workers", type=int, default=4, help="工作进程数 (默认: 4)")
    args = parser.parse_args()

    if args.workers > 1:
        logger.info(f"🚀 多进程模式启动: {args.workers} workers")
    else:
        logger.info("🚀 单进程模式启动")

    uvicorn.run(
        "main:app",
        host=args.host,
        port=args.port,
        workers=args.workers,
    )
