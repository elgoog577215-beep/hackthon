export interface StudyRequest {
  kind: 'note' | 'explain'
  nodeId: string
  quote: string
  anchor?: Record<string, unknown>
  recordId?: string
  prompt?: string
  token?: number
}
export interface StudyWorkspace {
  kind: 'note' | 'explain'
  revision: number
  course_version_id: string
  node_id: string
  node_name: string
  quote: string
  anchor: Record<string, unknown>
  record_id: string
  saved_revision: number
  draft: string
  assisted: boolean
  solution_seen?: boolean
  proposal: string | null
  versions: Array<{ revision:number; content:string; assisted:boolean; saved_at:string }>
  nearby: Array<{ record_id:string; content:string; quote:string }>
  knowledge: Array<{ knowledge_id:string; revision_id:string; name:string; question:string }>
  checks: Array<{ knowledge_id:string; passed:boolean|null; confidence:number; feedback:string; support_level:number; solution_seen?:boolean; answer:string }>
}
