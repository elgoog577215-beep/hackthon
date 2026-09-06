from enum import Enum


class FeatureType(str, Enum):
    """用户操作日志的功能类型枚举。

    - 常驻功能：chat / essay_check / video_analysis / resource / course / feedback /
      text_analysis / ppt_analysis（待上线）
    - 智能体：agent（feature_key 存 agent_id）

    资源生成 (resource) 与视频分析 (video_analysis) 内部还有子类，通过 feature_key 区分：
    - resource: outline / ppt / teaching_plan / question_bank
    - video_analysis: upload / zhiyun
    """
    CHAT = "chat"
    ESSAY_CHECK = "essay_check"
    VIDEO_ANALYSIS = "video_analysis"
    RESOURCE = "resource"
    COURSE = "course"
    FEEDBACK = "feedback"
    AGENT = "agent"
    TEXT_ANALYSIS = "text_analysis"
    PPT_ANALYSIS = "ppt_analysis"


# 旧版按 feature_type 单 key 映射；保留给只看 feature_type 的旧调用方使用。
FEATURE_TYPE_DISPLAY: dict[str, str] = {
    FeatureType.CHAT.value: "智能对话",
    FeatureType.ESSAY_CHECK.value: "论文审查",
    FeatureType.VIDEO_ANALYSIS.value: "视频分析",
    FeatureType.RESOURCE.value: "资源生成",
    FeatureType.COURSE.value: "我的课程",
    FeatureType.FEEDBACK.value: "反馈提交",
    FeatureType.TEXT_ANALYSIS.value: "文本分析",
    FeatureType.PPT_ANALYSIS.value: "PPT 分析",
}


# 精细化标签：以 (feature_type, feature_key) 为 key
# - feature_key=None 表示该类型整体（例如 CHAT 没有子类）
# - resource / video_analysis 必须给出子类 key
FEATURE_DISPLAY: dict[tuple[str, str | None], str] = {
    (FeatureType.RESOURCE.value, "outline"): "大纲生成",
    (FeatureType.RESOURCE.value, "ppt"): "PPT 生成",
    (FeatureType.RESOURCE.value, "teaching_plan"): "教案生成",
    (FeatureType.RESOURCE.value, "question_bank"): "题目生成",
    (FeatureType.COURSE.value, None): "我的课程",
    (FeatureType.CHAT.value, None): "智能对话",
    (FeatureType.VIDEO_ANALYSIS.value, "zhiyun"): "智云课堂分析",
    (FeatureType.VIDEO_ANALYSIS.value, "upload"): "上传视频分析",
    (FeatureType.TEXT_ANALYSIS.value, None): "文本分析",
    (FeatureType.PPT_ANALYSIS.value, None): "PPT 分析",
    (FeatureType.ESSAY_CHECK.value, None): "论文审查",
    (FeatureType.FEEDBACK.value, None): "反馈提交",
}


# 驾驶舱「常驻功能使用排序」要展示的 slot 顺序。
# dashboard_service.list_feature_usage 会按这个列表做零填充，
# 缺数据的 slot 也会以 (0, 0) 出一行，确保 10 类常驻 + 论文审查/反馈 始终在图表里。
RESIDENT_FEATURE_SLOTS: list[tuple[str, str | None]] = [
    (FeatureType.RESOURCE.value, "outline"),
    (FeatureType.RESOURCE.value, "ppt"),
    (FeatureType.RESOURCE.value, "teaching_plan"),
    (FeatureType.RESOURCE.value, "question_bank"),
    (FeatureType.COURSE.value, None),
    (FeatureType.CHAT.value, None),
    (FeatureType.VIDEO_ANALYSIS.value, "zhiyun"),
    (FeatureType.VIDEO_ANALYSIS.value, "upload"),
    (FeatureType.TEXT_ANALYSIS.value, None),
    (FeatureType.PPT_ANALYSIS.value, None),
    (FeatureType.ESSAY_CHECK.value, None),
    (FeatureType.FEEDBACK.value, None),
]


# 待上线功能 slot：前端会给 label 加「（待上线）」后缀，
# dashboard 接口也会在 FeatureUsageItem.pending 上置 True。
PENDING_FEATURE_SLOTS: set[tuple[str, str | None]] = {
    (FeatureType.TEXT_ANALYSIS.value, None),
    (FeatureType.PPT_ANALYSIS.value, None),
}
