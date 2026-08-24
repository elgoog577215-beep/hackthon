import { describe, expect, it } from 'vitest'
import { coursePreparationLabel, coursePreparationState } from '@/utils/course-preparation'

describe('course preparation projection', () => {
  it('只公开正在备课和备课完成两态', () => {
    expect(coursePreparationState({ course_status: 'draft', is_published: false })).toBe('preparing')
    expect(coursePreparationState({ is_published: true })).toBe('prepared')
    expect(coursePreparationState({ is_published: true }, { status: 'error' })).toBe('preparing')
    expect(coursePreparationState({ course_status: 'draft' }, { status: 'completed' })).toBe('prepared')
    expect(coursePreparationState({}, {
      status: 'completed_with_warnings',
      publicationAllowed: true,
    })).toBe('prepared')
    expect(new Set([
      coursePreparationLabel('preparing'),
      coursePreparationLabel('prepared'),
    ])).toEqual(new Set(['正在备课', '备课完成']))
  })
})
