# =============================================================================
# 图表生成路由
# AI 图表生成、图表类型查询
# =============================================================================

from fastapi import APIRouter, HTTPException
import logging
import sys, os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from models import GenerateDiagramRequest, GenerateDiagramResponse
from ai_service import ai_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/diagram", tags=["diagrams"])

DIAGRAM_TYPES = [
    "flowchart", "sequenceDiagram", "classDiagram", "stateDiagram",
    "erDiagram", "gantt", "pie", "mindmap",
]


@router.post("/generate", response_model=GenerateDiagramResponse)
async def generate_diagram(req: GenerateDiagramRequest):
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


@router.get("/types")
async def get_diagram_types():
    return {
        "types": [
            {"id": "flowchart", "name": "流程图", "description": "展示流程、算法、决策树", "icon": "mdi-sitemap"},
            {"id": "sequenceDiagram", "name": "时序图", "description": "展示对象间的交互顺序", "icon": "mdi-arrow-right-bold-outline"},
            {"id": "classDiagram", "name": "类图", "description": "展示类结构和关系", "icon": "mdi-code-braces"},
            {"id": "stateDiagram", "name": "状态图", "description": "展示状态转换", "icon": "mdi-state-machine"},
            {"id": "erDiagram", "name": "ER图", "description": "展示实体关系", "icon": "mdi-database"},
            {"id": "gantt", "name": "甘特图", "description": "展示项目时间线", "icon": "mdi-chart-timeline"},
            {"id": "pie", "name": "饼图", "description": "展示比例分布", "icon": "mdi-chart-pie"},
            {"id": "mindmap", "name": "思维导图", "description": "展示层级思维结构", "icon": "mdi-graph-outline"},
        ]
    }
