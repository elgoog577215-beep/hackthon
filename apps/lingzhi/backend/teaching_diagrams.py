"""One diagram vocabulary for the existing handout and answer requests.

The Markdown fence is preserved by the existing stores. Only the client draws
the declarative payload; this module adds no model call or publication gate.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def teaching_diagram_catalog() -> dict:
    return json.loads((Path(__file__).resolve().parents[1] / "shared" / "teaching-diagrams-v1.json").read_text(encoding="utf-8"))


def teaching_diagram_prompt() -> str:
    catalog = teaching_diagram_catalog()
    choices = "\n".join(f"- {t['id']}（{t['zh']}）：{t['use']}；数据字段：{t['data']}。" for t in catalog["types"])
    return """\n\n## 按内容需要选择教学图表
图表和正文在本次请求中一起完成，不另写生成计划。解释关系、步骤、集合、空间或真实数据时主动选择合适图型；简单事实用文字，共同维度比较优先用 Markdown 表格。不为每段凑图，不把所有内容强制画成流程图。用户指定图型且数据支持时采用；缺数据/关系时说明缺口，保留文字，不编造数值、时间、坐标、基数、权限、因果或学生能力分。
图前交代问题和条件，图后解释结论。图不能替代完整推导和答案。当前答案披露、来源、权限及文件范围的约束同样适用于图，禁止把隐藏解答藏进图表。
使用独立的 ```lingzhi-diagram 代码围栏，内部只写一个合法 JSON 对象。通用字段：schema_version="teaching_diagram_v1",type=下表ID,title=短标题,summary=完整可读结论及必要条件,source=当前已提供的来源定位或“假设示例”（不得伪造引用）。其余只写所选图型的数据字段。不输出 SVG、HTML、CSS、脚本、外部图片或布局坐标；定量/空间图需要的坐标只能来自内容数据。
共享对象定义：nodes=[{id:唯一短ID,label:名称,detail:完整说明可选,parent:父ID可选,group:组ID可选,kind:decision可选}]；edges=[{from:节点ID,to:节点ID,label:关系/条件可选,kind:return|inheritance|composition|association可选,value:真实流量可选}]；groups=[{id:组ID,label:组名}]。items 的字段按下表填写。所有文字为纯文本，保留完整标签和来源；数值为有限 JSON 数字，缺测用 null，不当成零。节点最多24、边最多48、数据项最多32；复杂图分为概览和完整细节，不静默截断或丢节点。禁止猜测关系，树必须单父无环，集合成员必须明确。
量图必须提供单位/量规；条形从零开始，时间轴/甘特按真实间隔，漏斗按真实递减数值，瀑布图 start 是起始总量且 items 仅是有符号变化（不重复终值），桑基中间节点入流等于出流且无环，雷达3–8个共同 axes、series.values 同长且 scale=[0,量规上限]，象限给真实 x_domain/y_domain。集合图2–3个 sets，嵌套 nodes.parent 确实表示包含；普通循环不使用需共同 hub 状态的 loop。架构变化 before/after 复用相同节点 ID，不能只凭标题推断变化。
学科图解：二维向量与线性组合使用 vector_plot，from/to 必须对应题设坐标或正文已展示的计算，平移向量保留真实首尾。矩阵消元使用 matrix_steps，每步列出完整矩阵及本步行操作，不能省略中间数据。解的分类按已给条件使用 flowchart，不用雷达、漏斗或装饰性统计图替代数学含义。
可选图型（共享注册表）：
""" + choices + """
示例（实际输出时围栏闭合，内容按当前来源替换）：
```lingzhi-diagram
{"schema_version":"teaching_diagram_v1","type":"flowchart","title":"检查后再读取","summary":"先检查范围，范围内才读取；这是条件流程示例。","source":"假设示例","nodes":[{"id":"check","label":"索引是否在范围内？","kind":"decision"},{"id":"read","label":"读取元素"},{"id":"stop","label":"结束"}],"edges":[{"from":"check","to":"read","label":"是"},{"from":"check","to":"stop","label":"否"}]}
```
"""
