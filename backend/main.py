# -----------------------------------------------------------------------------
# 主应用程序入口点
# 此文件初始化 FastAPI 应用程序，配置中间件（CORS、GZip），
# 并定义课程管理、节点操作和 AI 服务的 API 路由。
# -----------------------------------------------------------------------------

from fastapi import FastAPI, HTTPException, Depends, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import sys
import os
import logging
import json
import asyncio
import threading
from datetime import datetime

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 添加当前目录到 sys.path 以确保本地导入工作正常
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from models import (
        Node, Annotation, GenerateCourseRequest, GenerateSubNodesRequest,
        RedefineContentRequest, ExtendContentRequest, AskQuestionRequest,
        UpdateAnnotationRequest, GenerateQuizRequest, LocateNodeRequest,
        AddNodeRequest, SaveAnnotationRequest, UpdateNodeRequest, SummarizeChatRequest,
        LearningPathRequest, LearningPathResponse, KnowledgePointMastery,
        ReviewScheduleRequest, ReviewScheduleResponse, SubmitReviewRequest, ReviewProgressResponse,
        ExecuteCodeRequest, ExecuteCodeResponse, ImportMarkdownResponse
    )
    from storage import storage
    from ai_service import ai_service
    from task_manager import TaskManager
    from markdown_parser import parse_markdown_to_nodes
except ImportError:
    try:
        # 当从父目录运行时回退
        from backend.models import *
        from backend.storage import storage
        from backend.ai_service import ai_service
        from backend.task_manager import TaskManager
    except ImportError as e:
        logger.error(f"Failed to import required modules: {e}")
        raise

import uuid
from datetime import datetime
from pathlib import Path
import json

app = FastAPI()

# Initialize Task Manager
try:
    task_manager = TaskManager(storage, ai_service)
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
        message = {
            "type": update_type,
            "payload": payload
        }
        await self.broadcast(message)

ws_manager = ConnectionManager()

# Background task to broadcast task updates
async def task_update_broadcaster():
    last_task_states = {}
    
    while True:
        try:
            if task_manager:
                tasks = task_manager.get_all_tasks()
                
                for task in tasks:
                    task_id = task["id"]
                    current_state = {
                        "status": task.get("status"),
                        "progress": task.get("progress"),
                        "message": task.get("message"),
                        "current_node_name": task.get("current_node_name"),
                        "updated_at": task.get("updated_at")
                    }
                    
                    if task_id not in last_task_states:
                        last_task_states[task_id] = current_state
                        continue
                    
                    last_state = last_task_states[task_id]
                    
                    if (current_state["status"] != last_state["status"] or
                        current_state["progress"] != last_state["progress"] or
                        current_state["message"] != last_state["message"]):
                        
                        await ws_manager.broadcast_task_update(
                            task_id,
                            "task_update",
                            {
                                "taskId": task_id,
                                "courseId": task.get("course_id"),
                                "status": task.get("status"),
                                "progress": task.get("progress"),
                                "currentNodeName": task.get("current_node_name"),
                                "message": task.get("message")
                            }
                        )
                        
                        last_task_states[task_id] = current_state
                        
                        if task.get("status") == "completed":
                            await ws_manager.broadcast_task_update(
                                task_id,
                                "task_completed",
                                {
                                    "taskId": task_id,
                                    "courseId": task.get("course_id"),
                                    "message": "课程生成完成"
                                }
                            )
                        elif task.get("status") == "failed":
                            await ws_manager.broadcast_task_update(
                                task_id,
                                "task_error",
                                {
                                    "taskId": task_id,
                                    "courseId": task.get("course_id"),
                                    "error": task.get("error", "Unknown error")
                                }
                            )
            
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"Error in task update broadcaster: {e}")
            await asyncio.sleep(1)

# ============================================================================
# Dependency Injection & Common Utilities
# ============================================================================

def require_task_manager():
    """依赖注入：确保Task Manager已初始化"""
    if not task_manager:
        raise HTTPException(status_code=500, detail="Task Manager not initialized")
    return task_manager

async def get_course_or_404(course_id: str) -> dict:
    """获取课程数据，如果不存在则抛出404"""
    data = await run_in_threadpool(storage.load_course, course_id)
    if not data:
        raise HTTPException(status_code=404, detail="Course not found")
    return data

def get_node_or_404(tree_data: dict, node_id: str) -> dict:
    """从课程树中获取节点，如果不存在则抛出404"""
    nodes = tree_data.get("nodes", [])
    node = next((n for n in nodes if n.get("node_id") == node_id), None)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return node

def build_course_outline(tree_data: dict, max_content_length: int = 50) -> str:
    """构建课程大纲字符串，用于AI上下文"""
    nodes = tree_data.get("nodes", [])
    l1_nodes = [n for n in nodes if n.get("node_level", 1) == 1]
    outline_parts = []
    for i, node in enumerate(l1_nodes):
        content_preview = node.get("node_content", "")[:max_content_length]
        outline_parts.append(f"{i+1}. {node.get('node_name', '')}: {content_preview}...")
    return "\n".join(outline_parts)

def get_node_content(tree_data: dict, node_id: str) -> str:
    """获取指定节点的内容"""
    nodes = tree_data.get("nodes", [])
    node = next((n for n in nodes if n.get("node_id") == node_id), None)
    return node.get("node_content", "") if node else ""

# ============================================================================
# Application Lifecycle Events
# ============================================================================

@app.on_event("startup")
async def startup_event():
    if task_manager:
        task_manager.start_worker()
    asyncio.create_task(task_update_broadcaster())

@app.on_event("shutdown")
async def shutdown_event():
    if task_manager:
        task_manager.stop_worker()

# ============================================================================
# Middleware Configuration
# ============================================================================

app.add_middleware(
    GZipMiddleware,
    minimum_size=1000
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# Health Check Endpoints
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint for deployment monitoring"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

@app.get("/api/health")
def read_root():
    return {"message": "KnowledgeMap AI API"}

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
                        tasks = task_manager.get_tasks_by_course(course_id)
                        for task in tasks:
                            await ws_manager.send_personal_message({
                                "type": "task_update",
                                "payload": {
                                    "taskId": task["id"],
                                    "courseId": task["course_id"],
                                    "status": task["status"],
                                    "progress": task.get("progress", 0),
                                    "currentNodeName": task.get("current_node_name", ""),
                                    "message": task.get("message", "")
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
                        tasks = task_manager.get_tasks_by_course(course_id)
                        for task in tasks:
                            if task["status"] in ["pending", "running"]:
                                task_manager.pause_task(task["id"])
                                await ws_manager.send_personal_message({
                                    "type": "task_update",
                                    "payload": {
                                        "taskId": task["id"],
                                        "courseId": course_id,
                                        "status": "paused"
                                    }
                                }, websocket)
                    
                    elif command == "resume_task":
                        course_id = payload.get("courseId")
                        tasks = task_manager.get_tasks_by_course(course_id)
                        for task in tasks:
                            if task["status"] == "paused":
                                task_manager.resume_task(task["id"])
                                await ws_manager.send_personal_message({
                                    "type": "task_update",
                                    "payload": {
                                        "taskId": task["id"],
                                        "courseId": course_id,
                                        "status": "pending"
                                    }
                                }, websocket)
                    
                    elif command == "cancel_task":
                        course_id = payload.get("courseId")
                        tasks = task_manager.get_tasks_by_course(course_id)
                        for task in tasks:
                            if task["status"] in ["pending", "running", "paused"]:
                                task_manager.delete_task(task["id"])
                                await ws_manager.send_personal_message({
                                    "type": "task_cancelled",
                                    "payload": {
                                        "taskId": task["id"],
                                        "courseId": course_id
                                    }
                                }, websocket)
                    
                    elif command == "retry_node":
                        course_id = payload.get("courseId")
                        node_id = payload.get("nodeId")
                        await ws_manager.send_personal_message({
                            "type": "progress_update",
                            "payload": {
                                "courseId": course_id,
                                "message": f"Retrying node {node_id}..."
                            }
                        }, websocket)
                    
                    elif command == "set_priority":
                        course_id = payload.get("courseId")
                        priority = payload.get("priority", "normal")
                        await ws_manager.send_personal_message({
                            "type": "task_update",
                            "payload": {
                                "courseId": course_id,
                                "message": f"Priority set to {priority}"
                            }
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

# --- Task Management API ---

@app.post("/courses/{course_id}/auto_generate")
def start_auto_generation(
    course_id: str,
    tm: TaskManager = Depends(require_task_manager)
):
    # Check if there is already a running or paused task
    tasks = tm.get_tasks_by_course(course_id)
    existing = [t for t in tasks if t["status"] in ["pending", "running", "paused"]]
    if existing:
        # If paused, auto-resume it
        task = existing[0]
        if task["status"] == "paused":
            tm.resume_task(task["id"])
        return {"task_id": task["id"], "status": "exists"}
    
    task_id = tm.create_task(course_id)
    return {"task_id": task_id, "status": "created"}

@app.get("/courses/{course_id}/task")
def get_course_task(
    course_id: str,
    tm: TaskManager = Depends(require_task_manager)
):
    tasks = tm.get_tasks_by_course(course_id)
    if not tasks:
        return {"status": "none"}
    
    # Return the most relevant task (running or last updated)
    tasks.sort(key=lambda x: x["updated_at"], reverse=True)
    return tasks[0]

@app.get("/tasks")
def list_tasks(
    limit: int = 100,
    tm: TaskManager = Depends(require_task_manager)
):
    return tm.get_all_tasks(limit)

@app.get("/tasks/{task_id}")
def get_task(
    task_id: str,
    tm: TaskManager = Depends(require_task_manager)
):
    task = tm.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

@app.post("/tasks/{task_id}/pause")
def pause_task(
    task_id: str,
    tm: TaskManager = Depends(require_task_manager)
):
    tm.pause_task(task_id)
    return {"status": "paused"}

@app.post("/tasks/{task_id}/resume")
def resume_task(
    task_id: str,
    tm: TaskManager = Depends(require_task_manager)
):
    tm.resume_task(task_id)
    return {"status": "resumed"}

@app.delete("/tasks/failed")
def clear_failed_tasks(
    tm: TaskManager = Depends(require_task_manager)
):
    removed_count = tm.clear_failed_tasks()
    return {"status": "success", "removed": removed_count}

@app.delete("/tasks/{task_id}")
def delete_task(
    task_id: str,
    tm: TaskManager = Depends(require_task_manager)
):
    tm.delete_task(task_id)
    return {"status": "deleted"}

# --- Course Management ---

@app.get("/courses")
async def list_courses():
    return await run_in_threadpool(storage.list_courses)

@app.get("/courses/{course_id}")
async def get_course(course_id: str):
    return await get_course_or_404(course_id)

@app.delete("/courses/{course_id}")
async def delete_course(course_id: str):
    await run_in_threadpool(storage.delete_course, course_id)
    return {"status": "success"}

@app.post("/generate_course")
async def generate_course(req: GenerateCourseRequest):
    # Generate new course content
    data = await ai_service.generate_course(
        req.keyword, 
        difficulty=req.difficulty, 
        style=req.style, 
        requirements=req.requirements
    )
    
    # Create new Course ID
    course_id = str(uuid.uuid4())
    data["course_id"] = course_id
    
    # Store metadata
    data["difficulty"] = req.difficulty
    data["style"] = req.style
    data["requirements"] = req.requirements
    
    await run_in_threadpool(storage.save_course, course_id, data)

    # Note: We return the initial structure immediately.
    # The frontend's 'generateFullDetails' and 'queue' system will handle
    # the progressive generation of sub-nodes and content.
    
    return data

# --- Node Operations (Scoped by Course) ---

@app.post("/courses/{course_id}/nodes")
async def add_custom_node(course_id: str, req: AddNodeRequest):
    tree_data = await get_course_or_404(course_id)
    
    # Determine level based on parent
    level = 1
    if req.parent_node_id and req.parent_node_id != "root":
        parent = get_node_or_404(tree_data, req.parent_node_id)
        level = parent.get("node_level", 1) + 1
    
    new_node = {
        "node_id": str(uuid.uuid4()),
        "parent_node_id": req.parent_node_id,
        "node_name": req.node_name,
        "node_level": level,
        "node_content": "Custom content...",
        "node_type": "custom"
    }
    
    if "nodes" not in tree_data:
        tree_data["nodes"] = []
    
    tree_data["nodes"].append(new_node)
    await run_in_threadpool(storage.save_course, course_id, tree_data)
    return new_node

@app.post("/courses/{course_id}/nodes/{node_id}/subnodes")
async def generate_subnodes(course_id: str, node_id: str, req: GenerateSubNodesRequest):
    tree_data = await get_course_or_404(course_id)
    
    # Check if subnodes already exist to prevent duplication
    existing_children = [n for n in tree_data.get("nodes", []) if n.get("parent_node_id") == node_id]
    if existing_children:
        # Return existing children instead of regenerating (deduplication)
        return existing_children

    course_name = tree_data.get("course_name", "")
    
    # Build context for AI
    course_outline = build_course_outline(tree_data, max_content_length=50)
    parent_context = get_node_content(tree_data, node_id)
    
    new_nodes = await ai_service.generate_sub_nodes(
        req.node_name, 
        req.node_level, 
        node_id, 
        course_name, 
        parent_context, 
        course_outline,
        req.difficulty,
        req.style
    )
    
    if "nodes" not in tree_data:
        tree_data["nodes"] = []
    
    for node in new_nodes:
        tree_data["nodes"].append(node)
    await run_in_threadpool(storage.save_course, course_id, tree_data)
    
    return new_nodes

@app.post("/courses/{course_id}/nodes/{node_id}/redefine_stream")
async def redefine_node_stream(course_id: str, node_id: str, req: RedefineContentRequest):
    """
    Streams the content generation for a specific node.
    This provides a real-time typing effect on the frontend.
    """
    # Verify existence
    await get_course_or_404(course_id)
    
    async def stream_generator():
        full_content = ""
        try:
            async for chunk in ai_service.redefine_node_content(
                node_name=req.node_name,
                original_content=req.original_content,
                requirement=req.user_requirement,
                course_context=req.course_context,
                previous_context=req.previous_context,
                difficulty=req.difficulty,
                style=req.style
            ):
                full_content += chunk
                yield chunk
        except Exception as e:
            logger.error(f"Error in stream generation: {e}")
            yield f"\n[Error: {e}]"
        
        # After streaming, save to storage
        # Reload to minimize race conditions
        try:
            current_data = await run_in_threadpool(storage.load_course, course_id)
            if "nodes" in current_data:
                for node in current_data["nodes"]:
                    if node["node_id"] == node_id:
                        node["node_content"] = ai_service.clean_response_text(full_content)
                        node["node_type"] = "custom"
                        break
                await run_in_threadpool(storage.save_course, course_id, current_data)
        except Exception as e:
            logger.error(f"Error saving stream result: {e}")
            
    return StreamingResponse(stream_generator(), media_type="text/plain")

@app.post("/courses/{course_id}/nodes/{node_id}/redefine")
async def redefine_node(course_id: str, node_id: str, req: RedefineContentRequest):
    tree_data = await get_course_or_404(course_id)
    
    # Get the node to verify it exists
    node = get_node_or_404(tree_data, node_id)
    
    new_content = await ai_service.redefine_content(
        node_name=req.node_name, 
        requirement=req.user_requirement,
        original_content=req.original_content,
        course_context=req.course_context,
        previous_context=req.previous_context,
        difficulty=req.difficulty,
        style=req.style
    )
    
    # Update the node
    node["node_content"] = new_content
    node["node_type"] = "custom"
    
    await run_in_threadpool(storage.save_course, course_id, tree_data)
    return {"node_content": new_content}


# -----------------------------------------------------------------------------
# Knowledge Graph API
# -----------------------------------------------------------------------------
class KnowledgeGraphRequest(BaseModel):
    course_id: str


@app.post("/courses/{course_id}/knowledge_graph")
async def generate_knowledge_graph(course_id: str):
    """
    Generate a knowledge graph for the course using AI.
    """
    tree_data = await get_course_or_404(course_id)
    
    if "nodes" not in tree_data:
        raise HTTPException(status_code=404, detail="Course has no nodes")
    
    course_name = tree_data.get("course_name", "Unknown Course")
    nodes = tree_data.get("nodes", [])
    
    # Build course context using helper function
    course_context = f"Course: {course_name}\n"
    for node in nodes[:20]:
        content_preview = node.get("node_content", "")[:100]
        course_context += f"- {node.get('node_name', '')}: {content_preview}\n"
    
    # Generate knowledge graph
    graph_data = await ai_service.generate_knowledge_graph(
        course_name=course_name,
        course_context=course_context,
        nodes=nodes
    )
    
    # Cache the graph in storage
    await run_in_threadpool(storage.save_knowledge_graph, course_id, graph_data)
    
    return {
        "status": "success",
        "data": graph_data
    }


@app.get("/courses/{course_id}/knowledge_graph")
async def get_knowledge_graph(course_id: str):
    """
    Get the cached knowledge graph for a course.
    """
    graph_data = await run_in_threadpool(storage.load_knowledge_graph, course_id)
    if graph_data:
        return {
            "status": "success",
            "data": graph_data,
            "cached": True
        }
    
    # Return empty graph if not cached
    return {
        "status": "success",
        "data": {"nodes": [], "edges": []},
        "cached": False
    }

@app.post("/courses/{course_id}/nodes/{node_id}/quiz")
async def generate_quiz(course_id: str, node_id: str, req: GenerateQuizRequest):
    return await ai_service.generate_quiz(
        req.node_content, 
        node_name=req.node_name,
        difficulty=req.difficulty,
        style=req.style,
        user_persona=req.user_persona,
        question_count=req.question_count
    )

@app.post("/courses/{course_id}/nodes/{node_id}/extend")
async def extend_node_content(course_id: str, node_id: str, req: ExtendContentRequest):
    # req: node_name, requirement
    content = await ai_service.extend_content(req.node_name, req.user_requirement)
    
    # Save?
    # For now, just return, frontend appends
    return {"content": content}

class SummarizeNodeRequest(BaseModel):
    node_content: str
    node_name: str
    user_persona: Optional[str] = None

@app.post("/courses/{course_id}/nodes/{node_id}/summarize")
async def summarize_node(course_id: str, node_id: str, req: SummarizeNodeRequest):
    summary = await ai_service.summarize_content(
        req.node_content,
        node_name=req.node_name,
        user_persona=req.user_persona
    )
    return {"summary": summary}

@app.post("/ask")
def ask_question(req: AskQuestionRequest):
    return StreamingResponse(
        ai_service.answer_question_stream(
            req.question,
            req.node_content,
            req.history,
            req.selection,
            req.user_persona,
            req.course_id,
            req.node_id,
            req.user_notes,
            req.session_metrics,
            req.enable_long_term_memory
        ),
        media_type="text/plain"
    )

@app.get("/nodes/{node_id}/annotations")
async def get_annotations(node_id: str):
    return await run_in_threadpool(storage.get_annotations_by_node, node_id)

@app.post("/annotations")
async def save_annotation(req: SaveAnnotationRequest):
    # Basic validation is handled by Pydantic
    
    data = req.dict()
    # Ensure ID
    if not data.get("anno_id"):
        data["anno_id"] = f"anno_{uuid.uuid4()}"
    
    # AI-Enhanced Summary Generation
    # If anno_summary is just a truncated version of answer (or default), try to generate a better one
    # Only if answer is long enough (> 50 chars) and source_type is user/ai
    if len(data.get("answer", "")) > 50:
        # Check if summary is "lazy" (i.e. starts with answer prefix)
        current_summary = data.get("anno_summary", "")
        answer_start = data.get("answer", "")[:20]
        
        if not current_summary or current_summary.startswith(answer_start) or current_summary == "Note":
             try:
                 # Call AI Service to generate summary
                 generated_summary = await ai_service.summarize_note(data["answer"])
                 if generated_summary:
                     data["anno_summary"] = generated_summary
             except Exception as e:
                 print(f"Failed to generate AI summary for note: {e}")

    await run_in_threadpool(storage.save_annotation, data)
    return data

@app.delete("/annotations/{anno_id}")
async def delete_annotation(anno_id: str):
    await run_in_threadpool(storage.delete_annotation, anno_id)
    return {"status": "success"}

@app.put("/annotations/{anno_id}")
async def update_annotation(anno_id: str, req: UpdateAnnotationRequest):
    await run_in_threadpool(storage.update_annotation, anno_id, req.content)
    return {"status": "success"}

@app.put("/annotations/{anno_id}/tags")
async def update_annotation_tags(anno_id: str, req: dict):
    tags = req.get("tags", [])
    updated = await run_in_threadpool(storage.update_annotation_field, anno_id, "tags", tags)
    if not updated:
        raise HTTPException(status_code=404, detail="Annotation not found")
    return {"status": "success"}

@app.put("/annotations/{anno_id}/category")
async def update_annotation_category(anno_id: str, req: dict):
    category = req.get("category", "")
    updated = await run_in_threadpool(storage.update_annotation_field, anno_id, "category", category)
    if not updated:
        raise HTTPException(status_code=404, detail="Annotation not found")
    return {"status": "success"}

@app.put("/annotations/{anno_id}/priority")
async def update_annotation_priority(anno_id: str, req: dict):
    priority = req.get("priority", "medium")
    updated = await run_in_threadpool(storage.update_annotation_field, anno_id, "priority", priority)
    if not updated:
        raise HTTPException(status_code=404, detail="Annotation not found")
    return {"status": "success"}

@app.get("/courses/{course_id}/annotations")
async def get_course_annotations(course_id: str):
    """返回课程的所有批注（通过课程中的节点进行过滤）"""
    course_data = await get_course_or_404(course_id)
    
    if "nodes" not in course_data:
        return []
    
    node_ids = set(n["node_id"] for n in course_data["nodes"])
    
    # 获取所有批注并过滤
    all_annos = await run_in_threadpool(storage.load_annotations)
    results = []
    for a in all_annos:
        # 如果批注有 course_id，则必须匹配
        if a.get("course_id"):
            if a.get("course_id") == course_id:
                results.append(a)
        # 如果批注没有 course_id，则回退到 node_id 检查
        elif a.get("node_id") in node_ids:
            # 避免通用 ID (如 "id_1") 导致的跨课程泄露
            # 仅保留 ID 长度较长（看似 UUID）的旧笔记
            if len(a.get("node_id", "")) > 10:
                results.append(a)
                
    return results


@app.post("/courses/{course_id}/locate")
async def locate_node(course_id: str, req: LocateNodeRequest):
    tree_data = await get_course_or_404(course_id)
    if "nodes" not in tree_data:
        return {}
    return await ai_service.locate_node(req.keyword, tree_data["nodes"])

@app.post("/generate_quiz")
async def generate_quiz(req: GenerateQuizRequest):
    return await ai_service.generate_quiz(
        req.node_content,
        difficulty=req.difficulty,
        style=req.style,
        user_persona=req.user_persona,
        question_count=req.question_count
    )

@app.post("/summarize_chat")
async def summarize_chat(req: SummarizeChatRequest):
    return await ai_service.summarize_chat(req.history, req.course_context, req.user_persona)

@app.delete("/courses/{course_id}/nodes/{node_id}")
async def delete_node(course_id: str, node_id: str):
    """删除节点及其所有子节点"""
    tree_data = await get_course_or_404(course_id)
    
    if "nodes" not in tree_data:
        raise HTTPException(status_code=404, detail="Course has no nodes")
    
    original_len = len(tree_data["nodes"])
    
    # Find all descendants to delete
    to_delete = {node_id}
    changed = True
    while changed:
        changed = False
        for node in tree_data["nodes"]:
            if node.get("parent_node_id") in to_delete and node["node_id"] not in to_delete:
                to_delete.add(node["node_id"])
                changed = True
    
    tree_data["nodes"] = [n for n in tree_data["nodes"] if n["node_id"] not in to_delete]
    
    if len(tree_data["nodes"]) < original_len:
        await run_in_threadpool(storage.save_course, course_id, tree_data)
        return {"status": "success"}
        
    raise HTTPException(status_code=404, detail="Node not found")

@app.put("/courses/{course_id}/nodes/{node_id}")
async def update_node(course_id: str, node_id: str, node_update: UpdateNodeRequest):
    """更新节点信息"""
    tree_data = await get_course_or_404(course_id)
    
    if "nodes" not in tree_data:
        raise HTTPException(status_code=404, detail="Course has no nodes")
    
    # Find and update the node
    node = await get_node_or_404(tree_data, node_id)
    
    if node_update.node_name is not None:
        node["node_name"] = node_update.node_name
    if node_update.node_content is not None:
        node["node_content"] = node_update.node_content
    if node_update.is_read is not None:
        node["is_read"] = node_update.is_read
    
    await run_in_threadpool(storage.save_course, course_id, tree_data)
    return {"status": "success", "node": node}


# --- Learning Path & Recommendation APIs ---

@app.post("/courses/{course_id}/learning_path", response_model=LearningPathResponse)
async def generate_learning_path(course_id: str, req: LearningPathRequest):
    """
    Generate personalized learning path recommendations based on user's learning progress.
    """
    course_data = await get_course_or_404(course_id)
    all_nodes = course_data.get("nodes", [])
    
    # Generate learning path using AI service
    result = await ai_service.generate_learning_path(
        course_id=course_id,
        progress_data=[p.dict() for p in req.progress_data],
        wrong_answer_nodes=req.wrong_answer_nodes,
        target_goal=req.target_goal or "系统学习",
        available_time=req.available_time_minutes or 30,
        all_nodes=all_nodes
    )
    
    return LearningPathResponse(**result)


@app.get("/courses/{course_id}/knowledge_mastery")
async def get_knowledge_mastery(course_id: str):
    """
    Get knowledge mastery analysis for all nodes in a course.
    """
    course_data = await get_course_or_404(course_id)
    all_nodes = course_data.get("nodes", [])
    
    # Build progress data from node metadata
    progress_data = []
    for node in all_nodes:
        progress_data.append({
            "node_id": node.get("node_id"),
            "node_name": node.get("node_name"),
            "is_read": node.get("is_read", False),
            "read_time_minutes": node.get("read_time_minutes", 0),
            "quiz_score": node.get("quiz_score"),
            "last_accessed": node.get("last_accessed"),
            "notes_count": node.get("notes_count", 0)
        })
    
    # Analyze mastery
    mastery_data = await ai_service.analyze_knowledge_mastery(
        course_id=course_id,
        progress_data=progress_data,
        quiz_history=[],  # Could be loaded from storage if available
        all_nodes=all_nodes
    )
    
    return mastery_data


@app.get("/courses/{course_id}/learning_stats")
async def get_learning_stats(course_id: str):
    """
    Get comprehensive learning statistics for a course.
    """
    course_data = await get_course_or_404(course_id)
    nodes = course_data.get("nodes", [])
    
    # Calculate statistics
    total_nodes = len(nodes)
    completed_nodes = sum(1 for n in nodes if n.get("is_read", False))
    nodes_with_quiz = [n for n in nodes if n.get("quiz_score") is not None]
    
    avg_quiz_score = 0
    if nodes_with_quiz:
        avg_quiz_score = sum(n.get("quiz_score", 0) for n in nodes_with_quiz) / len(nodes_with_quiz)
    
    total_reading_time = sum(n.get("read_time_minutes", 0) for n in nodes)
    
    # Identify weak areas (quiz score < 60)
    weak_areas = [
        {
            "node_id": n.get("node_id"),
            "node_name": n.get("node_name"),
            "quiz_score": n.get("quiz_score"),
            "reason": "测验成绩较低，需要复习"
        }
        for n in nodes_with_quiz if n.get("quiz_score", 100) < 60
    ]
    
    return {
        "course_id": course_id,
        "course_name": course_data.get("course_name", "Unknown"),
        "total_nodes": total_nodes,
        "completed_nodes": completed_nodes,
        "completion_percentage": round(completed_nodes / total_nodes * 100, 1) if total_nodes > 0 else 0,
        "total_reading_time_minutes": total_reading_time,
        "quizzes_taken": len(nodes_with_quiz),
        "average_quiz_score": round(avg_quiz_score, 1),
        "weak_areas": weak_areas,
        "strong_areas": [
            {
                "node_id": n.get("node_id"),
                "node_name": n.get("node_name"),
                "quiz_score": n.get("quiz_score"),
                "reason": "掌握良好"
            }
            for n in nodes_with_quiz if n.get("quiz_score", 0) >= 80
        ]
    }


# --- Smart Review System APIs ---

@app.get("/courses/{course_id}/review/schedule")
async def get_review_schedule(course_id: str, max_items: int = 20, focus_on_weak: bool = True):
    """
    获取智能复习计划
    
    基于SM-2算法和艾宾浩斯遗忘曲线生成个性化复习计划
    """
    course_data = await get_course_or_404(course_id)
    
    result = await ai_service.generate_review_schedule(
        course_id=course_id,
        course_data=course_data,
        max_items=max_items,
        focus_on_weak=focus_on_weak
    )
    
    return result


@app.post("/courses/{course_id}/review/submit")
async def submit_review_results(course_id: str, req: SubmitReviewRequest):
    """
    提交复习结果
    
    使用SM-2算法更新复习间隔和记忆强度
    """
    course_data = await get_course_or_404(course_id)
    
    # 提交复习结果并更新复习历史
    result = await ai_service.submit_review_results(
        course_id=course_id,
        course_data=course_data,
        results=[r.dict() for r in req.results]
    )
    
    # 保存更新后的课程数据
    await run_in_threadpool(storage.save_course, course_id, course_data)
    
    return result


@app.get("/courses/{course_id}/review/progress")
async def get_review_progress(course_id: str):
    """
    获取复习进度和记忆曲线
    
    返回过去30天的记忆保留率曲线和掌握度趋势
    """
    course_data = await get_course_or_404(course_id)
    
    result = await ai_service.get_review_progress(
        course_id=course_id,
        course_data=course_data
    )
    
    return result


def _get_today_date() -> datetime:
    """获取今天的日期（去除时间部分）"""
    return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)


def _parse_iso_date(date_str: str) -> datetime:
    """解析ISO格式的日期字符串"""
    return datetime.fromisoformat(date_str)


@app.get("/courses/{course_id}/review/stats")
async def get_review_stats(course_id: str):
    """
    获取复习统计数据（快速查询）
    """
    course_data = await get_course_or_404(course_id)
    
    # 快速获取复习统计
    review_history = course_data.get("review_history", {})
    nodes = course_data.get("nodes", [])
    
    today = _get_today_date()
    
    due_today = 0
    overdue = 0
    completed_today = 0
    
    for node in nodes:
        node_id = node.get("node_id")
        node_review = review_history.get(node_id, {})
        
        if node_review.get("next_review"):
            next_review = _parse_iso_date(node_review["next_review"])
            if next_review.date() < today.date():
                overdue += 1
            elif next_review.date() == today.date():
                due_today += 1
        
        if node_review.get("last_reviewed"):
            last_reviewed = _parse_iso_date(node_review["last_reviewed"])
            if last_reviewed.date() == today.date():
                completed_today += 1
    
    return {
        "course_id": course_id,
        "total_items": len(nodes),
        "due_today": due_today,
        "overdue": overdue,
        "completed_today": completed_today,
        "streak_days": course_data.get("learning_streak", 0),
        "retention_rate": 0.75,  # 简化计算
        "last_review_date": course_data.get("last_review_date")
    }


@app.post("/courses/{course_id}/review/reset")
async def reset_review_history(course_id: str):
    """
    重置复习历史（用于调试或重新开始）
    """
    course_data = await get_course_or_404(course_id)
    
    # 清除复习历史
    course_data["review_history"] = {}
    course_data["learning_streak"] = 0
    course_data["last_review_date"] = None
    course_data["last_study_date"] = None
    
    await run_in_threadpool(storage.save_course, course_id, course_data)
    
    return {"status": "success", "message": "复习历史已重置"}


# --- Code Execution API ---

import subprocess
import tempfile
import time
import re

# Supported languages configuration
SUPPORTED_LANGUAGES = {
    "python": {
        "extension": ".py",
        "command": ["python3"],
        "timeout": 30
    },
    "javascript": {
        "extension": ".js",
        "command": ["node"],
        "timeout": 30
    },
    "typescript": {
        "extension": ".ts",
        "command": ["npx", "ts-node"],
        "timeout": 30
    },
    "bash": {
        "extension": ".sh",
        "command": ["bash"],
        "timeout": 10
    },
    "shell": {
        "extension": ".sh",
        "command": ["sh"],
        "timeout": 10
    }
}

# Security: Forbidden code patterns
FORBIDDEN_PATTERNS = [
    r"import\s+os\s*;.*system",
    r"subprocess\.call",
    r"subprocess\.run",
    r"subprocess\.Popen",
    r"eval\s*\(",
    r"exec\s*\(",
    r"__import__",
    r"open\s*\(.*['\"]\s*[/\\]",
    r"rm\s+-rf\s+/",
    r">\s*/",
    r"dd\s+if=",
]

MAX_OUTPUT_LENGTH = 10000


def _validate_code_security(code: str) -> tuple[bool, str]:
    """验证代码安全性，返回(是否安全, 错误信息)"""
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, code, re.IGNORECASE):
            return False, "Security Error: Code contains potentially dangerous operations"
    return True, ""


def _truncate_output(output: str, max_length: int = MAX_OUTPUT_LENGTH) -> str:
    """截断过长的输出"""
    if len(output) > max_length:
        return output[:max_length] + "\n... (output truncated)"
    return output


def _cleanup_temp_file(file_path: str):
    """安全地清理临时文件"""
    try:
        if os.path.exists(file_path):
            os.unlink(file_path)
    except OSError:
        pass


@app.post("/api/execute")
async def execute_code(req: ExecuteCodeRequest):
    """
    执行代码并返回结果
    
    支持 Python、JavaScript、TypeScript、Bash 等语言
    出于安全考虑，代码在沙箱环境中运行，有执行时间限制
    """
    language = req.language.lower()
    
    # Check if language is supported
    if language not in SUPPORTED_LANGUAGES:
        raise HTTPException(
            status_code=400, 
            detail=f"Unsupported language: {language}. Supported: {', '.join(SUPPORTED_LANGUAGES.keys())}"
        )
    
    lang_config = SUPPORTED_LANGUAGES[language]
    timeout = min(req.timeout, lang_config["timeout"])
    
    # Security validation
    is_safe, error_msg = _validate_code_security(req.code)
    if not is_safe:
        return ExecuteCodeResponse(
            success=False,
            output="",
            error=error_msg,
            execution_time=0,
            language=language
        )
    
    start_time = time.time()
    temp_file_path = None
    
    try:
        # Create temporary file
        with tempfile.NamedTemporaryFile(
            mode='w', 
            suffix=lang_config["extension"], 
            delete=False
        ) as temp_file:
            temp_file.write(req.code)
            temp_file_path = temp_file.name
        
        # Execute code
        result = subprocess.run(
            lang_config["command"] + [temp_file_path],
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        execution_time = (time.time() - start_time) * 1000
        
        # Clean up temp file
        _cleanup_temp_file(temp_file_path)
        temp_file_path = None
        
        output = _truncate_output(result.stdout)
        error = result.stderr if result.stderr else None
        
        return ExecuteCodeResponse(
            success=result.returncode == 0,
            output=output,
            error=error,
            execution_time=round(execution_time, 2),
            language=language
        )
        
    except subprocess.TimeoutExpired:
        execution_time = (time.time() - start_time) * 1000
        _cleanup_temp_file(temp_file_path)
        
        return ExecuteCodeResponse(
            success=False,
            output="",
            error=f"Execution timeout: Code took longer than {timeout} seconds to execute",
            execution_time=round(execution_time, 2),
            language=language
        )
        
    except Exception as e:
        execution_time = (time.time() - start_time) * 1000
        _cleanup_temp_file(temp_file_path)
        
        return ExecuteCodeResponse(
            success=False,
            output="",
            error=f"Execution error: {str(e)}",
            execution_time=round(execution_time, 2),
            language=language
        )


@app.get("/api/execute/languages")
async def get_supported_languages():
    """获取支持的编程语言列表"""
    return {
        "languages": [
            {
                "id": lang_id,
                "name": lang_id.capitalize(),
                "extension": config["extension"],
                "timeout": config["timeout"]
            }
            for lang_id, config in SUPPORTED_LANGUAGES.items()
        ]
    }


# --- AI 图表生成 API ---

class GenerateDiagramRequest(BaseModel):
    """AI图表生成请求"""
    description: str = Field(..., description="图表描述", min_length=1, max_length=2000)
    diagram_type: str = Field(default="flowchart", description="图表类型")
    context: str = Field(default="", description="额外上下文信息", max_length=1000)


class GenerateDiagramResponse(BaseModel):
    """AI图表生成响应"""
    success: bool = Field(..., description="是否成功")
    diagram_code: Optional[str] = Field(default=None, description="生成的Mermaid代码")
    diagram_type: str = Field(default="flowchart", description="图表类型")
    description: str = Field(default="", description="原始描述")
    error: Optional[str] = Field(default=None, description="错误信息")


DIAGRAM_TYPES = [
    "flowchart",      # 流程图
    "sequenceDiagram", # 时序图
    "classDiagram",   # 类图
    "stateDiagram",   # 状态图
    "erDiagram",      # ER图
    "gantt",          # 甘特图
    "pie",            # 饼图
    "mindmap",        # 思维导图
]


@app.post("/api/diagram/generate", response_model=GenerateDiagramResponse)
async def generate_diagram(req: GenerateDiagramRequest):
    """
    使用AI生成Mermaid图表

    根据用户的自然语言描述，自动生成对应的Mermaid图表代码。
    支持多种图表类型：流程图、时序图、类图、状态图等。

    ## 示例请求
    ```json
    {
        "description": "展示用户登录系统的流程，包括输入用户名密码、验证、成功或失败的处理",
        "diagram_type": "flowchart",
        "context": "这是一个Web应用的登录流程"
    }
    ```

    ## 支持的图表类型
    - `flowchart`: 流程图（默认）
    - `sequenceDiagram`: 时序图
    - `classDiagram`: 类图
    - `stateDiagram`: 状态图
    - `erDiagram`: ER图
    - `gantt`: 甘特图
    - `pie`: 饼图
    - `mindmap`: 思维导图
    """
    # Validate diagram type
    if req.diagram_type not in DIAGRAM_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported diagram type: {req.diagram_type}. Supported: {', '.join(DIAGRAM_TYPES)}"
        )

    try:
        result = await ai_service.generate_diagram(
            description=req.description,
            diagram_type=req.diagram_type,
            context=req.context
        )

        return GenerateDiagramResponse(
            success=result.get("success", False),
            diagram_code=result.get("diagram_code"),
            diagram_type=result.get("diagram_type", req.diagram_type),
            description=result.get("description", req.description),
            error=result.get("error")
        )

    except Exception as e:
        logger.error(f"Error in generate_diagram endpoint: {e}")
        raise HTTPException(status_code=500, detail=f"生成图表时出错: {str(e)}")


@app.get("/api/diagram/types")
async def get_diagram_types():
    """获取支持的图表类型列表"""
    return {
        "types": [
            {
                "id": "flowchart",
                "name": "流程图",
                "description": "展示流程、算法、决策树",
                "icon": "mdi-sitemap"
            },
            {
                "id": "sequenceDiagram",
                "name": "时序图",
                "description": "展示对象间的交互顺序",
                "icon": "mdi-arrow-right-bold-outline"
            },
            {
                "id": "classDiagram",
                "name": "类图",
                "description": "展示类结构和关系",
                "icon": "mdi-code-braces"
            },
            {
                "id": "stateDiagram",
                "name": "状态图",
                "description": "展示状态转换",
                "icon": "mdi-state-machine"
            },
            {
                "id": "erDiagram",
                "name": "ER图",
                "description": "展示实体关系",
                "icon": "mdi-database"
            },
            {
                "id": "gantt",
                "name": "甘特图",
                "description": "展示项目时间线",
                "icon": "mdi-chart-timeline"
            },
            {
                "id": "pie",
                "name": "饼图",
                "description": "展示比例分布",
                "icon": "mdi-chart-pie"
            },
            {
                "id": "mindmap",
                "name": "思维导图",
                "description": "展示层级思维结构",
                "icon": "mdi-graph-outline"
            }
        ]
    }


# ============================================================================
# 智能导师服务 API - 统一的学习助手接口
# ============================================================================

try:
    from tutor_service import (
        get_tutor_memory, get_proactive_engine,
        tutor_memory, proactive_engine,
        GoalType, GoalStatus
    )
    TUTOR_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Tutor service not available: {e}")
    TUTOR_AVAILABLE = False


class CreateGoalRequest(BaseModel):
    title: str
    description: str
    goal_type: str = "task_oriented"
    target_value: float
    unit: str = "个"
    deadline: Optional[str] = None
    related_nodes: List[str] = []
    priority: int = 1


class UpdateGoalProgressRequest(BaseModel):
    progress_delta: float


class RecordLearningRequest(BaseModel):
    node_id: str
    node_title: str
    is_correct: Optional[bool] = None
    time_spent: float = 0.0
    question_data: Optional[Dict] = None


class SessionSummaryRequest(BaseModel):
    duration: float
    questions_answered: int = 0
    correct_count: int = 0
    nodes_studied: List[str] = []


class TutorContextRequest(BaseModel):
    time_stuck: int = 0
    consecutive_wrong: int = 0
    current_node_id: Optional[str] = None


@app.get("/api/tutor/greeting")
async def get_tutor_greeting(course_id: Optional[str] = None, node_id: Optional[str] = None):
    """获取智能导师问候语 - 每次打开AI助手时调用"""
    if not TUTOR_AVAILABLE:
        return {
            "greeting": "👋 你好！我是你的AI学习助手，有什么可以帮助你的吗？",
            "actions": [],
            "stats": {}
        }
    
    user_id = "default_user"
    result = proactive_engine.generate_greeting(user_id, course_id, node_id)
    return result


@app.get("/api/tutor/profile")
async def get_tutor_profile():
    """获取学习者画像"""
    if not TUTOR_AVAILABLE:
        raise HTTPException(status_code=503, detail="导师服务未加载")
    
    user_id = "default_user"
    profile = tutor_memory.get_or_create_profile(user_id)
    weaknesses = tutor_memory.get_weaknesses(user_id)
    strengths = tutor_memory.get_strengths(user_id)
    
    return {
        "profile": profile,
        "weaknesses": weaknesses[:5],
        "strengths": strengths[:5],
        "knowledge_count": len(tutor_memory.knowledge_states.get(user_id, {}))
    }


@app.post("/api/tutor/record-learning")
async def record_learning(req: RecordLearningRequest):
    """记录学习行为 - 答题后调用"""
    if not TUTOR_AVAILABLE:
        return {"success": False}
    
    user_id = "default_user"
    state = tutor_memory.update_knowledge_state(
        user_id=user_id,
        node_id=req.node_id,
        node_title=req.node_title,
        is_correct=req.is_correct,
        time_spent=req.time_spent,
        question_data=req.question_data
    )
    
    return {
        "success": True,
        "mastery_level": state.mastery_level,
        "confidence": state.confidence,
        "correct_rate": state.correct_rate
    }


@app.post("/api/tutor/session-summary")
async def create_session_summary(req: SessionSummaryRequest):
    """创建学习会话总结"""
    if not TUTOR_AVAILABLE:
        return {"summary": "学习完成！", "stats": {}}
    
    user_id = "default_user"
    tutor_memory.record_study_session(user_id, req.duration, req.nodes_studied)
    
    result = proactive_engine.generate_session_summary(user_id, {
        'duration': req.duration,
        'questions_answered': req.questions_answered,
        'correct_count': req.correct_count
    })
    
    return result


@app.get("/api/tutor/review-items")
async def get_review_items(limit: int = 5):
    """获取待复习知识点"""
    if not TUTOR_AVAILABLE:
        return {"review_items": []}
    
    user_id = "default_user"
    items = tutor_memory.get_review_items(user_id, limit)
    return {"review_items": items}


@app.get("/api/tutor/wrong-answers")
async def get_wrong_answers(limit: int = 5):
    """获取错题本"""
    if not TUTOR_AVAILABLE:
        return {"wrong_answers": []}
    
    user_id = "default_user"
    items = tutor_memory.get_wrong_answers_for_review(user_id, limit)
    return {"wrong_answers": items}


@app.post("/api/tutor/suggestion")
async def get_tutor_suggestion(req: TutorContextRequest):
    """根据上下文获取学习建议"""
    if not TUTOR_AVAILABLE:
        return {"suggestions": []}
    
    user_id = "default_user"
    result = proactive_engine.generate_study_suggestion(user_id, {
        'time_stuck': req.time_stuck,
        'consecutive_wrong': req.consecutive_wrong,
        'current_node_id': req.current_node_id
    })
    return result


@app.get("/api/tutor/goals")
async def get_tutor_goals(status: Optional[str] = None):
    """获取学习目标"""
    if not TUTOR_AVAILABLE:
        return {"goals": []}
    
    user_id = "default_user"
    goals = tutor_memory.goals.get(user_id, [])
    
    if status:
        goals = [g for g in goals if g.status.value == status]
    
    return {"goals": [g.to_dict() for g in goals]}


@app.post("/api/tutor/goals")
async def create_tutor_goal(req: CreateGoalRequest):
    """创建学习目标"""
    if not TUTOR_AVAILABLE:
        raise HTTPException(status_code=503, detail="导师服务未加载")
    
    user_id = "default_user"
    
    try:
        goal_type = GoalType(req.goal_type)
    except ValueError:
        goal_type = GoalType.TASK_ORIENTED
    
    deadline = None
    if req.deadline:
        try:
            deadline = datetime.fromisoformat(req.deadline.replace('Z', '+00:00'))
        except ValueError:
            try:
                deadline = datetime.strptime(req.deadline, "%Y-%m-%d")
            except ValueError:
                pass
    
    goal = tutor_memory.create_goal(
        user_id=user_id,
        title=req.title,
        description=req.description,
        goal_type=goal_type,
        target_value=req.target_value,
        unit=req.unit,
        deadline=deadline,
        related_nodes=req.related_nodes,
        priority=req.priority
    )
    
    return {"success": True, "goal": goal.to_dict()}


@app.put("/api/tutor/goals/{goal_id}/progress")
async def update_tutor_goal_progress(goal_id: str, req: UpdateGoalProgressRequest):
    """更新目标进度"""
    if not TUTOR_AVAILABLE:
        raise HTTPException(status_code=503, detail="导师服务未加载")
    
    user_id = "default_user"
    goal = tutor_memory.update_goal_progress(user_id, goal_id, req.progress_delta)
    
    if not goal:
        raise HTTPException(status_code=404, detail="目标不存在")
    
    return {"success": True, "goal": goal.to_dict()}


@app.get("/api/tutor/goal-recommendations")
async def get_goal_recommendations():
    """获取目标建议"""
    if not TUTOR_AVAILABLE:
        return {"recommendations": []}
    
    user_id = "default_user"
    recommendations = tutor_memory.get_goal_recommendations(user_id)
    return {"recommendations": recommendations}



# --- Markdown 导入 ---

@app.post("/api/import_markdown", response_model=ImportMarkdownResponse)
async def import_markdown(file: UploadFile = File(...)):
    """将上传的 Markdown 文件解析为课程节点树并持久化存储。"""
    content = await file.read()

    # 大小校验
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="上传的文件为空")
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件过大，最大支持 20 MB")

    # MIME 类型校验
    allowed_mime = {"text/markdown", "text/plain", "application/octet-stream"}
    if file.content_type not in allowed_mime:
        raise HTTPException(status_code=415, detail="不支持的文件类型，请上传 .md 或 .txt 文件")

    # 编码校验
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=422, detail="文件编码不支持，请使用 UTF-8 编码的 Markdown 文件")

    stem = Path(file.filename).stem

    # 解析
    try:
        nodes, course_name = parse_markdown_to_nodes(text, stem)
    except ValueError:
        raise HTTPException(status_code=422, detail="未检测到 Markdown 标题，请确保文件包含至少一个 # 标题")

    # 构建课程树
    course_id = str(uuid.uuid4())
    course_tree = {
        "course_id": course_id,
        "course_name": course_name,
        "keyword": course_name,
        "nodes": nodes,
        "difficulty": "intermediate",
        "style": "academic",
        "create_time": datetime.utcnow().isoformat(),
    }

    await run_in_threadpool(storage.save_course, course_id, course_tree)

    return ImportMarkdownResponse(course_id=course_id, course_name=course_name)


# --- 静态文件服务（用于部署） ---
# 部署时提供前端静态资源（Vue.js 应用）。
# 这允许后端作为一个单元提供整个应用程序。

# 检查 'static' 目录是否存在（前端构建应在此处）
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

if os.path.exists(static_dir):
    # 挂载资产（CSS、JS、图像）
    if os.path.exists(os.path.join(static_dir, "assets")):
        app.mount("/assets", StaticFiles(directory=os.path.join(static_dir, "assets")), name="assets")
    
    # Root endpoint for SPA
    @app.get("/")
    async def serve_root():
        return FileResponse(os.path.join(static_dir, "index.html"))

    # SPA（Vue Router）的捕获所有路由
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        # 允许 API 调用通过（应由上述路由处理，但以防万一）
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API endpoint not found")
            
        # 检查特定文件是否存在（例如 favicon.ico, robots.txt）
        file_path = os.path.join(static_dir, full_path)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path)
            
        # 回退到 Vue Router 历史模式的 index.html
        return FileResponse(os.path.join(static_dir, "index.html"))

else:
    # If static files are not present (e.g. backend-only mode or build failed),
    # provide a basic root endpoint to satisfy health checks.
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
