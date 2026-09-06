#!/usr/bin/env python3
"""Export a fictional teaching example through the real confirmed-draft compiler.

Run with the application's Python environment and --output-dir outside Git.
No model calls, course records, services or private sources are involved.
"""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import json
from course_document import CourseBlock, CourseDocument, CourseSection
from course_presentation_graph import compile_course_presentation_graph
from ppt_fixed_templates import compile_fixed_template
from ppt_fixed_draft import lower_fixed_response
from ppt_teaching_planner import normalize_page_response
from ppt_teaching_manuscript import compile_teaching_manuscript
from slide_deck_v6 import compile_slide_deck_v6_from_manuscript
from slide_deck_v6_renderer import export_slide_deck_v6_pptx
from slide_deck_renderer import audit_exported_pptx

# A complete, explicitly fictional teaching source, not a generated model result.
source_text = '''平均数与中位数。以下月收入数据为教学示例，不代表真实调查。五人的月收入分别为甲 4、乙 5、丙 5、丁 6、戊 30，单位为千元/月。同一组数据可以有不同的典型值。先观察分布，再选择概括方式。
算术平均数是全部数值之和除以数据个数。平均数 = (4 + 5 + 5 + 6 + 30) ÷ 5 = 10。平均数为10千元。它表示总收入均摊后的数值，不表示多数人都收入10千元。
求中位数时，先从小到大排序，再找到中间位置，读出对应数值；这里共有5个数，中间位置是第3个，对应5。中位数为5千元。偶数个数据时，中位数是中间两个数的平均数。
平均数参与计算的是全部数值，中位数依据的是排序位置。异常高值会拉高平均数；中位数通常受异常高值影响较小。同样的数据，指标服务于不同的问题。
把最高收入从30改为80，其余4、5、5、6保持不变。最高值增加50，平均数从10变为20；中位数仍是5。平均数受每一个观测值影响；中位数由中间位置决定。这种稳定性并不意味着中位数能反映全部差异。
课堂任务：回到原始数据4、5、5、6、30。向一位新同学描述这五人的典型收入，你选10还是5？请说明原因。参考解释：在这组明显偏斜的数据中，5更接近中间位置，10受最高收入拉高。若问题是把总收入平均分配，则10有明确意义。没有脱离问题的最佳指标。
小结：关心总量均摊时选平均数，因为每个数值都参与计算；关心中间位置时看中位数，同时说明分布与异常值，避免用单一数字掩盖差异。'''
def field(value, heading=''):
    d={'text':value,'sources':[{'block_id':'source','quote':source_text}]}
    if heading: d['heading']=heading
    return d
def exact(quote): return {'sources':[{'block_id':'source','quote':quote}]}
def page(slug,title,goal,notes,**fields): return slug,goal,{'title':title,'notes':notes,**fields}
values=[
 page('cover','平均数与中位数','理解典型值与分布的关系','使用虚构的收入数据展开讨论，不把示例当作实际收入调查。',subtitle=field('同一组数据，为什么会有两种典型值？')),
 page('chart','一组月收入数据（教学示例）','观察异常高值与其他数值的差异','先让学生观察：四个数接近，一个数明显偏高。此时不要急于给出平均数。',unit=exact('千元/月'),points=[{'label':field(a),'value':exact(str(b))} for a,b in [('甲',4),('乙',5),('丙',5),('丁',6),('戊',30)]]),
 page('formula','平均数怎样计算','理解平均数的总量均摊含义','让学生先计算总量，再除以人数。强调10是均摊值，并不意味着多数人的收入是10。',formula=exact('平均数 = (4 + 5 + 5 + 6 + 30) ÷ 5 = 10'),explanation=field('10千元表示总收入均摊后的数值，\n并不表示多数人都收入10千元。')),
 page('flow','求中位数的三个步骤','掌握奇数个数据的中位数求法','本页处理奇数个数据。补充：偶数个数据时，取中间两个数的平均数。',steps=[field('从小到大排序\n4、5、5、6、30'),field('找到中间位置\n共5个数，取第3个'),field('读出对应数值\n中位数为5千元')]),
 page('comparison','同一组数据，两种概括','比较两种统计指标的计算依据和含义','通过共同维度比较，不把中位数简单说成比平均数更好。',condition=field('示例数据：4、5、5、6、30（千元）'),left_subject=field('平均数'),right_subject=field('中位数'),rows=[{'dimension':field('本例数值'),'left':field('10千元'),'right':field('5千元')},{'dimension':field('计算依据'),'left':field('全部数值之和 ÷ 个数'),'right':field('排序后的中间位置')},{'dimension':field('异常高值'),'left':field('会拉高平均数'),'right':field('通常影响较小')}],conclusion=field('指标的选择取决于要回答的问题')),
 page('bullets','最高值从30变为80，会怎样？','理解异常值对平均数和中位数的不同影响','让学生计算或口头预测。其余四个值固定为4、5、5、6，只有最高值变化。',points=[field('最高值增加50，其余数值保持不变。','只改变一个数'),field('每个观测值都参与计算，平均数从10变为20。','平均数跟着变化'),field('中间位置对应的数没有改变，中位数仍为5。','中位数保持不变')]),
 page('question','你会怎样描述典型收入？','根据问题和分布选择统计指标','先让学生独立选择并说明原因，再核对解释。若学生选择10，追问他回答的是典型位置还是总量均摊问题。',question=field('回到原始数据：4、5、5、6、30。\n描述这五人的典型收入，你会选10还是5？\n请说明原因。'),answer=field('5更接近中间位置；10受最高收入拉高。\n如果问题是总收入如何均摊，10就有明确意义。')),
 page('summary','先明确问题，再选择指标','形成有条件的指标选择规则','让学生用自己的语言说明两个指标各自回答什么问题，并提醒不能只报一个数字而省略分布。',points=[field('每个数值都参与计算，适合回答总量如何分配。','关心总量均摊：平均数'),field('同时说明分布与异常值，避免一个数字掩盖差异。','关心中间位置：中位数')]),
]
doc=CourseDocument(course_id='authored-layout-demo',title='平均数与中位数',document_revision='example-source-v1',sections=[CourseSection(section_id='s',title='平均数与中位数',position=0)],blocks=[CourseBlock(block_id='source',section_id='s',position=0,payload={'markdown':source_text},internal_revision='r1')])
graph=compile_course_presentation_graph(doc,teaching_plan={})
template=compile_fixed_template('qizhi-classroom')
sources={'source':{'block_id':'source','block_revision':'r1','full_text':source_text}}
planned=[]
for i,(slug,goal,data) in enumerate(values):
 plan={'layout_id':template.layout_id(slug),'page_goal':goal}
 value=normalize_page_response(lower_fixed_response(data,plan),sources)
 planned.append({**value,'page_id':f'p{i+1}','teaching_unit_id':graph.units[0].teaching_unit_id,'source_block_ids':['source']})
manuscript=compile_teaching_manuscript(doc,graph,template,{'central_question':'同一组数据，为什么会有两种典型值？'},planned)
deck=compile_slide_deck_v6_from_manuscript(doc,graph,manuscript,template)
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output-dir', type=Path, required=True)
out = parser.parse_args().output_dir
out.mkdir(parents=True, exist_ok=True)
path=export_slide_deck_v6_pptx(deck,out/'平均数与中位数.pptx')
report=audit_exported_pptx(path,expected_slide_count=9,require_pixel_audit=False)
(out/'内容稿.json').write_text(manuscript.model_dump_json(indent=2))
(out/'讲义来源.md').write_text(source_text)
(out/'文件检查.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({'path':str(path),'audit':report},ensure_ascii=False))
