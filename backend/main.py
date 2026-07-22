# =============================================================================
# 主应用程序入口点
# 初始化 FastAPI 应用，配置中间件，注册路由模块，管理 WebSocket 连接。
# =============================================================================

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from contextlib import asynccontextmanager
import sys
import os
import logging
import json

try:
    from static_serving import ImmutableStaticFiles, frontend_file_response
except ImportError:
    from backend.static_serving import ImmutableStaticFiles, frontend_file_response

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 添加当前目录到 sys.path 以确保本地导入工作正常
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from storage import storage
    from task_manager import TaskManager
    from course_repository import CourseDocumentRepository, register_course_revision_listener
    from representation_reconciliation import RepresentationReconciliationService
    from teaching_representations import teaching_representation_repository
    from dependencies import init_task_manager
    from websocket_service import WebSocketService
    from course_service import get_course_service
except ImportError:
    try:
        from backend.storage import storage
        from backend.task_manager import TaskManager
        from backend.course_repository import CourseDocumentRepository, register_course_revision_listener
        from backend.representation_reconciliation import RepresentationReconciliationService
        from backend.teaching_representations import teaching_representation_repository
        from backend.dependencies import init_task_manager
        from backend.websocket_service import WebSocketService
        from backend.course_service import get_course_service
    except ImportError as e:
        logger.error(f"Failed to import required modules: {e}")
        raise

# 导入路由模块
from routers import (
    courses, nodes, assistant, ai_teacher,
    review,
    code_execution, diagrams, tasks,
    markdown_import, materials, course_versions, learning_assets,
    learning_snapshots, learning_progress, learning_records, learning_continuation, learning_runtime, practice, diagnostics,
    question_bank,
    course_acceptance, block_regeneration, learner_model, change_proposals,
    knowledge_libraries, teaching_representations, course_evolution,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    if representation_reconciliation_service:
        await representation_reconciliation_service.start()
    if task_manager:
        await task_manager.start()
    yield
    # Shutdown
    if task_manager:
        await task_manager.shutdown()
    if representation_reconciliation_service:
        await representation_reconciliation_service.shutdown()

app = FastAPI(lifespan=lifespan)

# 初始化 Task Manager
try:
    ws_service = WebSocketService()
    course_service = get_course_service()
    course_repository = CourseDocumentRepository(storage)
    representation_reconciliation_service = RepresentationReconciliationService(
        course_repository,
        teaching_representation_repository,
    )
    register_course_revision_listener(representation_reconciliation_service.enqueue)
    task_manager = TaskManager(
        storage,
        course_service,
        ws_service,
        document_repository=course_repository,
    )
    ws_service.set_command_handler(task_manager.handle_command)
    init_task_manager(task_manager)
except NameError:
    task_manager = None
    representation_reconciliation_service = None

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
        "http://localhost:5174",
        "http://localhost:8000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:8000",
    ],
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):\d+$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With", "X-User-Id"],
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
app.include_router(assistant.router, prefix="/api")
app.include_router(ai_teacher.router)
app.include_router(review.router, prefix="/api")
app.include_router(code_execution.router)
app.include_router(diagrams.router)
app.include_router(tasks.router, prefix="/api")
app.include_router(markdown_import.router)
app.include_router(materials.router, prefix="/api")
app.include_router(course_versions.router, prefix="/api")
app.include_router(learning_assets.router, prefix="/api")
app.include_router(learning_snapshots.router, prefix="/api")
app.include_router(learning_progress.router, prefix="/api")
app.include_router(learning_records.router, prefix="/api")
app.include_router(learning_continuation.router, prefix="/api")
app.include_router(learning_runtime.router, prefix="/api")
app.include_router(learner_model.router, prefix="/api")
app.include_router(practice.router, prefix="/api")
app.include_router(question_bank.router, prefix="/api")
app.include_router(diagnostics.router, prefix="/api")
app.include_router(course_acceptance.router, prefix="/api")
app.include_router(block_regeneration.router, prefix="/api")
app.include_router(change_proposals.router, prefix="/api")
app.include_router(change_proposals.authoring_router, prefix="/api")
app.include_router(knowledge_libraries.router, prefix="/api")
app.include_router(teaching_representations.router, prefix="/api")
app.include_router(course_evolution.router, prefix="/api")
app.include_router(course_evolution.personal_router, prefix="/api")


# ============================================================================
# WebSocket Endpoints
# ============================================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Primary WebSocket endpoint used by the frontend.

    Uses WebSocketService so that TaskManager progress updates are delivered
    to subscribed clients.
    """
    connection_id = await ws_service.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                msg_type = message.get("type", "")

                if msg_type == "ping":
                    await websocket.send_json({"type": "pong"})
                else:
                    await ws_service.handle_client_command(connection_id, message)

            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "payload": {"message": "Invalid JSON"},
                })
    except WebSocketDisconnect:
        await ws_service.disconnect(connection_id)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await ws_service.disconnect(connection_id)


# ============================================================================
# 静态文件服务（用于部署）
# ============================================================================

static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
index_html = os.path.join(static_dir, "index.html")

if os.path.exists(static_dir) and os.path.exists(index_html):
    if os.path.exists(os.path.join(static_dir, "assets")):
        app.mount(
            "/assets",
            ImmutableStaticFiles(directory=os.path.join(static_dir, "assets")),
            name="assets",
        )

    @app.get("/")
    async def serve_root():
        return frontend_file_response(index_html, entrypoint=True)

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        from fastapi import HTTPException
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API endpoint not found")
        file_path = os.path.join(static_dir, full_path)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return frontend_file_response(file_path)
        return frontend_file_response(index_html, entrypoint=True)
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
