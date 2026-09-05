from agents.assistant.tools.registry import tool_registry


@tool_registry.register(
    description="分析教学视频。",
    loading_message="正在分析教学视频...",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "用户的视频分析需求"},
            "video_id": {"type": "string", "description": "可选，视频 ID"},
            "video_url": {"type": "string", "description": "可选，视频地址"},
        },
        "required": ["query"],
    },
)
async def video_analysis(payload: dict, context) -> str:
    del payload, context
    # 占位工具：先保持"可被 planner 识别"，后续再接入真实视频分析链路
    """分析教学视频。当用户要求分析教学视频、解析教学视频、提取教学视频内容时调用此工具。"""
    return "暂不支持视频分析功能哟～"
