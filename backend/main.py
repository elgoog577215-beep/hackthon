# =============================================================================
# 主应用程序入口点
# 初始化 FastAPI 应用，配置中间件，注册路由模块，管理 WebSocket 连接。
# =============================================================================

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from typing import List
import sys
import os
import logging

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 添加当前目录到 sys.path 以确保本地导入工作正常
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from storage import storage
    from ai_service import ai_service
    from task_manager import TaskManager
    from websocket_service import WebSocketService
    from dependencies import init_task_manager, init_ws_service
except ImportError:
    try:
        from backend.storage import storage
        from backend.ai_service import ai_service
        from backend.task_manager import TaskManager
        from backend.websocket_service import WebSocketService
        from backend.dependencies import init_task_manager, init_ws_service
    except ImportError as e:
        logger.error(f"Failed to import required modules: {e}")
        raise

# 导入路由模块
from routers import (
    courses, nodes, annotations, quiz,
    knowledge_graph, learning, review,
    tutor, code_execution, diagrams, tasks,
    markdown_import
)

# Check if profile router exists
try:
    from routers import profile as profile_router
    HAS_PROFILE = True
except ImportError:
    HAS_PROFILE = False


# Create WebSocket service
ws_service = WebSocketService()

# Create TaskManager with dependency injection
try:
    task_manager = TaskManager(
        storage=storage,
        course_service=ai_service,
        ws_service=ws_service,
        max_concurrency=5,
    )
    ws_service.set_command_handler(task_manager.handle_command)
    init_task_manager(task_manager)
    init_ws_service(ws_service)
except NameError:
    task_manager = None


# ============================================================================
# Application Lifespan (replaces @app.on_event startup/shutdown)
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    if task_manager:
        await task_manager.start()
    yield
    # Shutdown
    if task_manager:
        await task_manager.shutdown(timeout=30.0)


app = FastAPI(lifespan=lifespan)


# ============================================================================
# Middleware Configuration
# ============================================================================

from rate_limiter import RateLimitMiddleware

app.add_middleware(RateLimitMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1000)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:8000",
        "http://localhost:4000",
        "http://localhost:3000",
        "http://localhost:8080",
        "http://localhost:8081",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
        "http://127.0.0.1:4000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8080",
        "http://127.0.0.1:8081",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
)


# ============================================================================
# Health Check Endpoints
# ============================================================================

from datetime import datetime

@app.get("/health")
async def health_check():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

@app.get("/api/health")
def read_root():
    return {"message": "KnowledgeMap AI API"}


# ============================================================================
# Register Routers
# ============================================================================

app.include_router(courses.router, prefix="/api")
app.include_router(nodes.router, prefix="/api")
app.include_router(annotations.router, prefix="/api")
app.include_router(quiz.router, prefix="/api")
app.include_router(knowledge_graph.router, prefix="/api")
app.include_router(learning.router, prefix="/api")
app.include_router(review.router, prefix="/api")
app.include_router(tutor.router)
app.include_router(code_execution.router)
app.include_router(diagrams.router)
app.include_router(tasks.router, prefix="/api")
app.include_router(markdown_import.router)
if HAS_PROFILE:
    app.include_router(profile_router.router, prefix="/api")


# ============================================================================
# WebSocket Endpoints
# ============================================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Primary WebSocket endpoint using the new WebSocketService."""
    connection_id = await ws_service.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            await ws_service.handle_client_command(connection_id, data)
    except WebSocketDisconnect:
        await ws_service.disconnect(connection_id)
    except Exception as e:
        logger.error("WebSocket error: %s", e)
        await ws_service.disconnect(connection_id)


@app.websocket("/ws/tasks")
async def websocket_tasks_compat(websocket: WebSocket):
    """Backward-compatible alias for the old /ws/tasks endpoint."""
    connection_id = await ws_service.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            await ws_service.handle_client_command(connection_id, data)
    except WebSocketDisconnect:
        await ws_service.disconnect(connection_id)
    except Exception as e:
        logger.error("WebSocket error: %s", e)
        await ws_service.disconnect(connection_id)


# ============================================================================
# 静态文件服务（用于部署）
# ============================================================================

static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
index_html = os.path.join(static_dir, "index.html")

if os.path.exists(static_dir) and os.path.exists(index_html):
    if os.path.exists(os.path.join(static_dir, "assets")):
        app.mount("/assets", StaticFiles(directory=os.path.join(static_dir, "assets")), name="assets")

    @app.get("/")
    async def serve_root():
        return FileResponse(index_html)

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        from fastapi import HTTPException
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API endpoint not found")
        file_path = os.path.join(static_dir, full_path)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(index_html)
else:
    @app.get("/")
    async def root():
        return {
            "status": "Backend is running",
            "message": "Frontend static files not found. Please build the frontend or check deployment configuration.",
            "docs_url": "/docs"
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)