"""
API 路由
"""

from fastapi import APIRouter

from api import admin, agents, ai, audit, auth, common, course, document, essay_check, feedback, resource, session, user, video


api_router = APIRouter()

# 注册各个模块的路由
api_router.include_router(ai.router, prefix="/ai", tags=["ai"])
api_router.include_router(user.router, prefix="/user", tags=["user"])
api_router.include_router(course.router, prefix="/course", tags=["course"])
api_router.include_router(feedback.router, prefix="/feedback", tags=["feedback"])
api_router.include_router(resource.router, prefix="/resource", tags=["resource"])
api_router.include_router(session.router, prefix="/session", tags=["session"])
api_router.include_router(video.router, prefix="/video", tags=["video"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(essay_check.router, prefix="/essay", tags=["essay"])
api_router.include_router(agents.router, prefix="/agents", tags=["agents"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(audit.router, prefix="/audit", tags=["audit"])
api_router.include_router(document.router, prefix="/document", tags=["document"])
api_router.include_router(common.router, tags=["common"])
