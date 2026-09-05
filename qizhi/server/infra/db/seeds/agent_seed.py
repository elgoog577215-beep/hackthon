"""
智能体广场 seed 数据：将 HomeView.vue 中原有的 11 个硬编码 agent 写入数据库。

幂等：只在 agents 表为空时插入，保证重启不会覆盖运营修改/删除。
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from common.utils.logger import get_logger
from infra.db.database import sync_engine
from infra.db.models.agent import Agent


logger = get_logger(__name__)


AGENT_SEED_DATA: list[dict] = [
    {
        "card_key": "sol-simulator",
        "title": "SOL模拟器",
        "description": "模仿 SOL 说话的自动对话机器人（虽然暂时并没有用 SOL 语料库训练），基于 LSTM、Attention 和 GAN。",
        "tags": ["#dialog", "#Mo"],
        "popular": False,
        "badge_bg": "#DEE8FF",
        "badge_fg": "#2F4AA6",
        "icon_path": "M20 2H4c-1.1 0-1.99.9-1.99 2L2 22l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2zm0 14H5.17L4 18.17V4h16v12z",
        "href": "https://mo.zju.edu.cn/explore/5f7856b9878cb398519d2063?type=app",
        "route_to": None,
        "enabled": True,
    },
    {
        "card_key": "poetry-gpt2-lora",
        "title": "基于大模型高效微调的古诗生成模型",
        "description": "基于 GPT-2 和 LoRA 的古诗生成模型，可以根据提示生成相应主题的古诗或藏头诗。",
        "tags": ["#NLP", "#Mo"],
        "popular": False,
        "badge_bg": "#FFE7F2",
        "badge_fg": "#B12462",
        "icon_path": "M4 6h16v2H4V6zm0 5h10v2H4v-2zm0 5h16v2H4v-2zm12-5 4 4-1.4 1.4L14.2 12.4 12 14.6 10.6 13.2 14 9.8Z",
        "href": "https://mo.zju.edu.cn/explore/64b5f596f83507e5f1ab5b7f?type=app",
        "route_to": None,
        "enabled": True,
    },
    {
        "card_key": "object-detection",
        "title": "目标识别",
        "description": "本项目聚焦于目标识别领域。你可以选择人体、车辆等目标对象，上传一张图片，项目将精准识别并框出图片中对应的事物，同时统计出它们的数量。",
        "tags": ["#CV", "#Mo"],
        "popular": False,
        "badge_bg": "#E6FFF6",
        "badge_fg": "#0A7C5A",
        "icon_path": "M5 3h14a2 2 0 0 1 2 2v14h-2v-2H7v2H5V5a2 2 0 0 1 2-2Zm2 12h12V5H7v10Zm2-2V7h2v6H9Zm4 0V9h2v4h-2Zm4 0V8h2v5h-2Z",
        "href": "https://mo.zju.edu.cn/explore/685b45731ab66cd666014c6e?type=app",
        "route_to": None,
        "enabled": True,
    },
    {
        "card_key": "physics-ai-companion",
        "title": "《大学物理》智能伴学系统",
        "description": "通过前沿技术辅助教学，实现交互解题需求，赋能学生思维培养、提升课堂教学效率。",
        "tags": ["#课程", "#伴学"],
        "popular": False,
        "badge_bg": "#E7EEFF",
        "badge_fg": "#4C2E9C",
        "icon_path": "M18 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2zM6 4h12v16H6V4zm2 2v2h8V6H8zm0 4v2h8v-2H8zm0 4v2h5v-2H8z",
        "href": "http://aiassistant-cx.zju.edu.cn/528114",
        "route_to": None,
        "enabled": True,
    },
    {
        "card_key": "organic-chem-digital-star",
        "title": "《有机化学》数智星",
        "description": "通过前沿技术辅助，实现课程基础知识问答，帮助学生进行自主学习，提升课堂教学效率。",
        "tags": ["#课程", "#问答"],
        "popular": False,
        "badge_bg": "#E6FFF6",
        "badge_fg": "#0A7C5A",
        "icon_path": "M20 2H4c-1.1 0-1.99.9-1.99 2L2 22l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2zm0 14H5.17L4 18.17V4h16v12z",
        "href": "http://aiassistant-cx.zju.edu.cn/600680",
        "route_to": None,
        "enabled": True,
    },
    {
        "card_key": "programming-ai-ta",
        "title": "《程序设计》AI助教",
        "description": "智能问答，实现课程基础答疑；代码编程助手，帮助学生完成自主学习，提升课堂教学效率。",
        "tags": ["#课程", "#代码"],
        "popular": False,
        "badge_bg": "#EFE8FF",
        "badge_fg": "#5A2BD6",
        "icon_path": "M8.7 16.6 4.1 12l4.6-4.6L7.3 6 1.3 12l6 6 1.4-1.4Zm6.6 0 4.6-4.6-4.6-4.6L16.7 6l6 6-6 6-1.4-1.4Zm-5.8 2.2L12.9 5h-1.8L7.7 18.8h1.8Z",
        "href": "http://aiassistant-cx.zju.edu.cn/789163",
        "route_to": None,
        "enabled": True,
    },
    {
        "card_key": "analysis",
        "title": "资源分析",
        "description": "对课程视频与教学资源进行结构化分析与可视化呈现。",
        "tags": ["#data", "#video"],
        "popular": False,
        "badge_bg": "#E7EEFF",
        "badge_fg": "#4C2E9C",
        "icon_path": "M5 3h14a2 2 0 0 1 2 2v14h-2v-2H7v2H5V5a2 2 0 0 1 2-2Zm2 12h12V5H7v10Zm2-2V7h2v6H9Zm4 0V9h2v4h-2Zm4 0V8h2v5h-2Z",
        "href": None,
        "route_to": "/",
        "enabled": False,
    },
    {
        "card_key": "outline",
        "title": "大纲生成",
        "description": "基于课程目标与学时结构，自动生成可编辑教学大纲。",
        "tags": ["#outline", "#plan"],
        "popular": False,
        "badge_bg": "#FFE7F2",
        "badge_fg": "#B12462",
        "icon_path": "M4 6h16v2H4V6Zm0 5h10v2H4v-2Zm0 5h16v2H4v-2Zm12-5 4 4-1.4 1.4L14.2 12.4 12 14.6 10.6 13.2 14 9.8Z",
        "href": None,
        "route_to": "/",
        "enabled": False,
    },
    {
        "card_key": "ppt",
        "title": "PPT 生成",
        "description": "将知识点与案例自动组织成课件结构，支持快速导出与调整。",
        "tags": ["#slides", "#content"],
        "popular": True,
        "badge_bg": "#E6FFF6",
        "badge_fg": "#0A7C5A",
        "icon_path": "M6 4h12a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Zm2 4h8v2H8V8Zm0 4h6v2H8v-2Z",
        "href": None,
        "route_to": "/",
        "enabled": False,
    },
    {
        "card_key": "quiz",
        "title": "题目生成",
        "description": "按知识点与难度自动生成题目，并给出解析与参考答案。",
        "tags": ["#quiz", "#assessment"],
        "popular": False,
        "badge_bg": "#FFF2E4",
        "badge_fg": "#9A4A00",
        "icon_path": "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm.1 14.8a1.2 1.2 0 1 1 0-2.4 1.2 1.2 0 0 1 0 2.4ZM12 6a3 3 0 0 1 3 3c0 1.6-1 2.3-1.8 2.9-.6.4-1.2.8-1.2 1.6v.3h-2v-.5c0-1.7 1.1-2.5 2-3.1.6-.4 1-.7 1-1.2a1 1 0 0 0-2 0H8a3 3 0 0 1 4-2.8Z",
        "href": None,
        "route_to": "/",
        "enabled": False,
    },
    {
        "card_key": "workflow",
        "title": "流程编排",
        "description": "将多步骤教学任务编排为可复用流程，提高效率与一致性。",
        "tags": ["#workflow", "#agent"],
        "popular": False,
        "badge_bg": "#EFE8FF",
        "badge_fg": "#5A2BD6",
        "icon_path": "M7 6a3 3 0 1 1 2.8 4H14a3 3 0 1 1 0 2H9.8A3 3 0 1 1 7 6Zm0 2a1 1 0 1 0 0 2 1 1 0 0 0 0-2Zm10 3a1 1 0 1 0 0 2 1 1 0 0 0 0-2ZM7 14a1 1 0 1 0 0 2 1 1 0 0 0 0-2Z",
        "href": None,
        "route_to": "/",
        "enabled": False,
    },
]


def seed_agents() -> None:
    """若 agents 表为空，则批量插入硬编码的 11 个智能体。"""
    with Session(sync_engine) as session:
        count = session.execute(select(func.count(Agent.id))).scalar() or 0
        if count > 0:
            logger.info(f"agents 表已存在 {count} 条数据，跳过 seed")
            return

        logger.info(f"agents 表为空，开始 seed {len(AGENT_SEED_DATA)} 个智能体")
        for index, item in enumerate(AGENT_SEED_DATA):
            session.add(Agent(sort_order=index * 10, **item))
        session.commit()
        logger.info("agents seed 完成")
