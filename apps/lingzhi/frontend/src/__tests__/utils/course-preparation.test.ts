import { describe, expect, it } from 'vitest'
import { coursePreparationLabel, coursePreparationState } from '@/utils/course-preparation'

describe('course preparation projection', () => {
  it('只公开正在备课和备课完成两态', () => {
    expect(coursePreparationState({ course_status: 'draft', is_published: false })).toBe('preparing')
    expect(coursePreparationState({ is_published: true })).toBe('preparing')
    expect(coursePreparationState({ preparation_state: 'prepared', is_published: false })).toBe('prepared')
    expect(coursePreparationState({ preparation_state: 'prepared' }, { status: 'error' })).toBe('prepared')
    expect(coursePreparationState({ course_status: 'draft' }, { status: 'completed' })).toBe('preparing')
    expect(new Set([
      coursePreparationLabel('preparing'),
      coursePreparationLabel('prepared'),
    ])).toEqual(new Set(['备课中', '备课完成']))
  })
})
