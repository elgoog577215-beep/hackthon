"""定位知识关系在哪一层丢失：模型没产出，还是校验/装配丢弃了。

这两者修法相反——前者要改 prompt，后者要放宽校验——所以必须分清。

**方法上的关键一点：不能跨运行相减。** 模型每次输出都不同，用 A 次的原始
输出减 B 次的最终结果，得到的差值没有意义。必须在**同一次运行内**同时抓
三个点，闭环比对：

  1. `normalize_teaching_plan_batch_v3` 入口 —— 模型原始 payload
  2. `validate_teaching_plan_batch_v3` 出口 —— 批次是否被判失败
  3. `assemble_course_teaching_plan_v3` 出口 —— 最终装配结果

用法（需在 backend 目录下，且已配好 AI 凭据）：
    cd backend && set -a && source ~/.lz_qwen_provider.env && set +a \\
      && .venv/bin/python ../scripts/probe_relation_loss.py

输入课程需求读 `/tmp/kb-gen/req.json`；结果写 `/tmp/kb-gen/probe2.json`。

2026-08-11 实测结论：13 条产出 / 13 条装配，**逐节一致，无丢弃**，
即"关系少"是 prompt 侧问题。同时发现装配用 dict 按 node_id 后写覆盖，
重试返回 0 条时会整段抹掉前一次的成功结果（见 NOTES 3.12）。
"""
import asyncio, json, os, sys, uuid
from collections import defaultdict
sys.path.insert(0, '.')
# provider 凭据由 ~/.lz_qwen_provider.env 提供（仓库外）。
# 原先这里手动置空 MODELSCOPE_API_KEY 是为了绕开那个 401 的端点；
# ModelScope 端点已决定弃用，env 文件也已处理，故删除该逻辑。

import course_teaching_plan_v3 as tp
import course_service as cs
from course_service import CourseService

raw_seq = defaultdict(list)   # node_id -> [每次归一化时模型给的关系数]
assembled = {}                # node_id -> 最终装配后的关系数

_norm = tp.normalize_teaching_plan_batch_v3
def spy_norm(payload, **kw):
    for s in (payload or {}).get('sections') or []:
        if isinstance(s, dict):
            rels = s.get('knowledge_relations') or []
            raw_seq[str(s.get('node_id'))].append(len(rels))
    return _norm(payload, **kw)

_asm = tp.assemble_course_teaching_plan_v3
def spy_asm(**kw):
    out = _asm(**kw)
    for s in out.get('sections') or []:
        assembled[str(s.get('node_id'))] = len(s.get('knowledge_relations') or [])
    return out

for mod in (tp, cs):
    mod.normalize_teaching_plan_batch_v3 = spy_norm
    if hasattr(mod, 'assemble_course_teaching_plan_v3'):
        mod.assemble_course_teaching_plan_v3 = spy_asm

async def main():
    svc = CourseService()
    req = json.load(open('/tmp/kb-gen/req.json'))
    try:
        await svc.build_course_draft(
            course_id=str(uuid.uuid4()), topic=req['subject'],
            target_audience=req['target_audience'], depth='intermediate',
            requirements=req['requirements'], course_type='systematic',
            teacher_course_brief=req['teacher_course_brief'],
        )
    except Exception as e:
        print(f'（中断，探针有效）{str(e)[:60]}', flush=True)

    print('\nnode_id      模型各次输出 -> 最后一次 | 装配后 | 判定', flush=True)
    verdict = {}
    for nid in sorted(set(raw_seq) | set(assembled)):
        seq = raw_seq.get(nid, [])
        last = seq[-1] if seq else None
        asm = assembled.get(nid)
        if asm is None:
            v = '未装配'
        elif last is None:
            v = '无原始记录'
        elif asm == last:
            v = '一致（无丢弃）'
        elif last == 0 and asm == 0:
            v = '模型未产出'
        else:
            v = f'**丢弃 {last-asm} 条**'
        verdict[nid] = v
        print(f'{nid:12} {seq} -> {last} | {asm} | {v}', flush=True)
    json.dump({'raw_seq': dict(raw_seq), 'assembled': assembled, 'verdict': verdict},
              open('/tmp/kb-gen/probe2.json','w',encoding='utf-8'), ensure_ascii=False, indent=2)

asyncio.run(main())
