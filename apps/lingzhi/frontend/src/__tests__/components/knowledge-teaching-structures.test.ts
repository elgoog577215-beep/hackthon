import { mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import Panel from '@/components/KnowledgeTeachingStructures.vue'
import { setLocale } from '@/shared/i18n'
import zh from '../../../public/locales/zh/translation.json'
import en from '../../../public/locales/en/translation.json'

const tree:any={knowledge_points:[{knowledge_id:'K',revision_id:'R',name:'操作位置'},{knowledge_id:'J',revision_id:'JR',name:'另一知识'}],
  mastery_criteria:[{criterion_id:'C',knowledge_ids:['K'],knowledge_revision_refs:{K:'R'},name:'独立判断操作位置',dimension:'understanding',readiness:'ready',
    observable_performance:'指出正确位置',verification_method:'给出新状态，要求说明位置',controlled_conditions:['已给初始状态'],
    checkpoints:[{checkpoint_id:'A',label:'位置',pass_condition:'指出规定位置'},{checkpoint_id:'B',label:'理由',pass_condition:'理由符合定义'}],
    scoring:{max_score:2,pass_score:2},evidence_policy:{min_independent_successes:2,min_distinct_variants:2}}],
  misconceptions:[{misconception_id:'M',knowledge_ids:['K','J'],knowledge_revision_refs:{K:'R',J:'JR'},name:'混淆操作位置',
    observable_error_pattern:'放到了另一端',hypothesis:'可能混淆端点',alternative_explanations:['也可能读图失误'],
    discrimination:'先标出两端，再说明位置',repair_strategy:'对照前后状态',retest:'换一个状态再判断'}],
  extensions:[{extension_id:'X',knowledge_ids:['K'],knowledge_revision_refs:{K:'R'},name:'组合操作',scope_role:'extension',
    goal:'解释连续操作',explanation:'逐次更新状态。',prerequisite_knowledge_refs:{K:'R'},task:'比较两种顺序',success_criteria:['每一步符合规则'],resource_refs:[]}],
  teaching_coverage:{K:{status:'ready',knowledge_revision:'R',note:'',no_mistakes:'',no_extensions:''}}}
const options={global:{stubs:{MarkdownRenderer:{props:['content'],template:'<span>{{content}}</span>'}}}}
beforeEach(()=>vi.restoreAllMocks())

it.each([['zh',zh],['en',en]])('shows one teaching section at a time in %s',async(locale,messages)=>{
  vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>messages})));await setLocale(locale as 'zh'|'en')
  const w=mount(Panel,{props:{tree,knowledgeId:'K'},...options})
  expect(w.findAll('[role="tab"]')).toHaveLength(3)
  expect(w.find('[data-testid="structured-mistake"]').exists()).toBe(false)
  expect(w.find('[data-testid="structured-criterion"]').element.tagName).toBe('DETAILS')
  expect(w.find('[data-testid="structured-criterion"]').attributes('open')).toBeUndefined()
  expect(w.findAll('.evidence-policy')).toHaveLength(1)
  await w.findAll('[role="tab"]')[1]!.trigger('click')
  expect(w.find('[data-testid="structured-criterion"]').exists()).toBe(false)
  expect(w.text()).toContain('也可能读图失误')
  await w.findAll('button').find(b=>b.text()==='另一知识')!.trigger('click')
  expect(w.emitted('select-knowledge')).toEqual([['J']]);w.unmount()
})
it('resets the section when switching knowledge and hides stale records',async()=>{
  vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>zh})));await setLocale('zh')
  const w=mount(Panel,{props:{tree,knowledgeId:'K'},...options})
  await w.findAll('[role="tab"]')[1]!.trigger('click')
  const stale=structuredClone(tree);stale.knowledge_points[0].revision_id='new'
  await w.setProps({tree:stale,knowledgeId:'J'})
  expect(w.findAll('[role="tab"]')[0]!.attributes('aria-selected')).toBe('true')
  expect(w.text()).not.toContain('独立判断操作位置');w.unmount()
})
it('preserves specific review notes and formula names inside disclosed items',async()=>{
  vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>zh})));await setLocale('zh')
  const reviewed=structuredClone(tree);reviewed.misconceptions[0].name='遗漏阶乘 $k!$';reviewed.misconceptions[0].review_notes=['复测答案需核对']
  const w=mount(Panel,{props:{tree:reviewed,knowledgeId:'K'},...options})
  await w.findAll('[role="tab"]')[1]!.trigger('click')
  expect(w.text()).toContain('复测答案需核对')
  expect(w.find('[data-testid="structured-mistake"] summary .katex').exists()).toBe(true);w.unmount()
})
