from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import StreamingResponse
import sys
import os

# Add current directory to sys.path to ensure local imports work
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from models import (
    Node, Annotation, GenerateCourseRequest, GenerateSubNodesRequest,
    RedefineContentRequest, ExtendContentRequest, AskQuestionRequest,
    UpdateAnnotationRequest, GenerateQuizRequest, LocateNodeRequest,
    AddNodeRequest, SaveAnnotationRequest, UpdateNodeRequest, SummarizeChatRequest
)
    from storage import storage
    from ai_service import ai_service
except ImportError:
    # Fallback for when running from parent directory
    from backend.models import *
    from backend.storage import storage
    from backend.ai_service import ai_service

import uuid
from datetime import datetime
import json

app = FastAPI()

app.add_middleware(
    GZipMiddleware,
    minimum_size=1000
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", 
        "http://localhost:5174", 
        "http://127.0.0.1:5173", 
        "http://127.0.0.1:5174",
        "http://localhost:3700",
        "http://127.0.0.1:3700"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "KnowledgeMap AI API"}

# --- Course Management ---

@app.get("/courses")
def list_courses():
    return storage.list_courses()

@app.get("/courses/{course_id}")
def get_course(course_id: str):
    data = storage.load_course(course_id)
    if not data:
        raise HTTPException(status_code=404, detail="Course not found")
    return data

@app.delete("/courses/{course_id}")
def delete_course(course_id: str):
    storage.delete_course(course_id)
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
    
    storage.save_course(course_id, data)
    return data

# --- Node Operations (Scoped by Course) ---

@app.post("/courses/{course_id}/nodes")
def add_custom_node(course_id: str, req: AddNodeRequest):
    # Expects parent_node_id, node_name
    tree_data = storage.load_course(course_id)
    if not tree_data:
        raise HTTPException(status_code=404, detail="Course not found")
    
    # Determine level
    level = 1
    if req.parent_node_id and req.parent_node_id != "root":
        parent = next((n for n in tree_data.get("nodes", []) if n["node_id"] == req.parent_node_id), None)
        if parent:
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
    storage.save_course(course_id, tree_data)
    return new_node

@app.post("/courses/{course_id}/nodes/{node_id}/subnodes")
async def generate_subnodes(course_id: str, node_id: str, req: GenerateSubNodesRequest):
    tree_data = storage.load_course(course_id)
    if not tree_data:
        raise HTTPException(status_code=404, detail="Course not found")
    
    # Check if subnodes already exist to prevent duplication
    if "nodes" in tree_data:
        existing_children = [n for n in tree_data["nodes"] if n.get("parent_node_id") == node_id]
        if existing_children:
            # If duplicates/content exists, we can return them instead of regenerating
            # Or we can choose to delete them first if 'regeneration' is forced, 
            # but user asked for "deduplication mechanism", implying "don't generate if exists".
            # Returning existing children is safer and faster.
            return existing_children

    course_name = tree_data.get("course_name", "")
    
    # Find current node to get context (summary)
    parent_context = ""
    if "nodes" in tree_data:
        for node in tree_data["nodes"]:
            if node["node_id"] == node_id:
                parent_context = node.get("node_content", "")
                break
    
    new_nodes = await ai_service.generate_sub_nodes(req.node_name, req.node_level, node_id, course_name, parent_context)
    
    if "nodes" in tree_data:
        for node in new_nodes:
            tree_data["nodes"].append(node)
        storage.save_course(course_id, tree_data)
    
    return new_nodes

@app.post("/courses/{course_id}/nodes/{node_id}/redefine_stream")
async def redefine_node_stream(course_id: str, node_id: str, req: RedefineContentRequest):
    # Verify existence
    tree_data = storage.load_course(course_id)
    if not tree_data:
        raise HTTPException(status_code=404, detail="Course not found")
    
    # We will update the node content at the END of the stream or let the client do it via a final save call.
    # But usually, the server should save the final result.
    # Approach: Stream the chunks to the client. The server also aggregates them. 
    # When stream finishes, save to storage.
    
    async def stream_generator():
        full_content = ""
        try:
            async for chunk in ai_service.redefine_node_content(req.node_name, req.original_content, req.user_requirement, req.course_context, req.previous_context):
                full_content += chunk
                yield chunk
        except Exception as e:
            yield f"\n[Error: {e}]"
        
        # After streaming, save to storage
        # Reload to minimize race conditions (though simple file lock is not here)
        current_data = storage.load_course(course_id)
        if "nodes" in current_data:
            for node in current_data["nodes"]:
                if node["node_id"] == node_id:
                    node["node_content"] = ai_service.clean_response_text(full_content)
                    node["node_type"] = "custom"
                    break
            storage.save_course(course_id, current_data)
            
    return StreamingResponse(stream_generator(), media_type="text/plain")

@app.post("/courses/{course_id}/nodes/{node_id}/redefine")
def redefine_node(course_id: str, node_id: str, req: RedefineContentRequest):
    new_content = ai_service.redefine_content(
        req.node_name, 
        req.user_requirement,
        req.original_content,
        req.course_context,
        req.previous_context
    )
    
    tree_data = storage.load_course(course_id)
    if not tree_data:
        raise HTTPException(status_code=404, detail="Course not found")

    found = False
    if "nodes" in tree_data:
        for node in tree_data["nodes"]:
            if node["node_id"] == node_id:
                node["node_content"] = new_content
                node["node_type"] = "custom"
                found = True
                break
    
    if found:
        storage.save_course(course_id, tree_data)
        return {"node_content": new_content}
    raise HTTPException(status_code=404, detail="Node not found")

@app.post("/courses/{course_id}/nodes/{node_id}/quiz")
async def generate_quiz(course_id: str, node_id: str, req: GenerateQuizRequest):
    # Verify node content (or use provided content)
    questions = await ai_service.generate_quiz(req.node_content, req.node_name, req.difficulty, req.style)
    return questions

@app.post("/courses/{course_id}/nodes/{node_id}/extend")
async def extend_node_content(course_id: str, node_id: str, req: ExtendContentRequest):
    # req: node_name, requirement
    content = await ai_service.extend_content(req.node_name, req.user_requirement)
    
    # Save?
    # For now, just return, frontend appends
    return {"content": content}

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
            req.node_id
        ),
        media_type="text/plain"
    )

@app.get("/nodes/{node_id}/annotations")
def get_annotations(node_id: str):
    return storage.get_annotations_by_node(node_id)

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

    storage.save_annotation(data)
    return data

@app.delete("/annotations/{anno_id}")
def delete_annotation(anno_id: str):
    storage.delete_annotation(anno_id)
    return {"status": "success"}

@app.put("/annotations/{anno_id}")
def update_annotation(anno_id: str, req: UpdateAnnotationRequest):
    storage.update_annotation(anno_id, req.content)
    return {"status": "success"}

@app.get("/courses/{course_id}/annotations")
def get_course_annotations(course_id: str):
    # Return all annotations for a course (requires filtering by nodes in that course)
    # 1. Get all nodes in course
    course_data = storage.load_course(course_id)
    if not course_data or "nodes" not in course_data:
        return []
    
    node_ids = set(n["node_id"] for n in course_data["nodes"])
    
    # 2. Get all annotations and filter
    all_annos = storage.load_annotations()
    return [a for a in all_annos if a.get("node_id") in node_ids]


@app.post("/courses/{course_id}/locate")
def locate_node(course_id: str, req: LocateNodeRequest):
    tree_data = storage.load_course(course_id)
    if "nodes" not in tree_data:
         return {}
    return ai_service.locate_node(req.keyword, tree_data["nodes"])

@app.post("/generate_quiz")
async def generate_quiz(req: GenerateQuizRequest):
    return await ai_service.generate_quiz(req.node_content, req.difficulty, req.style, req.user_persona)

@app.post("/summarize_chat")
async def summarize_chat(req: SummarizeChatRequest):
    return await ai_service.summarize_chat(req.history, req.course_context, req.user_persona)

@app.delete("/courses/{course_id}/nodes/{node_id}")
def delete_node(course_id: str, node_id: str):
    tree_data = storage.load_course(course_id)
    if "nodes" in tree_data:
        original_len = len(tree_data["nodes"])
        
        # Find all descendants to delete
        to_delete = {node_id}
        changed = True
        while changed:
            changed = False
            for node in tree_data["nodes"]:
                if node["parent_node_id"] in to_delete and node["node_id"] not in to_delete:
                    to_delete.add(node["node_id"])
                    changed = True
        
        tree_data["nodes"] = [n for n in tree_data["nodes"] if n["node_id"] not in to_delete]
        
        if len(tree_data["nodes"]) < original_len:
            storage.save_course(course_id, tree_data)
            return {"status": "success"}
            
    raise HTTPException(status_code=404, detail="Node not found")

@app.put("/courses/{course_id}/nodes/{node_id}")
def update_node(course_id: str, node_id: str, node_update: UpdateNodeRequest):
    tree_data = storage.load_course(course_id)
    if "nodes" in tree_data:
        for node in tree_data["nodes"]:
            if node["node_id"] == node_id:
                if node_update.node_name is not None:
                    node["node_name"] = node_update.node_name
                if node_update.node_content is not None:
                    node["node_content"] = node_update.node_content
                if node_update.is_read is not None:
                    node["is_read"] = node_update.is_read
                if node_update.quiz_score is not None:
                    node["quiz_score"] = node_update.quiz_score
                storage.save_course(course_id, tree_data)
                return node
    raise HTTPException(status_code=404, detail="Node not found")
