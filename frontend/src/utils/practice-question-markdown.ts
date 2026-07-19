interface PracticeQuestionMarkdownSource {
  prompt?: unknown
  input_materials?: unknown
}

export interface PracticeQuestionMarkdownSections {
  task: string
  stimulus: string
  material: string
}

const INLINE_STIMULUS_LIMIT = 1200

const looksLikeCourseMaterial = (content: string) => (
  /^(?:给定课程材料|课程原文|缁欏畾璇剧▼鏉愭枡|浣庣疆淇¤绋嬭儗鏅?)/u
    .test(content.trim())
  || content.includes('<!-- BODY_START -->')
)

const looksLikeCodeLine = (line: string) => (
  /^\s*(?:class|def|async\s+def|from|import|for|while|if|elif|else|try|except|finally|with|return|yield|raise|del|const|let|var|function|interface|type)\b/.test(line)
  || /^\s*[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*\s*=(?!=)/.test(line)
  || /^\s*(?:print|console\.log)\s*\(/.test(line)
  || /^\s{2,}\S/.test(line)
)

const fenceBareCode = (content: string) => {
  if (/^\s*(`{3,}|~{3,})/m.test(content)) return content
  const lines = content.split('\n')
  const codeIndexes = lines
    .map((line, index) => (looksLikeCodeLine(line) ? index : -1))
    .filter(index => index >= 0)
  if (codeIndexes.length < 2) return content

  const start = codeIndexes[0] ?? 0
  const end = codeIndexes[codeIndexes.length - 1] ?? start
  const language = lines
    .slice(start, end + 1)
    .some(line => /\b(?:const|let|var|function|console\.log)\b/.test(line))
    ? 'javascript'
    : 'python'
  return [
    ...lines.slice(0, start),
    `\`\`\`${language}`,
    ...lines.slice(start, end + 1),
    '```',
    ...lines.slice(end + 1),
  ].join('\n')
}

const stripInternalComments = (content: string) => (
  content
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
)

const closeUnterminatedFence = (content: string) => {
  const fences = Array.from(
    content.matchAll(/^\s*(`{3,}|~{3,})[^\n]*$/gm),
  )
  if (fences.length % 2 === 0) return content
  const marker = fences[fences.length - 1]?.[1] || '```'
  return `${content}\n${marker[0]?.repeat(Math.max(3, marker.length)) || '```'}`
}

const stripMaterialLabel = (content: string) => (
  content
    .replace(/^(?:给定课程材料|低置信课程背景)[：:]\s*/u, '')
    .trim()
)

export const splitPracticeQuestionMarkdown = (
  value: unknown,
): PracticeQuestionMarkdownSections => {
  const question = (
    value && typeof value === 'object'
      ? value
      : null
  ) as PracticeQuestionMarkdownSource | null
  const prompt = String(question?.prompt || '').trim()
  if (!prompt) return { task: '', stimulus: '', material: '' }

  const inputMaterials = Array.isArray(question?.input_materials)
    ? question.input_materials
    : []
  const material = inputMaterials.find(
    value => typeof value === 'string' && value.trim(),
  )

  if (typeof material !== 'string' || !prompt.startsWith(material)) {
    return {
      task: closeUnterminatedFence(stripInternalComments(prompt)),
      stimulus: '',
      material: '',
    }
  }

  const renderedMaterial = closeUnterminatedFence(
    fenceBareCode(stripInternalComments(material)),
  )
  const task = stripInternalComments(prompt.slice(material.length))
  if (!task) {
    return {
      task: renderedMaterial,
      stimulus: '',
      material: '',
    }
  }

  const cleanedMaterial = stripMaterialLabel(renderedMaterial)
  const showInline = (
    cleanedMaterial.length <= INLINE_STIMULUS_LIMIT
    && !looksLikeCourseMaterial(material)
  )
  return {
    task,
    stimulus: showInline ? cleanedMaterial : '',
    material: showInline ? '' : cleanedMaterial,
  }
}

export const formatPracticeQuestionMarkdown = (
  value: unknown,
) => {
  const { task, stimulus, material } = splitPracticeQuestionMarkdown(value)
  const context = stimulus || material
  if (!context) return task

  return [
    context,
    '---',
    '## 作答任务',
    task,
  ].join('\n\n')
}
