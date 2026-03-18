# =============================================================================
# 主应用程序入口点
# 初始化 FastAPI 应用，配置中间件，注册路由模块，管理 WebSocket 连接。
# =============================================================================

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from typing import List
import sys
import os
import logging
import json
import asyncio
import threading

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 添加当前目录到 sys.path 以确保本地导入工作正常
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from storage import storage
    from ai_service import ai_service
    from task_manager import TaskManager
    from dependencies import init_task_manager
except ImportError:
    try:
        from backend.storage import storage
        from backend.ai_service import ai_service
        from backend.task_manager import TaskManager
        from backend.dependencies import init_task_manager
    except ImportError as e:
        logger.error(f"Failed to import required modules: {e}")
        raise

# 导入路由模块
from routers import (
    courses, nodes, annotations, quiz,
    knowledge_graph, learning, review,
    tutor, code_execution, diagrams, tasks,
    markdown_import, profile
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    if task_manager:
        task_manager.start_worker()
    asyncio.create_task(task_update_broadcaster())
    yield
    # Shutdown
    if task_manager:
        task_manager.stop_worker()

app = FastAPI(lifespan=lifespan)

# 初始化 Task Manager
try:
    task_manager = TaskManager(storage, ai_service)
    init_task_manager(task_manager)
except NameError:
    task_manager = None

# ============================================================================
# WebSocket Connection Manager
# ============================================================================

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self._lock = threading.Lock()
        self._broadcast_task = None

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        with self._lock:
            self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Failed to send personal message: {e}")

    async def broadcast(self, message: dict):
        with self._lock:
            connections = self.active_connections.copy()
        disconnected = []
        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Failed to broadcast to connection: {e}")
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)

    async def broadcast_task_update(self, task_id: str, update_type: str, payload: dict):
        message = {"type": update_type, "payload": payload}
        await self.broadcast(message)

ws_manager = ConnectionManager()


# ============================================================================
# Background Task Broadcaster
# ============================================================================

async def task_update_broadcaster():
    last_task_states = {}
    while True:
        try:
            if task_manager:
                tasks_list = task_manager.get_all_tasks()
                for task in tasks_list:
                    task_id = task["id"]
                    current_state = {
                        "status": task.get("status"),
                        "progress": task.get("progress"),
                        "message": task.get("message"),
                        "current_node_name": task.get("current_node_name"),
                        "completed_nodes": task.get("completed_nodes", 0),
                        "total_nodes": task.get("total_nodes", 0),
                        "updated_at": task.get("updated_at")
                    }
                    if task_id not in last_task_states:
                        last_task_states[task_id] = current_state
                        continue
                    last_state = last_task_states[task_id]
                    if (current_state["status"] != last_state["status"] or
                        current_state["progress"] != last_state["progress"] or
                        current_state["message"] != last_state["message"] or
                        current_state["completed_nodes"] != last_state["completed_nodes"] or
                        current_state["total_nodes"] != last_state["total_nodes"]):
                        await ws_manager.broadcast_task_update(
                            task_id, "progress_update",
                            {
                                "taskId": task_id,
                                "courseId": task.get("course_id"),
                                "status": task.get("status"),
                                "progress": task.get("progress"),
                                "currentNodeName": task.get("current_node_name"),
                                "completedNodes": task.get("completed_nodes", 0),
                                "totalNodes": task.get("total_nodes", 0),
                                "message": task.get("message")
                            }
                        )
                        last_task_states[task_id] = current_state
                        if task.get("status") == "completed":
                            await ws_manager.broadcast_task_update(
                                task_id, "task_completed",
                                {"taskId": task_id, "courseId": task.get("course_id"), "message": "课程生成完成"}
                            )
                        elif task.get("status") == "failed":
                            await ws_manager.broadcast_task_update(
                                task_id, "task_error",
                                {"taskId": task_id, "courseId": task.get("course_id"), "error": task.get("error", "Unknown error")}
                            )
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"Error in task update broadcaster: {e}")
            await asyncio.sleep(1)


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
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
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
app.include_router(profile.router, prefix="/api")


# ============================================================================
# WebSocket Endpoints
# ============================================================================

@app.websocket("/ws/tasks")
async def websocket_tasks(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)

                if message.get("type") == "ping":
                    await ws_manager.send_personal_message({"type": "pong"}, websocket)

                elif message.get("type") == "subscribe":
                    course_id = message.get("payload", {}).get("courseId")
                    if course_id and course_id != "all" and task_manager:
                        ws_tasks = task_manager.get_tasks_by_course(course_id)
                        for t in ws_tasks:
                            await ws_manager.send_personal_message({
                                "type": "task_update",
                                "payload": {
                                    "taskId": t["id"],
                                    "courseId": t["course_id"],
                                    "status": t["status"],
                                    "progress": t.get("progress", 0),
                                    "currentNodeName": t.get("current_node_name", ""),
                                    "message": t.get("message", "")
                                }
                            }, websocket)

                elif message.get("type") == "command":
                    command = message.get("command")
                    payload = message.get("payload", {})

                    if not task_manager:
                        await ws_manager.send_personal_message({
                            "type": "error",
                            "payload": {"message": "Task manager not available"}
                        }, websocket)
                        continue

                    if command == "pause_task":
                        course_id = payload.get("courseId")
                        ws_tasks = task_manager.get_tasks_by_course(course_id)
                        for t in ws_tasks:
                            if t["status"] in ["pending", "running"]:
                                task_manager.pause_task(t["id"])
                                await ws_manager.send_personal_message({
                                    "type": "task_update",
                                    "payload": {"taskId": t["id"], "courseId": course_id, "status": "paused"}
                                }, websocket)

                    elif command == "resume_task":
                        course_id = payload.get("courseId")
                        ws_tasks = task_manager.get_tasks_by_course(course_id)
                        for t in ws_tasks:
                            if t["status"] == "paused":
                                task_manager.resume_task(t["id"])
                                await ws_manager.send_personal_message({
                                    "type": "task_update",
                                    "payload": {"taskId": t["id"], "courseId": course_id, "status": "pending"}
                                }, websocket)

                    elif command == "cancel_task":
                        course_id = payload.get("courseId")
                        ws_tasks = task_manager.get_tasks_by_course(course_id)
                        for t in ws_tasks:
                            if t["status"] in ["pending", "running", "paused"]:
                                task_manager.delete_task(t["id"])
                                await ws_manager.send_personal_message({
                                    "type": "task_cancelled",
                                    "payload": {"taskId": t["id"], "courseId": course_id}
                                }, websocket)

                    elif command == "retry_node":
                        course_id = payload.get("courseId")
                        node_id = payload.get("nodeId")
                        await ws_manager.send_personal_message({
                            "type": "progress_update",
                            "payload": {"courseId": course_id, "message": f"Retrying node {node_id}..."}
                        }, websocket)

                    elif command == "set_priority":
                        course_id = payload.get("courseId")
                        priority = payload.get("priority", "normal")
                        await ws_manager.send_personal_message({
                            "type": "task_update",
                            "payload": {"courseId": course_id, "message": f"Priority set to {priority}"}
                        }, websocket)

            except json.JSONDecodeError:
                await ws_manager.send_personal_message({
                    "type": "error",
                    "payload": {"message": "Invalid JSON"}
                }, websocket)

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket)


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
