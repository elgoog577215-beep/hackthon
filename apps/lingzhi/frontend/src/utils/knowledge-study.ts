import type { KnowledgeLibraryView, KnowledgeNode } from '../types/knowledge-library'
import type { KnowledgeProfile, KnowledgeProfileNode, KnowledgeProfileSummary } from '../types/knowledge-profile'

export type CourseStudyLibrary = Pick<KnowledgeLibraryView,'nodes'|'lifecycle_status'|'binding_revision_id'|'revision_id'> & Partial<Pick<KnowledgeLibraryView,'relations'>>

function summarize(nodes:KnowledgeProfileNode[]):KnowledgeProfileSummary {
  const assessed = nodes.filter(n => n.mastery !== null)
  const sum = assessed.reduce((value,n) => value + n.mastery!,0)
  const round = (value:number) => Math.round(value * 10) / 10
  return { total_count:nodes.length, assessed_count:assessed.length, unknown_count:nodes.length-assessed.length,
    verified_progress:nodes.length ? round(sum/nodes.length):0, coverage:nodes.length ? round(assessed.length/nodes.length*100):0,
    assessed_average:assessed.length ? round(sum/assessed.length):null,
    mastered_count:nodes.filter(n=>n.status==='supported_mastery').length, attention_count:nodes.filter(n=>n.status==='needs_review').length }
}

/** Browse the real course library; unknowns are never fabricated learner scores. */
export function courseStudyProfile(library:CourseStudyLibrary, courseId:string, version:string, personal:KnowledgeProfile|null, preview:boolean):KnowledgeProfile {
  const roots = new Set(library.nodes.filter(n=>n.node_type==='course').map(n=>n.knowledge_id))
  const eligible = library.lifecycle_status === 'accepted' && !preview && personal?.course_id === courseId
    && personal.course_version_id === version && personal.baseline_revision === library.binding_revision_id
  const parent = (id:string|null) => !id || roots.has(id) ? '' : id
  const nodes:KnowledgeProfileNode[] = library.nodes.filter(n=>n.node_type==='knowledge_point' && n.covered_by_course && !['rejected','deleted','archived'].includes(n.status)).map(n=> {
    const evidence = eligible ? personal.nodes.find(p=>p.knowledge_id===n.knowledge_id && p.knowledge_revision_id===n.revision_id) : undefined
    return { knowledge_id:n.knowledge_id, knowledge_revision_id:n.revision_id, mastery:null, confidence:'none', status:'unassessed',
      assessment_count:0, independent_count:0, activity_count:0, historical_count:0, pending_attribution_count:0, next_action:'verify', evidence:[],
      ...evidence, name:n.name, aliases:n.aliases || [], terms:n.terms || [], statement:n.statement || n.description || '', parent_id:parent(n.parent_id), section_refs:n.section_ids || [], block_refs:n.block_ids || [] }
  })
  const byId = new Map(nodes.map(n=>[n.knowledge_id,n]))
  for(const node of nodes) node.links=[]
  for(const edge of library.relations || []) {
    if(['rejected','deleted','archived'].includes(edge.status)) continue
    const source=byId.get(edge.source_knowledge_id), target=byId.get(edge.target_knowledge_id)
    if(!source || !target || source===target) continue
    for(const [from,to,direction] of [[source,target,'outgoing'],[target,source,'incoming']] as const) {
      if(from.links!.some(link=>link.relation_id===edge.relation_id)) continue
      from.links!.push({relation_id:edge.relation_id,knowledge_id:to.knowledge_id,name:to.name,direction,type:edge.relation_type,
        reason:edge.reason || '',conditions:edge.conditions || [],lecture_names:library.nodes.filter(n=>['chapter','section'].includes(n.node_type) && n.section_ids?.some(id=>to.section_refs.includes(id))).map(n=>n.name)})
    }
  }
  const groups = library.nodes.filter(n=>n.node_type!=='knowledge_point' && n.node_type!=='course')
  const parentById = new Map(groups.map(n=>[n.knowledge_id,parent(n.parent_id)]))
  const branches = groups.map(group=> {
    const members=nodes.filter(n=> { let id=n.parent_id; const seen=new Set<string>(); while(id && !seen.has(id)) { if(id===group.knowledge_id) return true; seen.add(id); id=parentById.get(id)||'' } return false })
    const lecture = group.node_type === 'chapter' || (group.node_type === 'section' && !parent(group.parent_id))
    return { id:group.knowledge_id,parent_id:parent(group.parent_id),name:group.name,knowledge_ids:members.map(n=>n.knowledge_id),summary:summarize(members),pending:lecture && !members.length }
  }).filter(b=>b.knowledge_ids.length || b.pending)
  return { rule_version:personal?.rule_version || 'knowledge_mastery_v1',baseline_revision:library.binding_revision_id,
    revision_id:library.revision_id,course_id:courseId,course_version_id:version,availability:nodes.length || branches.length?'ready':'tree_unavailable',
    nodes,branches,summary:summarize(nodes),policy:{calibrated_probability:false,unknown_is_zero_ability:false,equal_leaf_weights:true} }
}

export interface KnowledgeFirstStudySource {
  enabled:boolean; knowledge_revision:string; document_revision?:string
  handouts?:Array<{ current_revision_id:string; revisions:Array<{revision_id:string;source_knowledge_revision:string;sections:Array<{blocks:Array<{block_id:string;role:string;content:string;knowledge_refs:Array<{knowledge_id:string;revision_id:string}>}>}>}> }>
  tree?: { revision_id?:string; categories?:Array<{id:string;parent_id:string|null;name:string}>;
    relations?:Array<{id:string;source_id:string;target_id:string;type:string;reason:string;conditions?:string[]}>;
    knowledge_points?:Array<{knowledge_id:string;revision_id:string;parent_id:string;topic:string;section_refs?:string[];name:string;statement:string;conditions?:string[];counterexamples?:string[];source_refs?:string[]}> } | null
}
/** Only the adopted current tree is readable here; candidates/history are not inputs. */
export function knowledgeFirstStudyLibrary(source:KnowledgeFirstStudySource, sectionIds:string[]):CourseStudyLibrary|null {
  if(!source.enabled || !source.knowledge_revision || !source.tree?.knowledge_points?.length) return null
  if(source.tree.revision_id && source.tree.revision_id !== source.knowledge_revision) return null
  const fields = { code:'',depth:0,sort_order:0,path_ids:[],path_names:[],aliases:[],learning_actions:[],typical_problems:[],block_ids:[],objective_ids:[],criterion_ids:[],question_ids:[],misconception_ids:[],skill_unit_ids:[],mistake_point_ids:[],improvement_ids:[],mastery_criterion_ids:[],source_status:'course_generated',source_bindings:[],status:'active',description:'' }
  const nodes:KnowledgeNode[] = (source.tree.categories || []).map(g=>({...fields,knowledge_id:g.id,parent_id:g.parent_id,node_type:'concept_group',name:g.name,section_ids:[],block_ids:[],covered_by_course:true,source_refs:[],revision_id:source.knowledge_revision}))
  for(const p of source.tree.knowledge_points) nodes.push({...fields,...p,node_type:'knowledge_point',description:p.statement,
    section_ids:(p.section_refs || [p.topic]).filter(id=>sectionIds.includes(id)),block_ids:[],covered_by_course:true,source_refs:p.source_refs || []})
  const relations = (source.tree.relations || []).map(r=>({relation_id:r.id,source_knowledge_id:r.source_id,target_knowledge_id:r.target_id,
    relation_type:r.type as KnowledgeLibraryView['relations'][number]['relation_type'],reason:r.reason,conditions:r.conditions,status:'accepted',source_status:'course_generated',source_refs:[],revision_id:source.knowledge_revision}))
  return { nodes,relations,lifecycle_status:'accepted',binding_revision_id:source.knowledge_revision,revision_id:source.knowledge_revision }
}

export function knowledgeFirstStudyExamples(source:KnowledgeFirstStudySource, library:CourseStudyLibrary) {
  const examples:Record<string,{example:string;exampleMarkdown:true}>={}
  for(const handout of source.handouts || []) {
    const revision=handout.revisions.find(r=>r.revision_id===handout.current_revision_id && r.source_knowledge_revision===source.knowledge_revision)
    for(const section of revision?.sections || []) for(const block of section.blocks || []) {
      if(!['concept','example'].includes(block.role)) continue
      for(const ref of block.knowledge_refs || []) {
        const point=library.nodes.find(n=>n.node_type==='knowledge_point' && n.knowledge_id===ref.knowledge_id && n.revision_id===ref.revision_id)
        if(!point) continue
        if(!point.block_ids.includes(block.block_id)) point.block_ids.push(block.block_id)
        if(block.role==='example' && block.content && !examples[point.knowledge_id]) examples[point.knowledge_id]={example:block.content,exampleMarkdown:true}
      }
    }
  }
  return examples
}
