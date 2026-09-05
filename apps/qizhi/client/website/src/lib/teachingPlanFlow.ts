import { operateResource } from '../api/resource'
import { OperationEnum, ResourceTypeEnum, type ResourceResponse } from '../api/types'

export interface CreateTeachingPlanOptions {
  name: string
  relatedUserId?: string
  courseId?: string
  unitId?: string
  /** 父资源（大纲版本）ID，传入后教案挂在该大纲下成为其子版本 */
  parentResourceId?: string
}

/** 创建空教案资源并可选绑定课程章节/大纲版本 */
export async function createTeachingPlanResource(options: CreateTeachingPlanOptions): Promise<string> {
  // 课程/父资源直接随 create 提交：后端按所在作用域（大纲版本下或课程下）分配版本号
  const id = await operateResource({
    operation: OperationEnum.CREATE,
    name: options.name.trim() || '教案',
    resource_type: ResourceTypeEnum.TeachingPlan,
    editable: true,
    related_user_id: options.relatedUserId,
    related_course_id: options.courseId || null,
    related_unit_id: options.unitId || null,
    parent_resource_id: options.parentResourceId || null,
  })
  if (!id) throw new Error('创建成功但未返回资源 id')
  return id
}

export function resolveOutlineResourceBinding(outline: ResourceResponse): {
  courseId?: string
  unitId?: string
} {
  const courseId = outline.related_course?.id ?? outline.related_course_id ?? undefined
  const unitId = outline.related_unit?.id ?? outline.related_unit_id ?? undefined
  return {
    courseId: courseId != null ? String(courseId) : undefined,
    unitId: unitId != null ? String(unitId) : undefined,
  }
}

export function buildTeachingPlanNameFromOutline(outlineName?: string | null): string {
  const name = outlineName?.trim() || '教学大纲'
  return name.includes('教案') ? name : `${name} - 教案`
}

/** 依照大纲创建空教案：挂为该大纲版本的子资源，并绑定大纲关联的课程/章节 */
export async function createTeachingPlanFromOutline(
  outline: ResourceResponse,
  options?: {
    relatedUserId?: string
    /** 课程页可显式传入，覆盖大纲自身绑定课程 */
    courseId?: string
  }
): Promise<{ id: string; courseId?: string }> {
  const binding = resolveOutlineResourceBinding(outline)
  const courseId = options?.courseId ?? binding.courseId
  const id = await createTeachingPlanResource({
    name: buildTeachingPlanNameFromOutline(outline.name),
    relatedUserId: options?.relatedUserId,
    courseId,
    unitId: binding.unitId,
    parentResourceId: outline.id ? String(outline.id) : undefined,
  })
  return { id, courseId }
}

export function buildTeachingPlanFromOutlineQuery(
  outlineId: string,
  courseId?: string
): Record<string, string> {
  const query: Record<string, string> = {
    resourceType: ResourceTypeEnum.TeachingPlan,
    outline_id: outlineId,
  }
  if (courseId) query.from_course = courseId
  return query
}
