"""
知识呈现二次处理模块。

从超星分析结果中提取并二次加工：
- 知识点分布（树状结构）
- 知识点词云
"""

import re
from collections import Counter
from typing import Any

from common.utils.logger import get_logger

logger = get_logger(__name__)

# 常见中文停用词
_STOP_WORDS = {
    "我们", "可以", "这是", "一个", "需要", "进行", "通过", "然后", "就是",
    "这个", "那个", "什么", "没有", "但是", "所以", "如果", "因为", "还是",
    "不是", "不要", "不能", "现在", "当时", "已经", "开始", "最后", "可能",
    "应该", "得到", "使用", "实现", "提出", "认为", "由于", "对于", "关于",
    "根据", "作为", "为了", "以及", "或者", "而且", "不仅", "并且", "因此",
    "于是", "接着", "后来", "首先", "其次", "例如", "比如", "像是", "好像",
    "这样", "那样", "这里", "那里", "哪里", "怎么", "多少", "非常", "比较",
    "很多", "一些", "所有", "部分", "各种", "不同", "相同", "类似", "相关",
    "主要", "重要", "基本", "根本", "核心", "关键", "总体", "整体", "全面",
    "具体", "详细", "简要", "大致", "大概", "大约", "几乎", "完全", "绝对",
    "相对", "特别", "尤其", "更加", "越发", "逐步", "逐渐", "渐渐", "慢慢",
    "立刻", "马上", "立即", "赶紧", "赶快", "平时", "平常", "通常", "一般",
    "普遍", "普通", "正常", "正规", "标准", "规范", "规则", "规律", "顺序",
    "程序", "流程", "过程", "经过", "经历", "经验", "体验", "感受", "感觉",
    "觉得", "知道", "了解", "理解", "明白", "清楚", "认识", "注意", "关注",
    "关心", "重视", "忽视", "忽略", "建立", "建设", "构建", "组成", "组织",
    "机构", "单位", "部门", "系统", "体系", "制度", "体制", "机制", "结构",
    "框架", "格局", "形式", "方式", "方法", "办法", "措施", "手段", "途径",
    "渠道", "路径", "路线", "方向", "目标", "目的", "打算", "计划", "规划",
    "安排", "部署", "布置", "配置", "设置", "设定", "规定", "确定", "肯定",
    "否定", "拒绝", "接受", "同意", "赞成", "支持", "反对", "抵制", "阻止",
    "阻挡", "阻碍", "妨碍", "影响", "作用", "效果", "结果", "成果", "成绩",
    "成就", "贡献", "付出", "投入", "投资", "收益", "收获", "获得", "取得",
    "达到", "到达", "来到", "出现", "产生", "发生", "引起", "导致", "造成",
    "形成", "变成", "成为", "属于", "位于", "处于", "处在", "一种", "一下",
    "一直", "一样", "一次", "一切", "一方", "一是", "二是", "三是", "第一",
    "第二", "第三", "那么", "这么", "几个", "两位", "三位", "大家", "同学们",
    "同学", "老师", "教师", "课堂", "课程", "教学", "学习", "作业", "内容",
    "问题", "方面", "情况", "时候", "时间", "地方", "人物", "事情", "东西",
    "意义", "价值", "要求", "水平", "能力", "素质", "质量", "数量", "程度",
    "范围", "领域", "行业", "专业", "学科", "知识", "理论", "实践", "实际",
    "现实", "事实", "原理", "原则", "概念", "定义", "含义", "内涵", "外延",
    "特征", "特点", "特色", "特性", "属性", "性质", "状态", "形态", "模式",
    "类型", "种类", "类别", "层次", "等级", "阶段", "时期", "时代", "年度",
    "长期", "短期", "暂时", "永久", "永远", "始终", "一贯", "从来", "向来",
    "日常", "经常", "常常", "时常", "有时", "偶尔", "偶然", "突然", "忽然",
    "一直", "始终", "从来", "平时", "平常", "一般", "通常", "往往", "每每",
    "总是", "老是", "一直", "向来", "一贯", "永远", "始终", "一直", "从来",
}


def extract_knowledge_tree(analyze_data: dict) -> list[dict]:
    """从超星 teach_knowledge 提取知识点树状结构。"""
    teach_knowledge = analyze_data.get("teach_knowledge", [])
    trees: list[dict[str, Any]] = []

    for block in teach_knowledge:
        for node in block.get("file_structure", []):
            trees.append(_clean_knowledge_node(node))

    return trees


def generate_word_cloud(transcript_data: dict, analyze_data: dict) -> list[dict]:
    """
    生成知识点词云。

    策略：
    1. 从 teach_knowledge 的 title 中提取候选核心词
    2. 从转写文本中统计候选词出现频率（权重×2）
    3. 同时提取转写文本中的高频 2-4 字词组作为补充
    4. 合并后取 TOP 50
    """
    teach_knowledge = analyze_data.get("teach_knowledge", [])

    # 收集 teach_knowledge 中的所有 title
    title_words: set[str] = set()
    for block in teach_knowledge:
        for node in block.get("file_structure", []):
            _collect_title_words(node, title_words)

    # 从转写文本中提取所有 2-4 字词组
    transcript = transcript_data.get("transcript", [])
    full_text = "".join(item.get("text", "") for item in transcript)
    all_words = re.findall(r"[一-鿿]{2,4}", full_text)

    # 统计词频
    counter: Counter[str] = Counter()

    # 优先统计 title 词在文本中的出现次数（权重×2）
    for word in title_words:
        count = full_text.count(word)
        if count > 0:
            counter[word] += count * 2

    # 补充统计所有 2-4 字词组
    for word in all_words:
        if word not in _STOP_WORDS and len(word) >= 2:
            counter[word] += 1

    # 取 TOP 50
    top_words = counter.most_common(50)
    return [{"word": word, "weight": weight} for word, weight in top_words]


# ---------------------------------------------------------------------------
# 私有辅助函数
# ---------------------------------------------------------------------------


def _clean_knowledge_node(node: dict) -> dict[str, Any]:
    """清洗单个知识点节点，确保字段完整。"""
    result: dict[str, Any] = {
        "id": node.get("id", ""),
        "title": node.get("title", ""),
        "start_time": node.get("start_time", ""),
        "end_time": node.get("end_time", ""),
    }
    children = node.get("children", [])
    if children:
        result["children"] = [_clean_knowledge_node(c) for c in children]
    return result


def _collect_title_words(node: dict, words: set[str]) -> None:
    """递归收集知识点树中所有 title。"""
    title = node.get("title", "")
    if title:
        words.add(title)
    for child in node.get("children", []):
        _collect_title_words(child, words)
