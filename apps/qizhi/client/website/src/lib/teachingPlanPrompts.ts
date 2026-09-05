import type { ResourceResponse } from '../api/types'

const SKIP_HEADING = /^(目录|contents?|教学大纲|课程简介|参考文献|附录)/i

function cleanHeading(raw: string): string {
  return raw
    .trim()
    .replace(/\*+/g, '')
    .replace(/^第[一二三四五六七八九十百千\d]+[章节篇]\s*/i, '')
    .replace(/^\d+(\.\d+)*[\.\、]\s*/, '')
    .trim()
}

/** 从大纲 Markdown 正文中提取章节标题（用于生成教案预设提示） */
export function extractOutlineChapterTopics(content?: string | null): string[] {
  if (!content?.trim()) return []
  const topics: string[] = []
  const seen = new Set<string>()
  for (const line of content.split('\n')) {
    const m = line.match(/^#{1,3}\s+(.+)$/)
    if (!m?.[1]) continue
    const title = cleanHeading(m[1])
    if (!title || title.length > 48 || SKIP_HEADING.test(title)) continue
    if (seen.has(title)) continue
    seen.add(title)
    topics.push(title)
    if (topics.length >= 8) break
  }
  return topics
}

export function resolveOutlineCourseLabel(outline: ResourceResponse): string {
  const related = outline.related_course?.name?.trim()
  if (related) {
    return related.replace(/\s*[-—]?\s*教学大纲\s*$/i, '').trim() || related
  }
  const name = outline.name?.trim() || ''
  const fromName = name.replace(/\s*[-—]?\s*教学大纲\s*$/i, '').trim()
  if (fromName) return fromName
  const unit = outline.related_unit?.name?.trim()
  return unit || '本课程'
}

/** 基于当前大纲生成面向大学生的教案预设提示（最多 3 条） */
export function buildTeachingPlanPromptSuggestions(outline?: ResourceResponse | null): string[] {
  if (!outline) {
    return [
      '首章 90 分钟课堂教案（本科生：目标、重难点、课后作业）',
      '2 学时研讨课（案例讨论 + 形成性评价）',
      '完整章节教案（讲授 + 练习 + 总结）',
    ]
  }

  const course = resolveOutlineCourseLabel(outline)
  const topics = extractOutlineChapterTopics(outline.content)

  if (topics.length >= 2) {
    const last = topics[topics.length - 1]!
    return [
      `《${course}》「${topics[0]}」90 分钟课堂教案（目标 + 重难点）`,
      `「${topics[1]}」2 学时研讨课（案例讨论 + 评价）`,
      `「${last}」完整教案（互动 + 练习 + 拓展）`,
    ]
  }

  if (topics.length === 1) {
    const topic = topics[0]!
    return [
      `《${course}》「${topic}」90 分钟课堂教案（目标 + 重难点）`,
      `「${topic}」2 学时研讨课（小组讨论 + 评价）`,
      `「${topic}」完整教案（练习 + 总结环节）`,
    ]
  }

  return [
    `《${course}》首章 90 分钟课堂教案（目标 + 重难点）`,
    `《${course}》2 学时研讨课（案例 + 课堂互动）`,
    `《${course}》完整章节教案（讲授 + 练习 + 评价）`,
  ]
}
