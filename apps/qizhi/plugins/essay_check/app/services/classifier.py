import json
from datetime import date
from typing import Optional

from app.config import (
    DASHSCOPE_API_KEY, LLM_MODEL, LLM_MODEL_SUMMARY,
    ENV, VLLM_API_KEY, VLLM_BASE_URL, VLLM_MODEL,
    SUMMARY_SINGLE_PASS_MAX_PAGES, SUMMARY_BATCH_PAGE_SIZE,
)

from app.logger import get_logger

logger = get_logger(__name__)

# ── ENV helpers ────────────────────────────────────────────────────────────


def use_local_llm() -> bool:
    return True


def _get_vllm_client():
    """Return a configured OpenAI client for vLLM (lazy import)."""
    from openai import OpenAI
    return OpenAI(base_url=VLLM_BASE_URL, api_key=VLLM_API_KEY)


# ── Sampling presets (from verify_vllm.py) ─────────────────────────────────

_NON_THINKING = dict(
    temperature=0.7,
    top_p=0.80,
    presence_penalty=1.5,
    extra_body={
        "top_k": 20,
        "min_p": 0.0,
        "repetition_penalty": 1.0,
        "chat_template_kwargs": {"enable_thinking": False},
    }
)

_WITH_THINKING = dict(
    temperature=1.0,
    top_p=0.95,
    presence_penalty=1.5,
    extra_body={
        "top_k": 20,
        "min_p": 0.0,
        "repetition_penalty": 1.0,
        "chat_template_kwargs": {"enable_thinking": True},
    },
)

# ── Constants ──────────────────────────────────────────────────────────────

# 当前日期，注入所有 prompt 顶部，避免模型误解时间
_DATE_PREFIX = f"当前日期：{date.today().strftime('%Y年%m月%d日')}\n\n"

PAGE_TYPES = [
    "cover", "commitment", "abstract_cn", "abstract_en", "toc",
    "body", "algorithm", "data_table", "conclusion", "references",
    "appendix", "task_sheet", "assessment_form", "expert_review",
    "defense_record", "acknowledgments", "symbols_table", "author_bio",
    "unknown",
]

CLASSIFY_PROMPT = (
    _DATE_PREFIX +
    "你是一名浙江大学本科毕业论文审核助手。请识别这张图片属于论文的哪个部分，并提取页面中与研究实验相关的数据信息。\n\n"
    "可选类型及说明:\n"
    "- cover: 封面页，包含论文题目、作者、导师、专业、学号、学院等信息\n"
    "- commitment: 承诺书/原创性声明页，包含学生签字、日期\n"
    "- abstract_cn: 中文摘要页（含中文关键词）\n"
    "- abstract_en: 英文摘要页（含Abstract标题和英文Keywords）\n"
    "- toc: 目录页，包含章节标题和对应页码\n"
    "- body: 正文页（绪论、文献综述、各章节正文等）\n"
    "- algorithm: 算法描述页，包含算法伪代码、流程图、模型架构说明\n"
    "- data_table: 数据表格/实验结果页，包含实验数据表格、对比结果\n"
    "- conclusion: 结论/总结页\n"
    "- references: 参考文献页\n"
    "- appendix: 附录页\n"
    "- task_sheet: 任务书页面\n"
    "- assessment_form: 考核表页面（指导教师评语、答辩小组评语等）\n"
    "- expert_review: 专家评阅意见表页面\n"
    "- defense_record: 现场答辩记录表页面\n"
    "- acknowledgments: 致谢页，包含对导师、基金资助、协助者等的感谢\n"
    "- symbols_table: 符号/缩略词/术语注释表页\n"
    "- author_bio: 作者简历页，包含教育经历、学术成果等\n"
    "- unknown: 无法归类的页面\n\n"
    "【数据提取要求】\n"
    "请仔细提取本页与**研究实验、调查分析、实证研究、数据统计**相关的数据信息。\n"
    "只提取有研究意义的数据，忽略页码、目录条目、章节编号、格式标记、纯装饰性数字等与研究无关的数字。\n\n"
    "需要提取的内容（如果本页有）：\n"
    "- 实验/研究：实验名称或主题、研究目的/假设、实验对象（人群/样本/材料）、样本量（参与人数、有效样本数等）、实验分组（实验组/对照组等）、实验方法/流程、实验条件、使用的仪器/平台/软件\n"
    "- 调查/问卷：调查名称、调查对象特征（年龄、性别、地区、职业等）、发放数量、有效回收率、抽样方法\n"
    "- 统计结果：均值、标准差、方差、百分比、p值、显著性水平、置信区间、相关系数、回归系数、效应量等具体数值\n"
    "- 表格/图表中的关键数据：表格标题、列名、核心数值、对比数据（如前后对比、组间差异）、趋势结论\n"
    "- 模型/算法：模型名称、超参数配置、训练/测试数据规模、准确率、损失值、F1值等评价指标\n"
    "- 案例/实证：案例对象信息、关键指标、前后变化数据\n\n"
    "提取时务必记录上下文背景：这个数据是做什么的？来自什么实验或研究？涉及什么群体？测量了什么指标？\n"
    "例如不要只写\"样本量120人\"，而要写\"关于XX满意度的问卷调查，面向XX地区大学生，发放问卷150份，有效回收120份，有效回收率80%\"。\n\n"
    "请仅返回JSON格式:\n"
    '{\n'
    '  "page_type": "类型",\n'
    '  "description": "页面内容简述",\n'
    '  "data_info": "本页提取的研究实验相关数据信息（保留原始数据和相关背景描述，若无相关数据则为空字符串）"\n'
    '}\n'
    "不要返回其他内容。"
)

_PAGE_CHECK_RULES = (
    "检查规则：\n"
    "- 你只能看到当前这一张图片，没有前后页面的上下文。\n"
    "- 请仅基于当前页面可见信息进行判断。\n"
    "- 如果基于本页无法得出或确定的结论，视为通过（passed: true），不要标记为有问题。\n"
    "  例如：本面无图表则图表相关检查点直接通过；本面无公式则公式检查点直接通过。\n"
)

_CHECK_PROMPT_TEMPLATES = {

    "cover": (
        _DATE_PREFIX +
        "这是毕业论文的《封面》页面。页面描述: {description}\n\n"
        + _PAGE_CHECK_RULES +
        "请逐项检查以下信息是否完整、规范，返回JSON对象:\n"
        '{{"checks": [{{"check_point": "论文题目完整准确", "passed": true/false, "detail": "说明或本面无此项"}},\n'
        ' {{"check_point": "作者姓名、学号填写完整", "passed": true/false, "detail": "说明或本面无此项"}},\n'
        ' {{"check_point": "指导教师姓名填写完整", "passed": true/false, "detail": "说明或本面无此项"}},\n'
        ' {{"check_point": "专业名称、学院信息填写完整", "passed": true/false, "detail": "说明或本面无此项"}},\n'
        ' {{"check_point": "提交日期/年份填写规范", "passed": true/false, "detail": "说明或本面无此项"}},\n'
        ' {{"check_point": "封面排版格式规范，字体字号统一", "passed": true/false, "detail": "说明"}}]}}'
    ),

    "commitment": (
        _DATE_PREFIX +
        "这是毕业论文的《承诺书/原创性声明》页面。页面描述: {description}\n\n"
        + _PAGE_CHECK_RULES +
        "请仔细检查以下项目，返回JSON对象:\n"
        '{{"checks": [{{"check_point": "学生本人签字完整（手写签名或电子签名）", "passed": true/false, "detail": "说明或本页无此项"}},\n'
        ' {{"check_point": "签署日期填写规范（年月日齐全）", "passed": true/false, "detail": "说明或本页无此项"}},\n'
        ' {{"check_point": "原创性声明正文内容完整无缺失", "passed": true/false, "detail": "说明"}},\n'
        ' {{"check_point": "无敏感词、不当用词", "passed": true/false, "detail": "如有请具体指出"}}]}}'
    ),

    "abstract_cn": (
        _DATE_PREFIX +
        "这是毕业论文的《中文摘要》页面。页面描述: {description}\n\n"
        + _PAGE_CHECK_RULES +
        "请严格按照学位论文摘要撰写规范，逐项检查，返回JSON对象:\n"
        '{{"checks": [{{"check_point": "摘要标题为纯\"摘要\"，无多余文字（如不应有\"摘要（中文）\"，括弧和\"中文\"两字应删除）", "passed": true/false, "detail": "说明"}},\n'
        ' {{"check_point": "摘要包含研究背景/目的（为什么做）", "passed": true/false, "detail": "说明"}},\n'
        ' {{"check_point": "摘要包含研究方法/手段（怎么做）", "passed": true/false, "detail": "说明"}},\n'
        ' {{"check_point": "摘要包含主要结果/发现（得到什么）", "passed": true/false, "detail": "说明"}},\n'
        ' {{"check_point": "摘要包含结论/意义（说明什么）", "passed": true/false, "detail": "说明"}},\n'
        ' {{"check_point": "摘要结构符合三段论(背景-方法-结果-结论)逻辑", "passed": true/false, "detail": "说明"}},\n'
        ' {{"check_point": "摘要包含关键数据指标或量化结果", "passed": true/false, "detail": "说明"}},\n'
        ' {{"check_point": "中文关键词3-5个，准确反映论文主题", "passed": true/false, "detail": "说明"}},\n'
        ' {{"check_point": "关键词格式规范（通常用分号或逗号分隔）", "passed": true/false, "detail": "说明"}},\n'
        ' {{"check_point": "摘要语言规范，无口语化表达", "passed": true/false, "detail": "如有问题请具体指出"}},\n'
        ' {{"check_point": "摘要无错别字、病句、错词", "passed": true/false, "detail": "如有问题请具体列出"}},\n'
        ' {{"check_point": "内容符合社会主义核心价值观，无不当政治表述", "passed": true/false, "detail": "如有请具体指出"}}]}}'
    ),

    "abstract_en": (
        _DATE_PREFIX +
        "这是毕业论文的《英文摘要(Abstract)》页面。页面描述: {description}\n\n"
        + _PAGE_CHECK_RULES +
        "请逐项检查，返回JSON对象:\n"
        '{{"checks": [{{"check_point": "英文Abstract包含研究背景、方法、结果、结论四要素", "passed": true/false, "detail": "如有问题请具体指出"}},\n'
        ' {{"check_point": "英文Keywords完整", "passed": true/false, "detail": "如有问题请具体指出"}},\n'
        ' {{"check_point": "英文语法正确，无明显语法错误", "passed": true/false, "detail": "如有问题请具体指出"}},\n'
        ' {{"check_point": "专业术语翻译准确", "passed": true/false, "detail": "如有问题请具体指出"}},\n'
        ' {{"check_point": "格式规范（Abstract/Keywords标题、分隔符等）", "passed": true/false, "detail": "如有问题请具体指出"}}]}}'
    ),

    "toc": (
        _DATE_PREFIX +
        "这是毕业论文的《目录》页面。页面描述: {description}\n\n"
        + _PAGE_CHECK_RULES +
        "请仔细检查以下项目，返回JSON对象:\n"
        '{{"checks": [{{"check_point": "目录包含绪论/引言章节", "passed": true/false, "detail": "如果该页明显不是第一页目录，则可以不包含"}},\n'
        ' {{"check_point": "目录包含结论/总结章节", "passed": true/false, "detail": "如果该页明显不是最后一页目录，则可以不包含"}},\n'
        ' {{"check_point": "目录包含参考文献条目", "passed": true/false, "detail": "如有问题请具体指出"}},\n'
        ' {{"check_point": "目录层级结构清晰（一级、二级标题层次分明）", "passed": true/false, "detail": "如有问题请具体指出"}},\n'
        ' {{"check_point": "目录页码依次递增，无跳号或倒序（仅基于当前可见页码判断，不确定的视为通过）", "passed": true/false, "detail": "说明"}},\n'
        ' {{"check_point": "目录格式规范（缩进对齐、编号连续）", "passed": true/false, "detail": "如有问题请具体指出"}},\n'
        ' {{"check_point": "摘要、Abstract等前置部分在目录中正确列出", "passed": true/false, "detail": "说明或无法确定的视为通过"}}]}}'
    ),

    "body": (
        _DATE_PREFIX +
        "这是毕业论文的《正文》页面。页面描述: {description}\n\n"
        + _PAGE_CHECK_RULES +
        "作为国家级教学名师和博士生导师，请以严格学术标准检查以下方面:\n"
        "【文字规范】检查错别字、病句、错词，语言规范专业无口语化，语句通顺无语法错误。\n"
        "【数据与单位】量词、单位使用规范（国际单位制），数字、数据表述合理，无明显捏造或夸大嫌疑。\n"
        "【引文与注释】引文标注符合 GB/T 7714（顺序编码制：序号置于方括号，多文献用逗号/短横线连接；著者-出版年制：姓氏+出版年，中国作者加\"等\"、欧美作者加\"et al.\"）。注释数量适度，优先脚注形式。\n"
        "【图表公式】表名在表上方、图名在图下方。图表引用，要先在正文引用，后出现图表。图表具有自明性。公式书写规范，编号右端对齐。\n"
        "【格式统一】段落格式统一（行间距、字号、缩进一致），各级标题格式统一（编号顶格排，与标题间空1字间隙）。\n"
        "【内容质量】论证缜密逻辑严密，无矛盾表述。引言页应包含研究背景、前人工作综述、研究目的与方法。结论页应概括核心观点并指出局限与未来方向。\n"
        "【思想政治】内容符合社会主义核心价值观，无敏感词、不当政治表述。\n\n"
        "最终结果请返回JSON对象，包含以下检查点:\n"
        '{{"checks": [{{"check_point": "文字规范（无错别字、病句、口语化表达）", "passed": true/false, "detail": "如有问题请具体列出"}},\n'
        ' {{"check_point": "数据与单位使用规范", "passed": true/false, "detail": "如有问题请具体指出"}},\n'
        ' {{"check_point": "引文与注释格式规范（GB/T 7714）", "passed": true/false, "detail": "如有问题请具体指出"}},\n'
        ' {{"check_point": "图表公式标注规范", "passed": true/false, "detail": "本面无图表公式的视为通过"}},\n'
        ' {{"check_point": "格式统一（段落、标题、缩进、字号一致）", "passed": true/false, "detail": "如有问题请具体指出"}},\n'
        ' {{"check_point": "内容逻辑严密、论述合理", "passed": true/false, "detail": "说明或无法确定的视为通过"}},\n'
        ' {{"check_point": "思想政治合规，无敏感词或不当表述", "passed": true/false, "detail": "如有请具体指出"}}]}}'
    ),

    "algorithm": (
        _DATE_PREFIX +
        "这是毕业论文的《算法描述》页面。页面描述: {description}\n\n"
        + _PAGE_CHECK_RULES +
        "请从学术规范角度检查，返回JSON对象:\n"
        '{{"checks": [{{"check_point": "算法伪代码/流程图格式规范", "passed": true/false, "detail": "说明"}},\n'
        ' {{"check_point": "算法步骤描述清晰、完整", "passed": true/false, "detail": "说明"}},\n'
        ' {{"check_point": "算法输入输出定义明确", "passed": true/false, "detail": "说明"}},\n'
        ' {{"check_point": "算法符号/变量命名统一规范", "passed": true/false, "detail": "说明"}},\n'
        ' {{"check_point": "算法逻辑正确，无明显错误", "passed": true/false, "detail": "说明或无法确定的视为通过"}},\n'
        ' {{"check_point": "如有公式，公式编号规范", "passed": true/false, "detail": "本面无公式的视为通过"}}]}}'
    ),

    "data_table": (
        _DATE_PREFIX +
        "这是毕业论文的《数据表格/实验结果》页面。页面描述: {description}\n\n"
        + _PAGE_CHECK_RULES +
        "请仔细检查数据的合理性和规范性，返回JSON对象:\n"
        '{{"checks": [{{"check_point": "表格有编号和标题（表名在表上方）", "passed": true/false, "detail": "说明"}},\n'
        ' {{"check_point": "表格列名、行名标注清晰完整", "passed": true/false, "detail": "说明"}},\n'
        ' {{"check_point": "数据单位标注规范", "passed": true/false, "detail": "说明"}},\n'
        ' {{"check_point": "数据无明显造假嫌疑（如精确度过高、数值过于完美等）", "passed": true/false, "detail": "说明或无法确定的视为通过"}},\n'
        ' {{"check_point": "本面内对比数据合理，无明显矛盾", "passed": true/false, "detail": "说明或无法确定的视为通过"}},\n'
        ' {{"check_point": "图表中使用的颜色/符号/标记区分清晰", "passed": true/false, "detail": "说明或本面无此项的视为通过"}}]}}'
    ),

    "conclusion": (
        _DATE_PREFIX +
        "这是毕业论文的《结论》页面。页面描述: {description}\n\n"
        + _PAGE_CHECK_RULES +
        "请检查，返回JSON对象:\n"
        '{{"checks": [{{"check_point": "结论完整概括了研究的主要发现", "passed": true/false, "detail": "说明或无法确定的视为通过"}},\n'
        ' {{"check_point": "结论包含研究的理论或实践意义", "passed": true/false, "detail": "说明或无法确定的视为通过"}},\n'
        ' {{"check_point": "结论指出了研究的局限性或未来方向", "passed": true/false, "detail": "说明或无法确定的视为通过"}},\n'
        ' {{"check_point": "结论语言规范、无夸大或浮夸表述", "passed": true/false, "detail": "说明"}},\n'
        ' {{"check_point": "结论无错别字、病句", "passed": true/false, "detail": "如有请具体列出"}},\n'
        ' {{"check_point": "结论内容符合学术规范和社会主义核心价值观", "passed": true/false, "detail": "说明或无法确定的视为通过"}}]}}'
    ),

    "references": (
        _DATE_PREFIX +
        "这是毕业论文的《参考文献》页面。页面描述: {description}\n\n"
        + _PAGE_CHECK_RULES +
        "请严格按照 GB/T 7714（信息与文献 参考文献著录规则）检查，返回JSON对象。\n\n"
        "1. 引文标注体系全文统一（顺序编码制或著者-出版年制，不混用）。\n"
        "2. 顺序编码制：序号用方括号[1]、[2]，按正文出现顺序连续编码；\n"
        "   著者-出版年制：文献按文种集中，再按责任者字顺和出版年排列。\n"
        '3. 责任者著录：姓在前名在后，不超3人全著录，超3人著录前3人后加"等"或相应外文词。\n'
        "4. 文献类型标识正确（M=图书, J=期刊, D=学位论文, C=会议录, R=报告, S=标准, P=专利, EB=电子资源等），\n"
        "   电子资源同时著录载体标识（如[EB/OL]、[J/OL]）及引用日期和获取路径。\n"
        "5. 出版信息著录顺序：出版地：出版者，出版年；期刊析出文献：刊名，年，卷(期)：页码。\n"
        "6. 各文献必备著录项目完整（责任者、题名、出版信息等），无关键信息缺失。\n"
        '7. 著录用标点符号规范（"."用于题名前，":"用于出版者/页码前，","用于责任者/出版年前，"//"用于析出文献出处前）。\n'
        "8. 页码用阿拉伯数字，西文大写符合该文种习惯，不著录并列题名。\n\n"
        '{{"checks": [{{"check_point": "引文标注体系统一，正文引用格式规范", "passed": true/false, "detail": "说明"}},\n'
        ' {{"check_point": "责任者著录、文献类型标识规范", "passed": true/false, "detail": "说明"}},\n'
        ' {{"check_point": "各文献著录项目完整（出版信息、年卷期页码等），无关键信息缺失", "passed": true/false, "detail": "说明"}},\n'
        ' {{"check_point": "著录用标点符号、格式排版规范", "passed": true/false, "detail": "说明"}},\n'
        ' {{"check_point": "文献排列顺序正确，无明显虚假文献特征", "passed": true/false, "detail": "说明"}}]}}'
    ),

    "task_sheet": (
        _DATE_PREFIX +
        "这是毕业论文的《任务书》页面。页面描述: {description}\n\n"
        + _PAGE_CHECK_RULES +
        "请逐项检查，返回JSON对象:\n"
        '{{"checks": [{{"check_point": "任务下达具体、详实、目标明确", "passed": true/false, "detail": "说明或无法确定的视为通过"}},\n'
        ' {{"check_point": "起讫日期规范", "passed": true/false, "detail": "说明或本页无此项的视为通过"}},\n'
        ' {{"check_point": "指导教师签字填写完整", "passed": true/false, "detail": "说明或本页无此项的视为通过"}},\n'
        ' {{"check_point": "系/研究所审核意见、负责人签字完整", "passed": true/false, "detail": "说明或本页无此项的视为通过"}},\n'
        ' {{"check_point": "系/研究所审核意见日期填写规范", "passed": true/false, "detail": "说明或本页无此项的视为通过"}},\n'
        ' {{"check_point": "任务书内容无格式错误和错别字", "passed": true/false, "detail": "说明"}}]}}'
    ),

    "assessment_form": (
        _DATE_PREFIX +
        "这是毕业论文的《考核表》页面。页面描述: {description}\n\n"
        + _PAGE_CHECK_RULES +
        "请逐项检查，返回JSON对象:\n"
        '{{"checks": [{{"check_point": "指导教师评语详细、有针对性", "passed": true/false, "detail": "说明或本页无此项的视为通过"}},\n'
        ' {{"check_point": "指导教师签字完整", "passed": true/false, "detail": "说明或本页无此项的视为通过"}},\n'
        ' {{"check_point": "指导教师评价时间填写规范", "passed": true/false, "detail": "说明或本页无此项的视为通过"}},\n'
        ' {{"check_point": "答辩小组答辩评语详细", "passed": true/false, "detail": "说明或本页无此项的视为通过"}},\n'
        ' {{"check_point": "答辩打分填写规范", "passed": true/false, "detail": "说明或本页无此项的视为通过"}},\n'
        ' {{"check_point": "开题分值填写完整", "passed": true/false, "detail": "说明或本页无此项的视为通过"}},\n'
        ' {{"check_point": "答辩小组负责人（非指导教师）签字完整", "passed": true/false, "detail": "说明或本页无此项的视为通过"}},\n'
        ' {{"check_point": "答辩考核时间填写规范", "passed": true/false, "detail": "说明或本页无此项的视为通过"}}]}}'
    ),

    "expert_review": (
        _DATE_PREFIX +
        "这是毕业论文的《专家评阅意见表》页面。页面描述: {description}\n\n"
        + _PAGE_CHECK_RULES +
        "请逐项检查，返回JSON对象:\n"
        '{{"checks": [{{"check_point": "专家评阅表头填写完整（论文题目、作者等）", "passed": true/false, "detail": "说明或本页无此项的视为通过"}},\n'
        ' {{"check_point": "评阅意见明确、有针对性", "passed": true/false, "detail": "说明或本页无此项的视为通过"}},\n'
        ' {{"check_point": "专家信息填写完整", "passed": true/false, "detail": "说明或本页无此项的视为通过"}},\n'
        ' {{"check_point": "专家签字完整", "passed": true/false, "detail": "说明或本页无此项的视为通过"}},\n'
        ' {{"check_point": "评阅日期填写规范", "passed": true/false, "detail": "说明或本页无此项的视为通过"}}]}}'
    ),

    "defense_record": (
        _DATE_PREFIX +
        "这是毕业论文的《现场答辩记录表》页面。页面描述: {description}\n\n"
        + _PAGE_CHECK_RULES +
        "请逐项检查，返回JSON对象:\n"
        '{{"checks": [{{"check_point": "答辩记录详尽，包含问答要点", "passed": true/false, "detail": "说明或本页无此项的视为通过"}},\n'
        ' {{"check_point": "相关人员签名完整", "passed": true/false, "detail": "说明或本页无此项的视为通过"}},\n'
        ' {{"check_point": "记录时间填写规范", "passed": true/false, "detail": "说明或本页无此项的视为通过"}},\n'
        ' {{"check_point": "答辩成绩/结论填写规范", "passed": true/false, "detail": "说明或本页无此项的视为通过"}}]}}'
    ),

    "acknowledgments": (
        _DATE_PREFIX +
        "这是毕业论文的《致谢》页面。页面描述: {description}\n\n"
        + _PAGE_CHECK_RULES +
        "请逐项检查，返回JSON对象:\n"
        '{{"checks": [{{"check_point": "致谢内容得体、规范，符合学术礼仪", "passed": true/false, "detail": "说明"}},\n'
        ' {{"check_point": "如含基金/资助致谢，资助项目名称、编号完整", "passed": true/false, "detail": "本面无基金致谢的视为通过"}},\n'
        ' {{"check_point": "致谢中无敏感词、不当用词", "passed": true/false, "detail": "如有请具体指出"}},\n'
        ' {{"check_point": "致谢内容符合社会主义核心价值观，无不当表述", "passed": true/false, "detail": "如有请具体指出"}}]}}'
    ),

    "symbols_table": (
        _DATE_PREFIX +
        "这是毕业论文的《符号、标志、缩略词、首字母缩写、计量单位、术语等注释表》页面。页面描述: {description}\n\n"
        + _PAGE_CHECK_RULES +
        "请逐项检查，返回JSON对象:\n"
        '{{"checks": [{{"check_point": "符号注释表有明确的标题", "passed": true/false, "detail": "说明"}},\n'
        ' {{"check_point": "符号、缩略词与正文中的使用一致", "passed": true/false, "detail": "说明或无法确定的视为通过"}},\n'
        ' {{"check_point": "计量单位使用国家法定计量单位", "passed": true/false, "detail": "说明"}},\n'
        ' {{"check_point": "符号、术语的书写格式规范统一", "passed": true/false, "detail": "说明"}}]}}'
    ),

    "appendix": (
        _DATE_PREFIX +
        "这是毕业论文的《附录》页面。页面描述: {description}\n\n"
        + _PAGE_CHECK_RULES +
        "请检查，返回JSON对象:\n"
        '{{"checks": [{{"check_point": "附录有编号和标题", "passed": true/false, "detail": "说明"}},\n'
        ' {{"check_point": "附录格式规范，与正文区分清楚", "passed": true/false, "detail": "说明"}},\n'
        ' {{"check_point": "附录内容完整，标注清楚", "passed": true/false, "detail": "说明或无法确定的视为通过"}},\n'
        ' {{"check_point": "附录中代码、数据、图表格式规范", "passed": true/false, "detail": "本面无相关内容的视为通过"}}]}}'
    ),

    "author_bio": (
        _DATE_PREFIX +
        "这是毕业论文的《作者简历/作者信息》页面。页面描述: {description}\n\n"
        + _PAGE_CHECK_RULES +
        "请检查，返回JSON对象:\n"
        '{{"checks": [{{"check_point": "作者教育经历完整（学校、专业、时间）", "passed": true/false, "detail": "说明或本页无此项的视为通过"}},\n'
        ' {{"check_point": "攻读学位期间发表的学术论文及成果已列出", "passed": true/false, "detail": "说明或本页无此项的视为通过"}},\n'
        ' {{"check_point": "参与项目、获奖情况填写完整", "passed": true/false, "detail": "说明或本页无此项的视为通过"}},\n'
        ' {{"check_point": "格式规范、排版整齐", "passed": true/false, "detail": "说明或无法确定的视为通过"}}]}}'
    ),

    "unknown": (
        _DATE_PREFIX +
        "这是毕业论文中无法识别类型的页面。页面描述: {description}\n\n"
        + _PAGE_CHECK_RULES +
        "请检查该页面的整体格式是否符合浙江大学本科毕业论文的一般规范要求，返回JSON对象:\n"
        '{{"checks": [{{"check_point": "页面格式规范，符合论文一般要求", "passed": true/false, "detail": "说明"}},\n'
        ' {{"check_point": "无明显错别字、病句", "passed": true/false, "detail": "如有请指出"}},\n'
        ' {{"check_point": "内容符合社会主义核心价值观，无不当表述", "passed": true/false, "detail": "如有请指出"}}]}}'
    ),
}


# ── classify_page ──────────────────────────────────────────────────────────


def classify_page(image_url: str) -> Optional[dict]:
    """Call LLM to classify a page. Returns dict with page_type and description."""
    try:
        logger.info(f"Classifying page with image: {image_url[:20]}...")
        if use_local_llm():
            return _classify_vllm(image_url)
        return _classify_dashscope(image_url)
    except Exception as e:
        logger.error(f"LLM classify error: {e}", exc_info=True)
    return None


def _classify_dashscope(image_url: str) -> Optional[dict]:
    from dashscope import MultiModalConversation
    response = MultiModalConversation.call(
        model=LLM_MODEL,
        messages=[{
            "role": "system",
            "content": [{"text": "你是论文审核助手，只返回JSON，不要返回其他内容。"}]
        }, {
            "role": "user",
            "content": [
                {"image": image_url},
                {"text": CLASSIFY_PROMPT}
            ]
        }],
        api_key=DASHSCOPE_API_KEY,
        result_format="message",
        response_format={"type": "json_object"},
        enable_thinking=False,
    )
    if response.status_code == 200:
        text = response.output.choices[0].message.content[0]["text"]
        return json.loads(_extract_json(text))
    logger.error(f"Qwen-VL classify failed: {response.code} {response.message}")
    return None


def _classify_vllm(image_url: str) -> Optional[dict]:
    client = _get_vllm_client()
    resp = client.chat.completions.create(
        model=VLLM_MODEL,
        messages=[{
            "role": "system",
            "content": "你是论文审核助手，只返回JSON，不要返回其他内容。"
        }, {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": image_url}},
                {"type": "text", "text": CLASSIFY_PROMPT}
            ]
        }],
        max_tokens=81920,
        response_format={"type": "json_object"},
        **_NON_THINKING,
    )
    return json.loads(_extract_json(resp.choices[0].message.content))


# ── check_page ─────────────────────────────────────────────────────────────


def check_page(image_url: str, page_type: str, description: str) -> Optional[list[dict]]:
    """Call LLM to check a page against its type-specific rules.
    Returns list of {check_point, passed, detail}."""
    prompt = _build_check_prompt(page_type, description)
    if not prompt:
        return []
    try:
        if use_local_llm():
            return _check_vllm(image_url, prompt)
        return _check_dashscope(image_url, prompt)
    except Exception as e:
        logger.error(f"LLM check error: {e}", exc_info=True)
    return None


def _check_vllm(image_url: str, prompt: str) -> Optional[list[dict]]:
    client = _get_vllm_client()
    resp = client.chat.completions.create(
        model=VLLM_MODEL,
        messages=[{
            "role": "system",
            "content": (
                _DATE_PREFIX +
                "你是浙江大学本科毕业论文审核专家，具有国家级教学名师的学术水平。"
                "你只能看到当前这一张图片，没有前后页面的上下文。"
                "请仅基于当前页面可见信息逐项检查。"
                "重要规则：如果基于本页无法得出或确定的结论，视为通过(passed: true)，不要标记为有问题。"
                "返回JSON对象格式：{\"checks\": [{\"check_point\": \"...\", \"passed\": true/false, \"detail\": \"...\"}]}"
            )
        }, {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": image_url}},
                {"type": "text", "text": prompt}
            ]
        }],
        max_tokens=81920,
        response_format={"type": "json_object"},
        **_NON_THINKING,
    )
    result = json.loads(_extract_json(resp.choices[0].message.content))

    # 提取 checks 数组
    if isinstance(result, dict) and "checks" in result:
        return result["checks"]
    # 兼容旧格式
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        return [result]

    logger.info("LLM check response: %s", resp.choices[0].message.content)
    return None


def _check_dashscope(image_url: str, prompt: str) -> Optional[list[dict]]:
    from dashscope import MultiModalConversation
    response = MultiModalConversation.call(
        model=LLM_MODEL,
        messages=[{
            "role": "system",
            "content": [{"text": (
                _DATE_PREFIX +
                "你是浙江大学本科毕业论文审核专家，具有国家级教学名师的学术水平。"
                "你只能看到当前这一张图片，没有前后页面的上下文。"
                "请仅基于当前页面可见信息逐项检查。"
                "重要规则：如果基于本页无法得出或确定的结论，视为通过（passed: true），不要标记为有问题。"
                "返回JSON对象格式：{\"checks\": [{\"check_point\": \"...\", \"passed\": true/false, \"detail\": \"...\"}]}"
            )}]
        }, {
            "role": "user",
            "content": [
                {"image": image_url},
                {"text": prompt}
            ]
        }],
        api_key=DASHSCOPE_API_KEY,
        result_format="message",
        response_format={"type": "json_object"},
        enable_thinking=False,
    )
    if response.status_code == 200:
        text = response.output.choices[0].message.content[0]["text"]
        result = json.loads(_extract_json(text))

        # 提取 checks 数组
        if isinstance(result, dict) and "checks" in result:
            return result["checks"]
        # 兼容旧格式
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return [result]

        logger.error(f"check_page returned unexpected format: {result}")
    logger.error(f"Qwen-VL check failed: {response.code} {response.message}")
    return None

# ── generate_summary ───────────────────────────────────────────────────────

_CHECK_DOMAINS_INSTRUCTION = (
    "请按照以下检查域逐项给出判断：\n\n"
    "=== 检查域列表 ===\n\n"
    "1. 【规范管理】\n"
    "   - 是否有毕业论文实施细则/任务书\n"
    "   - 任务书是否详实、起讫日期是否规范\n"
    "   - 各类签字、审核意见是否完整\n\n"
    "2. 【前置部分】\n"
    "   - 封面信息是否完整（题目、作者、导师、专业等）\n"
    "   - 承诺书签字/日期是否完整\n"
    "   - 中文摘要是否包含背景、方法、结果、结论四要素\n"
    "   - 中文摘要是否符合三段论(背景-方法-结果-结论)结构\n"
    "   - 英文摘要是否包含基本要素\n\n"
    "3. 【主体部分-内容质量】\n"
    "   - 绪论/正文/结论是否完整\n"
    "   - 算法描述是否正确、清晰（如有算法页）\n"
    "   - 实验数据是否合理（如有数据页）\n\n"
    "4. 【主体部分-文字规范】\n"
    "   - 错别字、病句、错词情况\n"
    "   - 语法错误、语句不通顺问题\n"
    "   - 口语化现象\n"
    "   - 语言不够专业的地方\n"
    "   - 数字夸大、浮夸之处\n\n"
    "5. 【主体部分-数据与图表】\n"
    "   - 数据合理性、是否存在捏造数据嫌疑\n"
    "   - 量化单位使用是否规范\n"
    "   - 图表标注是否规范（表名在表上、图名在图下）\n\n"
    "6. 【主体部分-格式统一性】\n"
    "   - 根据各页反馈判断格式一致性\n\n"
    "7. 【引文与参考文献】\n"
    "   - 参考文献格式是否统一\n"
    "   - 文献信息是否完整\n\n"
    "8. 【思想政治与价值观】\n"
    "   - 是否存在敏感词或不当用词\n"
    "   - 是否存在不当政治表述\n"
    "   - 内容是否符合社会主义核心价值观\n\n"
    "9. 【考核材料】\n"
    "   - 指导教师评语、签字、时间\n"
    "   - 答辩小组评语、打分、签字、时间\n"
    "   - 专家评阅意见\n"
    "   - 现场答辩记录\n"
)

_FINAL_SUMMARY_JSON_SCHEMA = (
    "请返回以下JSON格式，不要返回其他内容:\n"
    "{\n"
    '  "overall_score": "合格/需修改/不合格",\n'
    '  "summary": "总体评价文字（200-500字，从国家级教学名师角度给出专业、具体的评价）",\n'
    '  "check_domains": [\n'
    '    {"domain": "检查域名称", "check_points": [{"name": "检查点", "passed": true/false, "detail": "详细说明"}]}\n'
    "  ],\n"
    '  "reference_issues": ["参考文献格式不统一", "部分文献缺少出版年份"],\n'
    '  "typos_and_errors": ["第X页：错别字\'XX\'应为\'YY\'", "第X页：病句\'...\'"],\n'
    '  "data_issues": ["第X页数据XX可疑，原因：..."],\n'
    '  "format_issues": ["第X页行间距不统一", "第X页标题格式不一致"],\n'
    '  "political_issues": ["第X页表述不当：..."],\n'
    '  "recommendations": ["建议1", "建议2"]\n'
    "}\n"
)

_BATCH_SUMMARY_JSON_SCHEMA = (
    "请返回以下JSON格式，不要返回其他内容:\n"
    "{\n"
    '  "page_range": "本批次页码范围",\n'
    '  "batch_summary": "本批次简要评价（100-200字）",\n'
    '  "check_domains": [\n'
    '    {"domain": "检查域名称", "check_points": [{"name": "检查点", "passed": true/false, "detail": "详细说明"}]}\n'
    "  ],\n"
    '  "reference_issues": [],\n'
    '  "typos_and_errors": [],\n'
    '  "data_issues": [],\n'
    '  "format_issues": [],\n'
    '  "political_issues": [],\n'
    '  "recommendations": []\n'
    "}\n"
)


def compact_page_for_summary(page: dict) -> dict:
    """压缩单页数据，汇总时只保留描述与未通过的检查项。"""
    check_results = page.get("check_results") or []
    failed_checks = [
        c for c in check_results
        if isinstance(c, dict) and not c.get("passed", True)
    ]
    extracted = page.get("extracted_content") or {}
    description = extracted.get("description", "") if isinstance(extracted, dict) else ""
    return {
        "page_number": page.get("page_number"),
        "page_type": page.get("page_type"),
        "status": page.get("status"),
        "description": description,
        "failed_checks": failed_checks,
        "error_message": page.get("error_message"),
    }


def compact_pages_for_summary(pages_data: list[dict]) -> list[dict]:
    return [compact_page_for_summary(p) for p in pages_data]


def _pages_to_json(pages: list[dict]) -> str:
    return json.dumps(pages, ensure_ascii=False, separators=(",", ":"))


def _call_summary_llm(prompt: str) -> Optional[dict]:
    """调用汇总 LLM，返回解析后的 dict。"""
    try:
        if use_local_llm():
            raw = _summary_vllm_raw(prompt)
        else:
            raw = _summary_dashscope_raw(prompt)
        if raw is None:
            return None
        return json.loads(_extract_json(raw))
    except Exception as e:
        logger.error(f"LLM summary parse error: {e}", exc_info=True)
        return None


def generate_summary(all_pages_data: list[dict]) -> Optional[dict]:
    """根据各页检查结果生成汇总报告。长论文自动分批汇总再二次合并。"""
    compact = compact_pages_for_summary(all_pages_data)
    if len(compact) <= SUMMARY_SINGLE_PASS_MAX_PAGES:
        logger.info(f"Summary single-pass for {len(compact)} pages")
        return generate_summary_single(compact)

    batches = [
        compact[i:i + SUMMARY_BATCH_PAGE_SIZE]
        for i in range(0, len(compact), SUMMARY_BATCH_PAGE_SIZE)
    ]
    logger.info(
        f"Summary batched: {len(compact)} pages -> {len(batches)} batches "
        f"(batch_size={SUMMARY_BATCH_PAGE_SIZE})"
    )
    batch_results: list[dict] = []
    for idx, batch in enumerate(batches):
        page_range = f"{batch[0]['page_number']}-{batch[-1]['page_number']}"
        result = generate_batch_summary(batch, idx + 1, len(batches), page_range)
        if not result:
            logger.error(f"Batch summary failed: batch {idx + 1}/{len(batches)} pages {page_range}")
            return None
        batch_results.append(result)
        logger.info(f"Batch summary OK: {idx + 1}/{len(batches)} pages {page_range}")

    return merge_batch_summaries(batch_results, len(compact))


def generate_summary_single(compact_pages: list[dict]) -> Optional[dict]:
    """单次 LLM 调用生成完整汇总报告。"""
    pages_info = _pages_to_json(compact_pages)
    prompt = (
        _DATE_PREFIX +
        "你是一名国家级教学名师，985高校人工智能与设计学专业教授、博士生导师。\n"
        "请对以下浙江大学本科毕业论文的各页检查结果进行综合分析，给出详细的审查报告。\n\n"
        "注意：以下数据是逐页检查的汇总结果，你只能看到各页的检查结果文本，没有原始图片。\n"
        "请基于已有的检查结果进行分析，不要做无根据的推测。\n"
        "每页仅列出未通过的检查项（failed_checks）；若某页 failed_checks 为空表示该页检查均通过。\n\n"
        + _CHECK_DOMAINS_INSTRUCTION +
        "=== 各页检查结果 ===\n"
        f"{pages_info}\n\n"
        "=== 输出要求 ===\n\n"
        + _FINAL_SUMMARY_JSON_SCHEMA
    )
    result = _call_summary_llm(prompt)
    return result if isinstance(result, dict) else None


def generate_batch_summary(
    batch_pages: list[dict],
    batch_index: int,
    total_batches: int,
    page_range: str,
) -> Optional[dict]:
    """对一批页面生成局部汇总（不含 overall_score）。"""
    pages_info = _pages_to_json(batch_pages)
    prompt = (
        _DATE_PREFIX +
        "你是一名国家级教学名师，985高校人工智能与设计学专业教授、博士生导师。\n"
        f"这是整篇浙江大学本科毕业论文的第 {batch_index}/{total_batches} 批检查结果"
        f"（页码 {page_range}）。请仅基于本批次页面进行分析，不要推测其他批次内容。\n\n"
        "每页仅列出未通过的检查项（failed_checks）；若某页 failed_checks 为空表示该页检查均通过。\n"
        "若本批次未涉及某检查域（如无参考文献页），该域相关检查点可视为通过或注明「本批次无此项」。\n\n"
        + _CHECK_DOMAINS_INSTRUCTION +
        f"=== 本批次（第 {batch_index}/{total_batches} 批，页 {page_range}）检查结果 ===\n"
        f"{pages_info}\n\n"
        "=== 输出要求 ===\n\n"
        + _BATCH_SUMMARY_JSON_SCHEMA
    )
    result = _call_summary_llm(prompt)
    if isinstance(result, dict):
        result.setdefault("page_range", page_range)
        return result
    return None


def merge_batch_summaries(batch_results: list[dict], total_pages: int) -> Optional[dict]:
    """将各批次局部汇总合并为最终报告。"""
    batches_info = _pages_to_json(batch_results)
    prompt = (
        _DATE_PREFIX +
        "你是一名国家级教学名师，985高校人工智能与设计学专业教授、博士生导师。\n"
        f"以下是一篇共 {total_pages} 页的浙江大学本科毕业论文，按批次生成的局部审查汇总（共 {len(batch_results)} 批）。\n"
        "请合并各批次结论，去重同类问题，给出整篇论文的最终审查报告。\n\n"
        "合并原则：\n"
        "- overall_score 按全篇最严重问题综合判定（合格/需修改/不合格）\n"
        "- 各批次 typos_and_errors、reference_issues 等列表合并去重，保留页码\n"
        "- check_domains 按九大检查域合并，同一检查点任一批次未通过则全篇未通过\n"
        "- summary 写 200-500 字全篇总评，不要只复述某一批\n\n"
        "=== 各批次局部汇总 ===\n"
        f"{batches_info}\n\n"
        "=== 输出要求 ===\n\n"
        + _FINAL_SUMMARY_JSON_SCHEMA
    )
    result = _call_summary_llm(prompt)
    return result if isinstance(result, dict) else None


def _summary_dashscope_raw(prompt: str) -> Optional[str]:
    from dashscope import MultiModalConversation
    response = MultiModalConversation.call(
        model=LLM_MODEL_SUMMARY,
        messages=[{
            "role": "user",
            "content": [{"text": prompt}]
        }],
        api_key=DASHSCOPE_API_KEY,
        result_format="message",
        response_format={"type": "json_object"},
        enable_thinking=True,
    )
    if response.status_code == 200:
        text = response.output.choices[0].message.content[0]["text"]
        return text
    logger.error(f"Qwen summary failed: {response.code} {response.message}")
    return None


def _summary_vllm_raw(prompt: str) -> Optional[str]:
    client = _get_vllm_client()
    resp = client.chat.completions.create(
        model=VLLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=81920,
        response_format={"type": "json_object"},
        **_NON_THINKING,
    )
    content = resp.choices[0].message.content
    return content if content else None


# ── 数据一致性分析 ─────────────────────────────────────────────────────────


def analyze_data_consistency(all_data_texts: str) -> Optional[dict]:
    """读取所有页面的数据提取信息，分析数据一致性、造假嫌疑等。

    Args:
        all_data_texts: 所有页面 data_info 的汇总文本（页号 + 数据内容）。

    Returns:
        数据分析结果 JSON dict，包含 inconsistencies、fabrication_suspicions、data_quality 等字段。
    """
    prompt = (
        _DATE_PREFIX +
        "你是一名浙江大学本科毕业论文数据审查专家，具有丰富的学术不端检测经验。\n"
        "以下是一篇论文各页面提取的原始数据信息，请进行综合分析。\n\n"
        "=== 各页面提取的数据信息 ===\n"
        f"{all_data_texts}\n\n"
        "请从以下角度进行分析:\n"
        "1. 【数据前后一致性】：同一指标在不同页面是否矛盾？样本量、实验组人数、关键数据是否前后一致？\n"
        "2. 【数据造假嫌疑】：是否存在明显不可能的数值（如概率大于1、百分比超过100%）？是否存在严重违反常识或逻辑矛盾的数据？\n"
        "3. 【数据完整性】：是否有明显缺失的关键数据（如实验只有实验组完全没有对照组）？\n"
        "4. 【统计方法合理性】：统计检验方法是否与数据类型严重不匹配？\n"
        "5. 【引用数据与原始数据一致性】：结论中引用的数据是否与前文实验数据明显矛盾？\n\n"
        "【重要判断原则】\n"
        "- 检查标准不能太严格，只要没有明显的数据造假或逻辑矛盾，都应视为通过。\n"
        "- 实验数据统一保留相同小数位数是正常规范，不要因为\"数据都是小数点后2位\"等格式统一性原因标记为问题。\n"
        "- 只有当存在明显的数值矛盾、逻辑不可能、或前后严重不一致时，才标记为问题。\n"
        "请返回以下JSON格式，不要返回其他内容:\n"
        '{\n'
        '  "inconsistencies": ["第X页与第Y页的XX指标明显矛盾：...", ...],\n'
        '  "fabrication_suspicions": ["第X页数据XX明显不可能（如概率>1）：...", ...],\n'
        '  "data_quality_issues": ["第X页完全没有对照组数据", ...],\n'
        '  "statistical_concerns": ["第X页使用的统计方法与数据类型严重不匹配：...", ...],\n'
        '  "citation_mismatch": ["结论引用的XX数据与第X页实验结果明显矛盾：...", ...],\n'
        '  "overall_assessment": "数据质量总体评价（合格/存疑/高风险）",\n'
        '  "summary": "数据综合分析结论（200-300字，未发现问题时简要说明即可）"\n'
        '}\n'
        "注意：如果未发现某类问题，对应数组返回空数组[]。如无数据可分析，返回所有字段为空的JSON。"
    )
    logger.info("start data consistency analysis")
    try:
        if use_local_llm():
            data = _data_analysis_vllm(prompt)
            logger.info("data consistency analysis result: %s", data)
            return data
        return _data_analysis_dashscope(prompt)
    except Exception as e:
        logger.error(f"LLM data analysis error: {e}", exc_info=True)
    return None


def _data_analysis_dashscope(prompt: str) -> Optional[dict]:
    from dashscope import MultiModalConversation
    response = MultiModalConversation.call(
        model=LLM_MODEL_SUMMARY,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        api_key=DASHSCOPE_API_KEY,
        result_format="message",
        response_format={"type": "json_object"},
        enable_thinking=True,
    )
    if response.status_code == 200:
        text = response.output.choices[0].message.content[0]["text"]
        result = json.loads(_extract_json(text))
        if isinstance(result, dict):
            return result
    return None


def _data_analysis_vllm(prompt: str) -> Optional[dict]:
    client = _get_vllm_client()
    resp = client.chat.completions.create(
        model=VLLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=81920,
        response_format={"type": "json_object"},
        **_WITH_THINKING,
    )
    result = json.loads(_extract_json(resp.choices[0].message.content))
    if isinstance(result, dict):
        return result
    return None


# ── Helpers ────────────────────────────────────────────────────────────────


def _build_check_prompt(page_type: str, description: str) -> Optional[str]:
    """Build type-specific check prompt."""
    template = _CHECK_PROMPT_TEMPLATES.get(page_type)
    if template is None:
        return (
            _DATE_PREFIX +
            f"这是毕业论文的页面。页面描述: {description}\n\n"
            + _PAGE_CHECK_RULES +
            "请检查该页面的整体格式是否符合浙江大学本科毕业论文的一般规范要求。\n"
            "返回JSON数组格式:\n"
            '[{"check_point": "页面格式规范，符合论文要求", "passed": true/false, "detail": "说明或无法确定的视为通过"}]'
        )
    return template.format(description=description)


def _extract_json(text: str) -> str:
    """Extract JSON from model response. Handles code blocks, multiple objects, etc."""
    text = text.strip()

    # Remove markdown code blocks
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # Try direct parse first
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass

    # Try to parse multiple concatenated JSON objects/arrays
    objects = []
    remaining = text
    while remaining.strip():
        remaining = remaining.strip()
        start = remaining.find("{")
        arr_start = remaining.find("[")
        if arr_start != -1 and (start == -1 or arr_start < start):
            start = arr_start
        if start == -1:
            break

        brace_count = 0
        bracket_count = 0
        in_string = False
        escape_next = False
        end = -1

        for i, ch in enumerate(remaining[start:], start):
            if escape_next:
                escape_next = False
                continue
            if ch == "\\":
                if in_string:
                    escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                brace_count += 1
            elif ch == "}":
                brace_count -= 1
                if brace_count == 0 and bracket_count == 0:
                    end = i + 1
                    break
            elif ch == "[":
                bracket_count += 1
            elif ch == "]":
                bracket_count -= 1
                if bracket_count == 0 and brace_count == 0:
                    end = i + 1
                    break

        if end == -1:
            break

        obj_text = remaining[start:end].strip()
        try:
            objects.append(json.loads(obj_text))
        except json.JSONDecodeError:
            pass
        remaining = remaining[end:]

    if len(objects) == 1:
        return json.dumps(objects[0], ensure_ascii=False)
    elif len(objects) > 1:
        return json.dumps(objects, ensure_ascii=False)

    # Fallback: find outermost { } or [ ]
    start = text.find("{")
    if start == -1:
        start = text.find("[")
    end = text.rfind("}")
    if end == -1:
        end = text.rfind("]")

    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]
    return text
