# =============================================================================
# Markdown 导入路由
# 上传 Markdown 文件解析为课程节点树
# =============================================================================

from fastapi import APIRouter, HTTPException, UploadFile, File
from pathlib import Path
from datetime import datetime
import uuid
import sys, os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from dependencies import get_course_document_repository
from models import ImportMarkdownResponse
from markdown_parser import parse_markdown_to_nodes

router = APIRouter(prefix="/api", tags=["import"])


@router.post("/import_markdown", response_model=ImportMarkdownResponse)
async def import_markdown(file: UploadFile = File(...)):
    """将上传的 Markdown 文件解析为课程节点树并持久化存储。"""
    content = await file.read()

    if len(content) == 0:
        raise HTTPException(status_code=400, detail="上传的文件为空")
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件过大，最大支持 20 MB")

    allowed_mime = {"text/markdown", "text/plain", "application/octet-stream"}
    if file.content_type not in allowed_mime:
        raise HTTPException(status_code=415, detail="不支持的文件类型，请上传 .md 或 .txt 文件")

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=422, detail="文件编码不支持，请使用 UTF-8 编码的 Markdown 文件")

    stem = Path(file.filename).stem

    try:
        nodes, course_name = parse_markdown_to_nodes(text, stem)
    except ValueError:
        raise HTTPException(status_code=422, detail="未检测到 Markdown 标题，请确保文件包含至少一个 # 标题")

    if not any(str(node.get("node_content", "")).strip() for node in nodes):
        raise HTTPException(status_code=422, detail="课程至少需要一段可讲授正文，不能只有标题或层级")

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

    await get_course_document_repository().create_imported_course(
        course_id,
        imported_course=course_tree,
    )
    return ImportMarkdownResponse(course_id=course_id, course_name=course_name)
