/**
 * prompt-config 验证规则测试
 * 测试共享配置中的验证函数和常量一致性
 */
import { describe, it, expect } from 'vitest'
import {
  validateDifficulty,
  validateStyle,
  validateCompositionStyle,
  validateCourseType,
  validateLearningPurpose,
  validateCourseTeachingType,
  validateNodeType,
  validateGenerateCourseParams,
  canonicalizeCourseGenerationOptions,
  detectContentTypes,
  generateContextSuggestions,
  VALID_DIFFICULTY_LEVELS,
  VALID_TEACHING_STYLES,
  VALID_COURSE_COMPOSITION_STYLES,
  VALID_COURSE_TYPES,
  VALID_LEARNING_PURPOSES,
  VALID_COURSE_TEACHING_TYPES,
  VALID_NODE_TYPES,
  PARAMETER_RULES,
  DIFFICULTY_LEVELS,
  TEACHING_STYLES,
  COURSE_COMPOSITION_STYLES,
  COURSE_TYPES,
  LEARNING_PURPOSES,
  COURSE_TEACHING_TYPES,
  NODE_LEVELS,
  NODE_TYPES,
} from '@/shared/prompt-config'

// ---------------------------------------------------------------------------
// 常量一致性
// ---------------------------------------------------------------------------

describe('常量定义', () => {
  it('难度等级常量与有效列表一致', () => {
    const values = Object.values(DIFFICULTY_LEVELS)
    expect(values).toEqual(VALID_DIFFICULTY_LEVELS)
  })

  it('教学风格常量与有效列表一致', () => {
    const values = Object.values(TEACHING_STYLES)
    expect(values).toEqual(VALID_TEACHING_STYLES)
  })

  it('课程编排偏好常量与有效列表一致', () => {
    const values = Object.values(COURSE_COMPOSITION_STYLES)
    expect(values).toEqual(VALID_COURSE_COMPOSITION_STYLES)
  })

  it('课程类型常量与有效列表一致', () => {
    expect(Object.values(COURSE_TYPES)).toEqual(VALID_COURSE_TYPES)
  })

  it('学习目的与课程教学类型分别维护稳定列表', () => {
    expect(Object.values(LEARNING_PURPOSES)).toEqual(VALID_LEARNING_PURPOSES)
    expect(Object.values(COURSE_TEACHING_TYPES)).toEqual(VALID_COURSE_TEACHING_TYPES)
  })

  it('节点类型常量与有效列表一致', () => {
    const values = Object.values(NODE_TYPES)
    expect(values).toEqual(VALID_NODE_TYPES)
  })

  it('节点层级为 1/2/3', () => {
    expect(NODE_LEVELS.CHAPTER).toBe(1)
    expect(NODE_LEVELS.SECTION).toBe(2)
    expect(NODE_LEVELS.SUBSECTION).toBe(3)
  })
})


// ---------------------------------------------------------------------------
// 基础验证函数
// ---------------------------------------------------------------------------

describe('validateDifficulty', () => {
  it('接受有效难度等级', () => {
    expect(validateDifficulty('beginner')).toBe(true)
    expect(validateDifficulty('intermediate')).toBe(true)
    expect(validateDifficulty('advanced')).toBe(true)
  })

  it('拒绝无效难度等级', () => {
    expect(validateDifficulty('expert')).toBe(false)
    expect(validateDifficulty('')).toBe(false)
    expect(validateDifficulty('BEGINNER')).toBe(false)
  })
})

describe('validateStyle', () => {
  it('接受有效教学风格', () => {
    expect(validateStyle('academic')).toBe(true)
    expect(validateStyle('industrial')).toBe(true)
    expect(validateStyle('socratic')).toBe(true)
    expect(validateStyle('humorous')).toBe(true)
  })

  it('拒绝无效教学风格', () => {
    expect(validateStyle('casual')).toBe(false)
    expect(validateStyle('')).toBe(false)
  })
})

describe('validateCompositionStyle', () => {
  it('接受五种课程编排偏好并拒绝旧文案风格', () => {
    for (const style of VALID_COURSE_COMPOSITION_STYLES) {
      expect(validateCompositionStyle(style)).toBe(true)
    }
    expect(validateCompositionStyle('academic')).toBe(false)
    expect(validateCompositionStyle('casual')).toBe(false)
  })
})

describe('validateCourseType', () => {
  it('旧课程类型字段继续接受四种兼容值', () => {
    for (const courseType of VALID_COURSE_TYPES) expect(validateCourseType(courseType)).toBe(true)
    expect(validateCourseType('material_organization')).toBe(false)
  })
})

describe('validateTeachingSemantics', () => {
  it('只接受三种学习目的与六种课程教学类型', () => {
    for (const value of VALID_LEARNING_PURPOSES) expect(validateLearningPurpose(value)).toBe(true)
    for (const value of VALID_COURSE_TEACHING_TYPES) expect(validateCourseTeachingType(value)).toBe(true)
    expect(validateLearningPurpose('inquiry')).toBe(false)
    expect(validateCourseTeachingType('exam')).toBe(false)
  })
})

describe('validateNodeType', () => {
  it('接受有效节点类型', () => {
    expect(validateNodeType('original')).toBe(true)
    expect(validateNodeType('expanded')).toBe(true)
    expect(validateNodeType('redefined')).toBe(true)
  })

  it('拒绝无效节点类型', () => {
    expect(validateNodeType('custom')).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// 数值范围验证
// ---------------------------------------------------------------------------

describe('课程结构不再按难度硬编数量', () => {
  it('不提供章节数、子节数和公式密度难度映射', () => {
    expect(PARAMETER_RULES).not.toHaveProperty('chapterCount')
    expect(PARAMETER_RULES).not.toHaveProperty('subChapterCount')
    expect(PARAMETER_RULES).not.toHaveProperty('formulaDensity')
  })
})

// ---------------------------------------------------------------------------
// 复合参数验证
// ---------------------------------------------------------------------------

describe('validateGenerateCourseParams', () => {
  const validParams = {
    subject: '机器学习',
    difficulty: 'intermediate' as const,
    learning_purpose: 'systematic' as const,
    course_teaching_type: 'comprehensive' as const,
    course_intent: {
      schema_version: 'course_intent_v1' as const,
      type: 'systematic' as const,
      learning_goal: '理解机器学习的核心概念',
    },
  }

  it('有效参数返回 valid: true', () => {
    const result = validateGenerateCourseParams(validParams)
    expect(result.valid).toBe(true)
    expect(result.errors).toHaveLength(0)
  })

  it('缺少 subject 返回错误', () => {
    const result = validateGenerateCourseParams({ ...validParams, subject: '' })
    expect(result.valid).toBe(false)
    expect(result.errors.length).toBeGreaterThan(0)
  })

  it('无效 difficulty 返回错误', () => {
    const result = validateGenerateCourseParams({ ...validParams, difficulty: 'expert' as any })
    expect(result.valid).toBe(false)
  })

  it('无效学习目的和课程教学类型返回错误', () => {
    const result = validateGenerateCourseParams({
      ...validParams,
      learning_purpose: 'inquiry' as any,
      course_teaching_type: 'exam' as any,
    })
    expect(result.valid).toBe(false)
    expect(result.errors.join(' ')).toContain('Invalid learning_purpose')
    expect(result.errors.join(' ')).toContain('Invalid course_teaching_type')
  })

  it('当前请求不允许继续写入旧分类字段', () => {
    const result = validateGenerateCourseParams({ ...validParams, course_type: 'systematic' } as any)
    expect(result.valid).toBe(false)
    expect(result.errors.join(' ')).toContain('course_type is legacy-only')
  })

  it('项目实战只要求项目目标与交付成果，自述起点允许留空', () => {
    const result = validateGenerateCourseParams({
      ...validParams,
      learning_purpose: 'project',
      course_teaching_type: 'project',
      course_intent: {
        schema_version: 'course_intent_v1',
        type: 'project',
        project_goal: '制作个人网站',
        expected_deliverable: '可部署的网站',
        prior_experience: '会 HTML',
        current_uncertainty: '',
      },
    })
    expect(result.valid).toBe(true)
    expect(result.errors).toHaveLength(0)
  })

  it('考试冲刺校验专用规划输入', () => {
    const exam = validateGenerateCourseParams({
      ...validParams,
      learning_purpose: 'exam',
      course_teaching_type: 'practice',
      course_intent: {
        schema_version: 'course_intent_v1',
        type: 'exam',
        exam_name: '大学英语六级考试',
        exam_date: '2026-12-20',
        exam_scope: '听力、阅读、翻译与写作',
      },
    })
    const incompleteExam = validateGenerateCourseParams({
      ...validParams,
      learning_purpose: 'exam',
      course_teaching_type: 'practice',
      course_intent: {
        schema_version: 'course_intent_v1',
        type: 'exam',
        exam_name: '大学英语六级考试',
        exam_date: '',
        exam_scope: '',
      },
    })

    expect(exam.valid).toBe(true)
    expect(incompleteExam.errors).toEqual(expect.arrayContaining([
      'course_intent.exam_date is required',
      'course_intent.exam_scope is required',
    ]))
  })

  it('历史问题探究会被转成系统学习与研讨课，且不延续旧字段', () => {
    const result = canonicalizeCourseGenerationOptions({
      course_type: 'inquiry',
      composition_style: 'inquiry_driven',
      course_intent: {
        schema_version: 'course_intent_v1',
        type: 'inquiry',
        core_question: '生成式 AI 会如何改变大学评价？',
        desired_output: '带证据边界的判断报告',
      },
    })
    expect(result.learning_purpose).toBe('systematic')
    expect(result.course_teaching_type).toBe('seminar')
    expect(result.course_intent).toMatchObject({
      type: 'systematic',
      learning_goal: '生成式 AI 会如何改变大学评价？；带证据边界的判断报告',
    })
    expect(result).not.toHaveProperty('course_type')
    expect(result).not.toHaveProperty('composition_style')
  })

  it('空对象返回多个错误', () => {
    const result = validateGenerateCourseParams({})
    expect(result.valid).toBe(false)
    expect(result.errors.length).toBeGreaterThanOrEqual(3)
  })
})

// ---------------------------------------------------------------------------
// 内容类型检测与上下文建议
// ---------------------------------------------------------------------------

describe('detectContentTypes', () => {
  it('检测定义类内容', () => {
    const types = detectContentTypes('什么是机器学习？机器学习的定义是...')
    expect(types).toContain('definition')
  })

  it('检测公式类内容', () => {
    const types = detectContentTypes('根据公式计算结果')
    expect(types).toContain('formula')
  })

  it('检测多种类型', () => {
    const types = detectContentTypes('定义：根据公式推导步骤如下')
    expect(types).toContain('definition')
    expect(types).toContain('formula')
    expect(types).toContain('process')
  })

  it('无匹配时返回空数组', () => {
    const types = detectContentTypes('Hello World')
    expect(types).toHaveLength(0)
  })
})

describe('generateContextSuggestions', () => {
  it('返回不超过 3 条建议', () => {
    const suggestions = generateContextSuggestions('线性代数', '定义：公式推导步骤案例')
    expect(suggestions.length).toBeLessThanOrEqual(3)
  })

  it('始终包含 keypoints 类型建议', () => {
    const suggestions = generateContextSuggestions('测试节点', '普通内容')
    const types = suggestions.map(s => s.type)
    expect(types).toContain('keypoints')
  })

  it('建议文本包含节点名称', () => {
    const suggestions = generateContextSuggestions('神经网络', '定义概念')
    const hasNodeName = suggestions.some(s => s.text.includes('神经网络'))
    expect(hasNodeName).toBe(true)
  })
})
