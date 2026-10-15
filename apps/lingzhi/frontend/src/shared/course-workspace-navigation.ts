export type WorkspaceStage = 'foundation' | 'lesson' | 'script' | 'ppt' | 'question-bank' | 'companion'
export interface WorkspaceLocation {
  view: 'categories' | 'files'
  stage: WorkspaceStage
  lessonId: string
  knowledge: boolean
  companionTemplateId?: string
}
const stages: WorkspaceStage[] = ['foundation', 'lesson', 'script', 'ppt', 'question-bank', 'companion']
const single = (value: unknown) => typeof value === 'string' ? value : ''

export function readWorkspaceLocation(query: Record<string, unknown>): WorkspaceLocation {
  const stage = single(query.stage)
  return {
    view: query.view === 'files' ? 'files' : 'categories',
    stage: stages.includes(stage as WorkspaceStage) ? stage as WorkspaceStage : stage === 'knowledge' ? 'script' : 'foundation',
    lessonId: single(query.lesson),
    knowledge: stage === 'knowledge',
    companionTemplateId: single(query.template),
  }
}

export function workspaceLocationQuery(query: Record<string, unknown>, location: WorkspaceLocation) {
  const result = { ...query }
  const previous = readWorkspaceLocation(query)
  for (const key of ['section', 'generate']) delete result[key]
  if (previous.stage !== location.stage || previous.knowledge !== location.knowledge || (previous.lessonId && previous.lessonId !== location.lessonId)) {
    for (const key of ['issue', 'block', 'task', 'expandIssue']) delete result[key]
  }
  if (location.view === 'files') result.view = 'files'
  else delete result.view
  result.stage = location.knowledge ? 'knowledge' : location.stage
  if (location.lessonId && (location.knowledge || ['lesson', 'script', 'ppt', 'question-bank'].includes(location.stage))) result.lesson = location.lessonId
  else delete result.lesson
  if (location.stage === 'companion' && location.companionTemplateId) result.template = location.companionTemplateId
  else delete result.template
  return result
}
