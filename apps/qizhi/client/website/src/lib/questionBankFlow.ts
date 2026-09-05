import { operateResource } from '../api/resource'
import { OperationEnum, ResourceTypeEnum, type ResourceResponse } from '../api/types'
import { resolveOutlineResourceBinding } from './teachingPlanFlow'

export interface CreateQuestionBankOptions {
  name: string
  relatedUserId?: string
  courseId?: string
  unitId?: string
  /** 父资源（大纲/教案版本）ID，传入后习题集挂在其下成为子版本 */
  parentResourceId?: string
}

/** 创建空习题集资源并可选绑定课程章节/父资源版本 */
export async function createQuestionBankResource(options: CreateQuestionBankOptions): Promise<string> {
  // 课程/父资源直接随 create 提交：后端按所在作用域分配版本号
  const id = await operateResource({
    operation: OperationEnum.CREATE,
    name: options.name.trim() || '题目',
    resource_type: ResourceTypeEnum.QuestionBank,
    editable: true,
    related_user_id: options.relatedUserId,
    related_course_id: options.courseId || null,
    related_unit_id: options.unitId || null,
    parent_resource_id: options.parentResourceId || null,
  })
  if (!id) throw new Error('创建成功但未返回资源 id')
  return id
}

export function buildQuestionBankNameFromTeachingPlan(planName?: string | null): string {
  const name = planName?.trim() || '教案'
  return name.includes('题目') ? name : `${name} - 题目`
}

/** 依照教案创建空习题集：挂为该教案版本的子资源，并绑定教案关联的课程/章节 */
export async function createQuestionBankFromTeachingPlan(
  teachingPlan: ResourceResponse,
  options?: {
    relatedUserId?: string
    courseId?: string
  }
): Promise<{ id: string; courseId?: string }> {
  const binding = resolveOutlineResourceBinding(teachingPlan)
  const courseId = options?.courseId ?? binding.courseId
  const id = await createQuestionBankResource({
    name: buildQuestionBankNameFromTeachingPlan(teachingPlan.name),
    relatedUserId: options?.relatedUserId,
    courseId,
    unitId: binding.unitId,
    parentResourceId: teachingPlan.id ? String(teachingPlan.id) : undefined,
  })
  return { id, courseId }
}

/** outline_id 为历史参数名，此处表示参考教案 id */
export function buildQuestionBankFromTeachingPlanQuery(
  teachingPlanId: string,
  courseId?: string
): Record<string, string> {
  const query: Record<string, string> = {
    resourceType: ResourceTypeEnum.QuestionBank,
    outline_id: teachingPlanId,
  }
  if (courseId) query.from_course = courseId
  return query
}
