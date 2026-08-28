/**
 * 智能课程生成系统 - 共享提示词配置
 * 
 * 此文件用于前后端共享提示词系统的配置和类型定义
 * 确保前后端使用一致的参数、版本和验证规则
 * 
 * @version 1.0.0
 */

// =============================================================================
// 类型定义
// =============================================================================

/** 难度等级 */
export type DifficultyLevel = 'beginner' | 'intermediate' | 'advanced';

/** 旧节点级文案风格；仅用于历史接口兼容 */
export type TeachingStyle = 'academic' | 'industrial' | 'socratic' | 'humorous';

/** 课程块编排偏好 */
export type CourseCompositionStyle =
  | 'balanced'
  | 'theory_driven'
  | 'example_driven'
  | 'project_driven'
  | 'inquiry_driven';

/** 旧课程目标字段；保留 inquiry 只为读取历史课程。 */
export type CourseType = 'systematic' | 'project' | 'inquiry' | 'exam';

/** 学习目的：回答为什么学、最终要得到什么。 */
export type LearningPurpose = 'systematic' | 'project' | 'exam';

/** 课程教学类型：回答整门课主要怎样教。 */
export type CourseTeachingType =
  | 'theory'
  | 'laboratory'
  | 'practice'
  | 'seminar'
  | 'project'
  | 'comprehensive';

export interface SystematicCourseIntent {
  schema_version: 'course_intent_v1';
  type: 'systematic';
  learning_goal: string;
  desired_outcome?: string;
  existing_foundation?: string;
}

export interface ProjectCourseIntent {
  schema_version: 'course_intent_v1';
  type: 'project';
  project_goal: string;
  expected_deliverable: string;
  prior_experience?: string;
  current_uncertainty?: string;
  project_constraints?: string;
}

export interface InquiryCourseIntent {
  schema_version: 'course_intent_v1';
  type: 'inquiry';
  core_question: string;
  existing_understanding?: string;
  evidence_scope?: string;
  desired_output: string;
}

export interface ExamCourseIntent {
  schema_version: 'course_intent_v1';
  type: 'exam';
  exam_name: string;
  exam_date: string;
  exam_scope: string;
  current_preparation?: string;
}

export type CourseIntent =
  | SystematicCourseIntent
  | ProjectCourseIntent
  | InquiryCourseIntent
  | ExamCourseIntent;

/** 当前建课仅写入的课程目标；Inquiry 只留在历史数据转换器中读取。 */
export type CurrentCourseIntent =
  | SystematicCourseIntent
  | ProjectCourseIntent
  | ExamCourseIntent;

/** 学科类型：回答这门课主要通过什么学科行为来教学。 */
export type PedagogyMode =
  | 'general'
  | 'math_formal'
  | 'programming_engineering'
  | 'natural_science'
  | 'life_medical'
  | 'humanities_social'
  | 'language_learning'
  | 'business_career';

export type PedagogyModeSelection = 'auto' | PedagogyMode;
export type SecondaryIntensity = 'light' | 'collaborative' | 'dual_core';

/** 节点层级 */
export type NodeLevel = 1 | 2 | 3;

/** 节点类型 */
export type NodeType = 'original' | 'expanded' | 'redefined';

/** 学科类型 */
export type DisciplineType = 'natural_science' | 'humanities' | 'skill_based';

// =============================================================================
// 常量定义
// =============================================================================

/** 难度等级常量 */
export const DIFFICULTY_LEVELS = {
  BEGINNER: 'beginner' as const,
  INTERMEDIATE: 'intermediate' as const,
  ADVANCED: 'advanced' as const
};

/** 教学风格常量 */
export const TEACHING_STYLES = {
  ACADEMIC: 'academic' as const,
  INDUSTRIAL: 'industrial' as const,
  SOCRATIC: 'socratic' as const,
  HUMOROUS: 'humorous' as const
};

export const COURSE_COMPOSITION_STYLES = {
  BALANCED: 'balanced' as const,
  THEORY_DRIVEN: 'theory_driven' as const,
  EXAMPLE_DRIVEN: 'example_driven' as const,
  PROJECT_DRIVEN: 'project_driven' as const,
  INQUIRY_DRIVEN: 'inquiry_driven' as const,
};

export const COURSE_TYPES = {
  SYSTEMATIC: 'systematic' as const,
  PROJECT: 'project' as const,
  INQUIRY: 'inquiry' as const,
  EXAM: 'exam' as const,
};

export const LEARNING_PURPOSES = {
  SYSTEMATIC: 'systematic' as const,
  PROJECT: 'project' as const,
  EXAM: 'exam' as const,
};

export const COURSE_TEACHING_TYPES = {
  THEORY: 'theory' as const,
  LABORATORY: 'laboratory' as const,
  PRACTICE: 'practice' as const,
  SEMINAR: 'seminar' as const,
  PROJECT: 'project' as const,
  COMPREHENSIVE: 'comprehensive' as const,
};

export const PEDAGOGY_MODE_OPTIONS: Array<{
  value: PedagogyModeSelection;
  labelKey: string;
}> = [
  { value: 'auto', labelKey: 'courseGeneration.pedagogy.options.auto' },
  { value: 'general', labelKey: 'courseGeneration.pedagogy.options.general' },
  { value: 'math_formal', labelKey: 'courseGeneration.pedagogy.options.math_formal' },
  { value: 'programming_engineering', labelKey: 'courseGeneration.pedagogy.options.programming_engineering' },
  { value: 'natural_science', labelKey: 'courseGeneration.pedagogy.options.natural_science' },
  { value: 'life_medical', labelKey: 'courseGeneration.pedagogy.options.life_medical' },
  { value: 'humanities_social', labelKey: 'courseGeneration.pedagogy.options.humanities_social' },
  { value: 'language_learning', labelKey: 'courseGeneration.pedagogy.options.language_learning' },
  { value: 'business_career', labelKey: 'courseGeneration.pedagogy.options.business_career' },
];

/** 节点层级常量 */
export const NODE_LEVELS = {
  CHAPTER: 1 as const,      // L1: 章节
  SECTION: 2 as const,      // L2: 小节
  SUBSECTION: 3 as const    // L3: 子节（内容）
};

/** 节点类型常量 */
export const NODE_TYPES = {
  ORIGINAL: 'original' as const,    // 原始生成
  EXPANDED: 'expanded' as const,    // 扩展生成
  REDEFINED: 'redefined' as const   // 重定义
};

/** 学科类型常量 */
export const DISCIPLINE_TYPES = {
  NATURAL_SCIENCE: 'natural_science' as const,
  HUMANITIES: 'humanities' as const,
  SKILL_BASED: 'skill_based' as const
};

// =============================================================================
// 参数规则
// =============================================================================

/** 参数范围规则 */
export const PARAMETER_RULES = {
  /** 内容长度限制 */
  contentLength: {
    min: 100,      // 最少字符数
    max: 10000     // 最多字符数
  }
};

/** 有效的难度等级列表 */
export const VALID_DIFFICULTY_LEVELS: DifficultyLevel[] = [
  'beginner',
  'intermediate',
  'advanced'
];

/** 有效的教学风格列表 */
export const VALID_TEACHING_STYLES: TeachingStyle[] = [
  'academic',
  'industrial',
  'socratic',
  'humorous'
];

export const VALID_COURSE_COMPOSITION_STYLES: CourseCompositionStyle[] = [
  'balanced',
  'theory_driven',
  'example_driven',
  'project_driven',
  'inquiry_driven',
];

export const VALID_COURSE_TYPES: CourseType[] = [
  'systematic',
  'project',
  'inquiry',
  'exam',
];

export const VALID_LEARNING_PURPOSES: LearningPurpose[] = [
  'systematic',
  'project',
  'exam',
];

export const VALID_COURSE_TEACHING_TYPES: CourseTeachingType[] = [
  'theory',
  'laboratory',
  'practice',
  'seminar',
  'project',
  'comprehensive',
];

/** 有效的节点类型列表 */
export const VALID_NODE_TYPES: NodeType[] = [
  'original',
  'expanded',
  'redefined'
];

/** 有效的学科类型列表 */
export const VALID_DISCIPLINE_TYPES: DisciplineType[] = [
  'natural_science',
  'humanities',
  'skill_based'
];

// =============================================================================
// 提示词模板参数定义
// =============================================================================

/** 生成课程大纲参数 */
export interface CourseMaterialInput {
  filename: string;
  file_type?: string;
  user_description?: string;
  source_label?: string;
  usage: 'content_source' | 'style_reference' | 'question_source' | 'supplement' | 'weak_context';
  importance: 'core' | 'supporting' | 'weak';
  content?: string;
}

export interface CourseMaterialBindingInput {
  asset_id: string;
  purpose: 'content_source' | 'style_reference' | 'question_source' | 'supplement' | 'weak_context';
  priority: 'core' | 'supporting' | 'weak';
  authority: 'primary' | 'secondary' | 'context_only';
  usage_policy: 'must_use' | 'prefer' | 'optional' | 'style_only';
  reuse_policy: 'verbatim_allowed' | 'reference_only' | 'original_generation';
  rights_basis: 'teacher_asserted' | 'open_license' | 'license_unknown' | 'platform_owned';
  source_metadata: {
    year?: number;
    term?: string;
    exam_type?: string;
    source_url?: string;
  };
  user_description?: string;
  source_label?: string;
}

export interface CourseMaterialDraft extends Omit<CourseMaterialBindingInput, 'asset_id'> {
  local_id: string;
  asset_id?: string;
  filename: string;
  file_type?: string;
  file?: File;
  manual_content?: string;
  upload_status: 'pending' | 'uploading' | 'uploaded' | 'error';
  parse_status?: string;
  upload_error?: string;
}

export interface TeacherResourceRef {
  resource_id: string;
  resource_version_id?: string;
  label?: string;
  parse_status?: 'ready' | 'pending' | 'unavailable' | 'failed';
}

export interface TeacherCourseBriefV1 {
  schema_version: 'teacher_course_brief_v1';
  academic_term?: string;
  target_audience: string;
  total_class_hours: number;
  lesson_duration_minutes: number;
  /** 旧课程兼容字段；新教师工作台不再要求用户选择授课场景。 */
  teaching_context?: 'classroom' | 'online' | 'blended' | 'self_study';
  class_size?: number;
  class_profile?: string;
  chapter_count?: number;
  section_count?: number;
  additional_requirements?: string;
  material_refs?: TeacherResourceRef[];
}

export interface GenerateCourseParams {
  subject: string;
  request_id?: string;
  target_course_id?: string;
  difficulty: DifficultyLevel;
  learning_purpose: LearningPurpose;
  course_teaching_type: CourseTeachingType;
  course_intent: CurrentCourseIntent;
  target_audience?: string;
  teacher_course_brief?: TeacherCourseBriefV1;
  requirements?: string;
  materials?: CourseMaterialInput[];
  material_bindings?: CourseMaterialBindingInput[];
  grounding_strategy?: 'strict_grounded' | 'material_first' | 'general_assisted';
  learner_profile_summary?: string;
  current_readiness?: 'none' | DifficultyLevel;
  adaptation_preference?: 'preserve_target_extend' | 'split_foundation' | 'fast_track' | 'lower_target';
  pedagogy_mode?: PedagogyModeSelection;
  secondary_mode?: PedagogyMode;
  secondary_intensity?: SecondaryIntensity;
  generation_mode?: 'fast' | 'review_blueprint';
  production_mode?: 'manual' | 'automatic';
  teacher_authoring_mode?: 'lesson_assets_v1';
  asset_preferences?: Record<string, boolean>;
  web_question_enrichment?: {
    mode?: 'auto_on_gap' | 'off' | 'always';
    enabled?: boolean;
  };
  /** 联网研究授权；检索开关与策略由团队检索网关拥有。 */
  retrieval?: {
    enabled: boolean;
  };
  /** 联网结果落成资料资产时的取舍；不承载检索配置。 */
  web_material_ingest?: {
    skip_ingest?: boolean;
    excluded_source_ids?: string[];
    excluded_urls?: string[];
  };
}

/**
 * 页面之间传递的建课选项。旧字段只为读取已有课程和任务，
 * 新页面提交前必须经过 canonicalizeCourseGenerationOptions。
 */
export type CourseGenerationOptions = Partial<Omit<GenerateCourseParams, 'subject' | 'course_intent'>> & {
  course_intent?: CourseIntent;
  course_type?: CourseType;
  course_purpose?: 'systematic' | 'exam_sprint' | 'material_organization' | 'personalized_remedial';
  composition_style?: CourseCompositionStyle;
  style?: TeachingStyle;
};

/**
 * Read an old generation request once and return the current three-part
 * teaching contract. New UI code must send the returned object instead of
 * copying legacy classification fields forward.
 */
export function canonicalizeCourseGenerationOptions(
  value: CourseGenerationOptions | Record<string, unknown> | undefined,
): CourseGenerationOptions {
  const raw = { ...(value || {}) } as Record<string, any>
  const intent = raw.course_intent && typeof raw.course_intent === 'object'
    ? { ...raw.course_intent }
    : {}
  const legacyType = String(raw.course_type || intent.type || '')
  const learningPurpose = VALID_LEARNING_PURPOSES.includes(raw.learning_purpose)
    ? raw.learning_purpose as LearningPurpose
    : legacyType === 'project'
      ? 'project'
      : legacyType === 'exam' || raw.course_purpose === 'exam_sprint'
        ? 'exam'
        : 'systematic'
  const courseTeachingType = VALID_COURSE_TEACHING_TYPES.includes(raw.course_teaching_type)
    ? raw.course_teaching_type as CourseTeachingType
    : legacyType === 'project' || raw.composition_style === 'project_driven'
      ? 'project'
      : legacyType === 'inquiry' || raw.composition_style === 'inquiry_driven'
        ? 'seminar'
        : raw.composition_style === 'theory_driven'
          ? 'theory'
          : 'comprehensive'

  let courseIntent: CourseIntent
  if (learningPurpose === 'project') {
    courseIntent = {
      schema_version: 'course_intent_v1',
      type: 'project',
      project_goal: String(intent.project_goal || raw.subject || raw.requirements || ''),
      expected_deliverable: String(intent.expected_deliverable || ''),
      prior_experience: String(intent.prior_experience || ''),
      current_uncertainty: String(intent.current_uncertainty || ''),
      project_constraints: String(intent.project_constraints || raw.requirements || ''),
    }
  } else if (learningPurpose === 'exam') {
    courseIntent = {
      schema_version: 'course_intent_v1',
      type: 'exam',
      exam_name: String(intent.exam_name || raw.subject || ''),
      exam_date: String(intent.exam_date || ''),
      exam_scope: String(intent.exam_scope || raw.requirements || ''),
      current_preparation: String(intent.current_preparation || ''),
    }
  } else {
    const inquiryGoal = [intent.core_question, intent.desired_output]
      .map(item => String(item || '').trim())
      .filter(Boolean)
      .join('；')
    courseIntent = {
      schema_version: 'course_intent_v1',
      type: 'systematic',
      learning_goal: String(intent.learning_goal || inquiryGoal || raw.subject || raw.requirements || ''),
      desired_outcome: String(intent.desired_outcome || ''),
      existing_foundation: String(intent.existing_foundation || intent.existing_understanding || ''),
    }
  }

  raw.learning_purpose = learningPurpose
  raw.course_teaching_type = courseTeachingType
  raw.course_intent = courseIntent
  delete raw.course_type
  delete raw.course_purpose
  delete raw.composition_style
  return raw as CourseGenerationOptions
}

// =============================================================================
// 验证函数
// =============================================================================

export interface ValidationResult {
  valid: boolean;
  errors: string[];
}

/**
 * 验证难度等级
 */
export function validateDifficulty(difficulty: string): boolean {
  return VALID_DIFFICULTY_LEVELS.includes(difficulty as DifficultyLevel);
}

/**
 * 验证教学风格
 */
export function validateStyle(style: string): boolean {
  return VALID_TEACHING_STYLES.includes(style as TeachingStyle);
}

export function validateCompositionStyle(style: string): boolean {
  return VALID_COURSE_COMPOSITION_STYLES.includes(style as CourseCompositionStyle);
}

export function validateCourseType(courseType: string): boolean {
  return VALID_COURSE_TYPES.includes(courseType as CourseType);
}

export function validateLearningPurpose(value: string): boolean {
  return VALID_LEARNING_PURPOSES.includes(value as LearningPurpose);
}

export function validateCourseTeachingType(value: string): boolean {
  return VALID_COURSE_TEACHING_TYPES.includes(value as CourseTeachingType);
}

/**
 * 验证节点类型
 */
export function validateNodeType(nodeType: string): boolean {
  return VALID_NODE_TYPES.includes(nodeType as NodeType);
}

/**
 * 验证学科类型
 */
export function validateDisciplineType(disciplineType: string): boolean {
  return VALID_DISCIPLINE_TYPES.includes(disciplineType as DisciplineType);
}

/**
 * 验证生成课程参数
 */
export function validateGenerateCourseParams(
  params: Partial<GenerateCourseParams>
): ValidationResult {
  const errors: string[] = [];
  const raw = params as Partial<GenerateCourseParams> & Record<string, unknown>;
  
  if (!params.subject || params.subject.trim().length === 0) {
    errors.push('subject is required and cannot be empty');
  }
  
  if (!params.difficulty) {
    errors.push('difficulty is required');
  } else if (!validateDifficulty(params.difficulty)) {
    errors.push(`Invalid difficulty: ${params.difficulty}. Must be one of: ${VALID_DIFFICULTY_LEVELS.join(', ')}`);
  }
  
  if (!params.learning_purpose) {
    errors.push('learning_purpose is required');
  } else if (!validateLearningPurpose(params.learning_purpose)) {
    errors.push(`Invalid learning_purpose: ${params.learning_purpose}. Must be one of: ${VALID_LEARNING_PURPOSES.join(', ')}`);
  }

  if (!params.course_teaching_type) {
    errors.push('course_teaching_type is required');
  } else if (!validateCourseTeachingType(params.course_teaching_type)) {
    errors.push(`Invalid course_teaching_type: ${params.course_teaching_type}. Must be one of: ${VALID_COURSE_TEACHING_TYPES.join(', ')}`);
  }

  for (const legacyField of ['course_type', 'course_purpose', 'composition_style'] as const) {
    if (raw[legacyField] !== undefined) errors.push(`${legacyField} is legacy-only; convert it before validation`);
  }

  if (!params.course_intent) {
    errors.push('course_intent is required');
  } else if (params.learning_purpose && params.course_intent.type !== params.learning_purpose) {
    errors.push('course_intent.type must match learning_purpose');
  }

  if (params.learning_purpose === 'project') {
    const project = params.course_intent?.type === 'project' ? params.course_intent : null;
    if (!project) {
      errors.push('a project course_intent is required when learning_purpose is project');
    } else {
      const requiredProjectFields: Array<keyof ProjectCourseIntent> = [
        'project_goal',
        'expected_deliverable',
      ];
      for (const field of requiredProjectFields) {
        if (!project[field]?.trim()) errors.push(`course_intent.${field} is required`);
      }
    }
  }

  if (params.learning_purpose === 'exam') {
    const exam = params.course_intent?.type === 'exam' ? params.course_intent : null;
    if (!exam) {
      errors.push('an exam course_intent is required when learning_purpose is exam');
    } else {
      for (const field of ['exam_name', 'exam_date', 'exam_scope'] as const) {
        if (!exam[field]?.trim()) errors.push(`course_intent.${field} is required`);
      }
      if (exam.exam_date && !/^\d{4}-\d{2}-\d{2}$/.test(exam.exam_date)) {
        errors.push('course_intent.exam_date must use YYYY-MM-DD format');
      }
    }
  }

  if (params.learning_purpose === 'systematic') {
    const systematic = params.course_intent?.type === 'systematic' ? params.course_intent : null;
    if (!systematic?.learning_goal.trim()) errors.push('course_intent.learning_goal is required');
  }

  const teacherBrief = params.teacher_course_brief;
  if (teacherBrief) {
    if (!teacherBrief.target_audience.trim()) errors.push('teacher_course_brief.target_audience is required');
    if (!Number.isInteger(teacherBrief.total_class_hours) || teacherBrief.total_class_hours < 1 || teacherBrief.total_class_hours > 1000) {
      errors.push('teacher_course_brief.total_class_hours must be an integer between 1 and 1000');
    }
    if (!Number.isInteger(teacherBrief.lesson_duration_minutes) || teacherBrief.lesson_duration_minutes < 20 || teacherBrief.lesson_duration_minutes > 240) {
      errors.push('teacher_course_brief.lesson_duration_minutes must be an integer between 20 and 240');
    }
  }
  
  return {
    valid: errors.length === 0,
    errors
  };
}

// =============================================================================
// 智能建议配置
// =============================================================================

/** 建议项类型 */
export interface SuggestionItem {
  text: string;
  type: string;
}

/** 上下文建议模式 */
export interface ContextSuggestionPattern {
  keywords: string[];
  template: string;
  type: string;
}

/** 通用智能建议 */
export const SMART_SUGGESTIONS = {
  general: [
    { text: '请帮我总结一下本章的核心概念', type: 'summary' },
    { text: '这个概念在实际项目中如何应用？', type: 'application' },
    { text: '能否用更通俗的方式解释一下？', type: 'explanation' },
    { text: '给我一些相关的练习题', type: 'practice' },
    { text: '这部分内容与其他章节有什么联系？', type: 'connection' }
  ] as SuggestionItem[],
  context: {
    maxSuggestions: 3,
    patterns: [
      {
        keywords: ['算法', 'algorithm', '复杂度', 'complexity'],
        template: '请详细讲解{nodeName}的时间复杂度分析',
        type: 'technical'
      },
      {
        keywords: ['公式', 'formula', '推导', 'proof'],
        template: '能否给出{nodeName}的完整推导过程？',
        type: 'technical'
      },
      {
        keywords: ['代码', 'code', '实现', 'implementation'],
        template: '请展示{nodeName}的代码实现示例',
        type: 'practical'
      },
      {
        keywords: ['架构', 'architecture', '设计', 'design'],
        template: '{nodeName}的架构设计有哪些关键点？',
        type: 'conceptual'
      },
      {
        keywords: ['优化', 'optimization', '性能', 'performance'],
        template: '如何优化{nodeName}的性能？',
        type: 'practical'
      }
    ] as ContextSuggestionPattern[]
  }
};

/** 上下文建议模式（便捷导出） */
export const CONTEXT_SUGGESTION_PATTERNS = SMART_SUGGESTIONS.context.patterns;

/** 基于内容类型的建议模板 */
export const CONTEXT_SUGGESTION_TEMPLATES = {
  definition: (concept: string) => `"${concept}"的核心定义是什么？`,
  formula: () => '这个公式的适用条件是什么？',
  process: () => '能梳理一下操作步骤吗？',
  example: () => '还有类似的例子吗？',
  keypoints: (concept: string) => `关于"${concept}"的重点有哪些？`,
  comparison: (concept: string) => `"${concept}"与其他相关概念有什么区别？`,
  application: () => '这个知识在实际中如何应用？',
  principle: () => '背后的原理是什么？'
};

/** 内容类型检测关键词 */
export const CONTENT_TYPE_KEYWORDS = {
  definition: ['定义', '概念', '什么是', '指'],
  formula: ['公式', '计算', '方程', '定理', '定律'],
  process: ['步骤', '流程', '过程', '方法', '算法'],
  example: ['例子', '案例', '示例', '比如', '例如'],
  comparison: ['区别', '对比', '比较', 'vs', 'versus'],
  application: ['应用', '使用', '实践', '实现', '运用'],
  principle: ['原理', '机制', '为什么', '原因']
};

/**
 * 检测内容类型
 */
export function detectContentTypes(content: string): string[] {
  const types: string[] = [];
  const lowerContent = content.toLowerCase();
  
  for (const [type, keywords] of Object.entries(CONTENT_TYPE_KEYWORDS)) {
    if (keywords.some(keyword => lowerContent.includes(keyword))) {
      types.push(type);
    }
  }
  
  return types;
}

/**
 * 生成上下文建议
 */
export function generateContextSuggestions(
  nodeName: string,
  content: string
): Array<{ text: string; type: string }> {
  const suggestions: Array<{ text: string; type: string }> = [];
  const contentTypes = detectContentTypes(content);
  
  for (const type of contentTypes.slice(0, 3)) {
    const template = CONTEXT_SUGGESTION_TEMPLATES[type as keyof typeof CONTEXT_SUGGESTION_TEMPLATES];
    if (template) {
      suggestions.push({
        text: template(nodeName),
        type
      });
    }
  }
  
  // 始终添加一个通用建议
  suggestions.push({
    text: CONTEXT_SUGGESTION_TEMPLATES.keypoints(nodeName),
    type: 'keypoints'
  });
  
  return suggestions.slice(0, 3);
}

// =============================================================================
// 导出默认配置
// =============================================================================

export default {
  DIFFICULTY_LEVELS,
  TEACHING_STYLES,
  NODE_LEVELS,
  NODE_TYPES,
  DISCIPLINE_TYPES,
  PARAMETER_RULES,
  VALID_DIFFICULTY_LEVELS,
  VALID_TEACHING_STYLES,
  VALID_NODE_TYPES,
  VALID_DISCIPLINE_TYPES,
  SMART_SUGGESTIONS,
  CONTEXT_SUGGESTION_TEMPLATES,
  CONTENT_TYPE_KEYWORDS
};
