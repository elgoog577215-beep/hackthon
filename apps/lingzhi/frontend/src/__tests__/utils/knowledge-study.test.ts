import { describe, expect, it } from 'vitest'
import { courseStudyProfile, knowledgeFirstStudyLibrary, knowledgeFirstStudyExamples } from '@/utils/knowledge-study'
import type { KnowledgeLibraryView } from '@/types/knowledge-library'
import demo from '@/demo/knowledge-profile.json'
import type { KnowledgeProfile } from '@/types/knowledge-profile'
import { createKnowledgeTree } from '@/utils/knowledge-tree-layout'

const personal=demo.cases.at(-1)!.profile as KnowledgeProfile
const node=personal.nodes.find(n=>n.knowledge_id==='demo-k7')!
const library={ lifecycle_status:'accepted',binding_revision_id:personal.baseline_revision,revision_id:'library-1',nodes:[
  {knowledge_id:'course',node_type:'course'},
  {knowledge_id:'group',node_type:'concept_group',parent_id:'course',name:'条件分支'},
  {knowledge_id:node.knowledge_id,revision_id:node.knowledge_revision_id,node_type:'knowledge_point',parent_id:'group',name:node.name,statement:'课程原始规则',section_ids:['lecture-2'],covered_by_course:true,status:'active'},
] } as KnowledgeLibraryView

it('shows one adopted lecture and keeps other lectures as empty named branches',()=> {
  const partial = {...library,nodes:[library.nodes[0]!,
    {knowledge_id:'l1',node_type:'chapter',parent_id:'course',name:'第一讲'},
    {knowledge_id:'l2',node_type:'chapter',parent_id:'course',name:'第二讲'},
    {...library.nodes[1]!,parent_id:'l1'},library.nodes[2]!,
  ]} as KnowledgeLibraryView
  const result=courseStudyProfile(partial,'c','v',null,true)
  expect(result.availability).toBe('ready')
  expect(result.summary.total_count).toBe(1)
  expect(result.branches.find(b=>b.id==='l2')).toMatchObject({name:'第二讲',pending:true,knowledge_ids:[]})
  expect(createKnowledgeTree(result,'课程').children.map(n=>n.label)).toEqual(['第一讲','第二讲'])
  const empty=courseStudyProfile({...partial,nodes:partial.nodes.filter(n=>n.node_type!=='knowledge_point')},'c','v',null,true)
  expect(empty.summary.total_count).toBe(0)
  expect(createKnowledgeTree(empty,'课程').children.map(n=>n.label)).toEqual(['第一讲','第二讲'])
})

describe('course knowledge study binding',()=> {
  it('indexes a cross-lecture relation at both points without reversing or duplicating the edge',()=> {
    const source = {...library,nodes:[...library.nodes,{...library.nodes[2]!,knowledge_id:'new',name:'New point',section_ids:['lecture-3']}],
      relations:[{relation_id:'edge',source_knowledge_id:node.knowledge_id,target_knowledge_id:'new',relation_type:'prerequisite',reason:'先理解旧点',conditions:['特定条件']}]}
    const result=courseStudyProfile(source as KnowledgeLibraryView,'c','v',null,true)
    expect(result.nodes[0]?.links).toEqual([expect.objectContaining({knowledge_id:'new',direction:'outgoing',type:'prerequisite',reason:'先理解旧点'})])
    expect(result.nodes[1]?.links).toEqual([expect.objectContaining({knowledge_id:node.knowledge_id,direction:'incoming',type:'prerequisite'})])
    const hidden=courseStudyProfile({...source,nodes:source.nodes.filter(n=>n.knowledge_id!=='new')} as KnowledgeLibraryView,'c','v',null,true)
    expect(hidden.nodes[0]?.links).toEqual([])
  })
  it('uses exact current evidence but retains authoritative course text and lecture links',()=> {
    const result=courseStudyProfile(library,personal.course_id,personal.course_version_id,personal,false)
    expect(result.nodes[0]).toMatchObject({mastery:25,name:node.name,statement:'课程原始规则',parent_id:'group',section_refs:['lecture-2']})
    expect(result.branches[0]?.knowledge_ids).toEqual([node.knowledge_id])
  })
  it('does not leak scores or evidence into teacher preview or a mismatched course/version/baseline',()=> {
    const run=(changes:Partial<KnowledgeProfile>={},preview=false)=>courseStudyProfile(library,personal.course_id,personal.course_version_id,{...personal,...changes},preview)
    for(const result of [run({},true),run({course_id:'another'}),run({course_version_id:'old'}),run({baseline_revision:'old'})]) {
      expect(result.nodes[0]).toMatchObject({mastery:null,status:'unassessed',evidence:[],assessment_count:0})
    }
  })
  it('does not bind old point revisions, and omits rejected and out-of-course points',()=> {
    const result=courseStudyProfile({...library,nodes:[...library.nodes,
      {...library.nodes[2]!,knowledge_id:'rejected',status:'rejected'},
      {...library.nodes[2]!,knowledge_id:'outside',covered_by_course:false},
    ].map(n=>n.knowledge_id===node.knowledge_id?{...n,revision_id:'new-point-revision'}:n)},personal.course_id,personal.course_version_id,personal,false)
    expect(result.nodes).toHaveLength(1)
    expect(result.nodes[0]?.mastery).toBeNull()
  })
})

it('accepts only the adopted knowledge-first tree and exact-revision handout examples',()=> {
  const tree={revision_id:'kb1',categories:[{id:'group',parent_id:null,name:'Group'}],knowledge_points:[{knowledge_id:'p1',revision_id:'r1',parent_id:'group',topic:'s1',name:'Point',statement:'Rule'}]}
  const source={enabled:true,knowledge_revision:'kb1',tree,handouts:[{current_revision_id:'h1',revisions:[{revision_id:'h1',source_knowledge_revision:'kb1',sections:[{blocks:[{block_id:'b1',role:'example',content:'Current example',knowledge_refs:[{knowledge_id:'p1',revision_id:'r1'}]},{block_id:'b2',role:'example',content:'Old example',knowledge_refs:[{knowledge_id:'p1',revision_id:'old'}]}]}]}]}]}
  const library=knowledgeFirstStudyLibrary(source,['s1'])!
  expect(library.nodes.find(n=>n.knowledge_id==='p1')?.section_ids).toEqual(['s1'])
  expect(knowledgeFirstStudyExamples(source,library)).toEqual({p1:{example:'Current example',exampleMarkdown:true}})
  expect(library.nodes.find(n=>n.knowledge_id==='p1')?.block_ids).toEqual(['b1'])
  expect(knowledgeFirstStudyLibrary({...source,knowledge_revision:'kb2'},['s1'])).toBeNull()
  expect(knowledgeFirstStudyLibrary({...source,tree:null},['s1'])).toBeNull()
})
