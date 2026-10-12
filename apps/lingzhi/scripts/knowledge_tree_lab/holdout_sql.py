"""Prepare one previously unused official chapter, without node-level coaching.

Evaluator requirements are frozen separately and never enter model requests.
Source HTML is fetched once and retained outside the repository.
"""
import argparse
from pathlib import Path
import re
import sys
from bs4 import BeautifulSoup
from .pipeline import read,save,digest
from .foundation_round import SYSTEM,INVENTORY,ATOMS,CLASSIFY

# Reviewer requirements: absent from fixtures, contexts and prompts.
REQUIREMENTS={
 'M1':['入门范围非完整SQL教程，部分特性为扩展','示例前提mydb已创建且psql可启动','教程源码位置及二进制发行版可能无文件','make生成脚本并编译示例C文件','psql的文件读入命令','单步模式在发送语句前暂停'],
 'M2':['关系型数据库和关系/表','表为有名行集合','各行具有相同命名列且列有类型','列顺序固定','表行顺序无保证','表/数据库/单服务器数据库簇的层次'],
 'M3':['建表需表名列名类型','psql用分号判命令结束','命令可用空格制表与换行排版','双短横线注释到行尾','关键字和未加双引号标识符大小写规则','双引号标识符保留大小写的例外','varchar的长度含义','int与real等给定类型语义','支持标准类型并可自定义类型','类型名一般非关键字且有SQL标准特例','point为PostgreSQL特有类型','DROP TABLE移除表'],
 'M4':['INSERT添加行','非简单数值常量通常需单引号','date可接受多格式而教程采用无歧义形式','point输入为坐标对','隐式插入依赖列顺序','显式列列表可换顺序或省略列','显式列名的可维护性建议','COPY批量读平面文本通常更快但灵活性较低','COPY文件由后端读取须在服务器可访问','示例数据/输入文件作为案例不冒充通用事实'],
 'M5':['SELECT取数据及三部分结构','星号代表所有列','生产中星号受新增列影响的边界','选择列表可为表达式','AS改输出列标签及其可省略性','WHERE仅返回条件为真的行','AND/OR/NOT逻辑筛选','ORDER BY排序','单个排序键相同的行仍可任意次序','增加排序键进一步确定次序','DISTINCT去除重复结果行','DISTINCT本身不保证当前PostgreSQL排序'],
 'M6':['连接按条件组合多表或同表实例的行','内连接不保留不匹配行','SELECT星号连接拼接两边列而显式列可控制输出','同名列需限定所属表','限定列名可防后续同名列变化','本例隐式连接与JOIN ON等价且后者含义更清楚','左外连接左行至少一次，可能不止一次','不匹配左行的右列补NULL','右/全外连接仅作为待探索提及，不编造材料未解释规则','自连接是同表与自身连接','别名区分表实例及简化名称','逐对比较只是概念模型，不是保证的执行算法'],
 'M7':['聚合多输入行得一个结果','count/sum/avg/max/min作为聚合例子','同一查询层WHERE先于聚合不能直接引用该层聚合','独立子查询可先算聚合供外层WHERE比较','GROUP BY按组计算聚合','HAVING过滤聚合后分组结果','WHERE筛聚合前输入行','HAVING允许不包含聚合的明确例外','无需聚合的条件可提前WHERE减少计算','LIKE示例是模式匹配及前缀限制','FILTER只影响所附聚合输入，不影响其他聚合'],
 'M8':['UPDATE修改现有行','SET可同时修改多个列并使用原列表达式','WHERE限定更新行','更新后数据只作为可追溯案例'],
 'M9':['DELETE删除行','WHERE限定删除范围','无WHERE删除全部行但表保留为空','删除不会先向用户请求确认']}


def prepare(root):
    if (root/'manifest.json').exists():raise ValueError('already_frozen')
    old=read(root/'materials.json');materials=[]
    for i,item in enumerate(old,1):
        soup=BeautifulSoup((root/f'source-{i}.html').read_bytes(),'html.parser');article=soup.select_one('div.sect1')
        blocks=[]
        for node in article.find_all(['h2','h3','p','pre','li']):
            if any(parent.name in {'p','pre','li'} for parent in node.parents if parent is not article):continue
            text=node.get_text('',strip=False).strip()
            if node.name!='pre':text=' '.join(text.split())
            if text:blocks.append(text)
        materials.append({**item,'text':'\n\n'.join(blocks)})
    save(root/'materials-extraction-original.json',old);save(root/'materials.json',materials)
    course={'key':'postgres_sql_holdout','title':'PostgreSQL 18：SQL语言入门（官方教程完整第2章）',
       'profile':'PostgreSQL 18官方教程第2章（2.1至2.9）；这是SQL简单操作的入门概览，不是完整SQL语言，部分功能为PostgreSQL扩展。假定已创建mydb并能启动psql。只依据所给材料整理，示例表和数值不作为通用规则。',
       'materials':materials}
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'backend'))
    from course_knowledge_context import build_knowledge_generation_context,knowledge_context_prompt
    from .context_comparison import fixture_course
    raw_course=fixture_course(course)
    context=knowledge_context_prompt(build_knowledge_generation_context(raw_course))
    keys=('course_id','course_title','requirements','target_audience','course_intent','difficulty','scope_contract','evidence_package','material_coverage','source_reference_aliases','revision_id')
    save(root/'contexts.json',{course['key']:{k:context[k] for k in keys if k in context}})
    save(root/'fixtures.json',[course])
    # Generic prompts from the previous foundation round: only capacity ceilings change.
    prompts={'system':SYSTEM,'inventory':INVENTORY.replace('最多32项','最多96项'),
             'atoms':ATOMS.replace('最多24点','最多128点'),'classify':CLASSIFY.replace('最多8个分类','最多24个分类')}
    save(root/'prompts.json',prompts);save(root/'requirements.json',REQUIREMENTS)
    save(root/'eval.json',{'max_calls':4,'max_output_tokens':24000,'request_timeout_seconds':600,'json_mode':True,
        'scope':'先前四微单元实验未使用的新学科官方完整章节；不是完整学期数据库课程',
        'stages':['inventory','atoms','classify'],'human_node_guidance':False,'human_content_repair':False,
        'model_repair_calls':0,'hidden_requirements':True,
        'changes_from_foundation':['仅放宽条目/节点/分类数量上限','输出预算24000与超时600秒适应长材料','开启提供方JSON模式'],
        'criteria':['源内准确及元答案一致','隐藏清单的语义覆盖','独立原子判断而非复合或案例叶子','分类无环无遗漏且语义适当','范围随独立节点保留'],
        'comparison_limit':'材料长度、学科、语言均改变；先前4/4有人工逐点计划，此轮无，不能将单个差异归因于某一因素',
        'no_production_writes':True,'no_model_code_execution':True})
    save(root/'source-provenance.json',{'origin':'https://www.postgresql.org/docs/18/tutorial-sql.html',
        'license':'https://www.postgresql.org/about/licence/','chapter_complete':True,'sections':len(materials),
        'characters':sum(len(m['text']) for m in materials),'words':sum(len(m['text'].split()) for m in materials),
        'source_hashes':{m['url']:digest(m['text']) for m in materials},
        'extraction':'官方HTML的sect1正文，保留脚注；段落仅折叠空白，pre代码/结果保留换行；未翻译或预先拆成知识点',
        'known_exposure':'未用于本线程此前知识树生成/精修；不声称模型训练时未见过公开文档'})
    names=('fixtures.json','contexts.json','prompts.json','requirements.json','eval.json','source-provenance.json')
    save(root/'manifest.json',{'input_hashes':{n:digest(read(root/n)) for n in names}})
    print(read(root/'source-provenance.json')['characters'],sum(map(len,REQUIREMENTS.values())),'hidden requirements')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);prepare(p.parse_args().root)
