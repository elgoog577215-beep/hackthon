import DOMPurify from 'dompurify'

const ALLOWED_TAGS = [
  'p', 'br', 'strong', 'em', 'u', 's', 'span',
  'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'ul', 'ol', 'li', 'blockquote', 'pre', 'code',
  'a', 'img', 'table', 'thead', 'tbody', 'tr', 'th', 'td',
  'hr', 'div'
]

const ALLOWED_ATTR = [
  'href', 'src', 'alt', 'title', 'class', 'id',
  'target', 'rel', 'width', 'height', 'style'
]

export function sanitizeHTML(dirty: string): string {
  return DOMPurify.sanitize(dirty, {
    ALLOWED_TAGS,
    ALLOWED_ATTR,
    ALLOW_DATA_ATTR: false
  })
}

export function sanitizeText(text: string): string {
  const div = document.createElement('div')
  div.textContent = text
  return div.innerHTML
}

export function escapeHTML(str: string): string {
  const escapeMap: Record<string, string> = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#x27;',
    '/': '&#x2F;',
    '`': '&#x60;',
    '=': '&#x3D;'
  }
  return str.replace(/[&<>"'`=/]/g, (char) => escapeMap[char] || char)
}

export function unescapeHTML(str: string): string {
  const unescapeMap: Record<string, string> = {
    '&amp;': '&',
    '&lt;': '<',
    '&gt;': '>',
    '&quot;': '"',
    '&#x27;': "'",
    '&#x2F;': '/',
    '&#x60;': '`',
    '&#x3D;': '='
  }
  return str.replace(/&(amp|lt|gt|quot|#x27|#x2F|#x60|#x3D);/g, (entity) => unescapeMap[entity] || entity)
}

export function isValidURL(url: string): boolean {
  try {
    const parsed = new URL(url)
    return ['http:', 'https:'].includes(parsed.protocol)
  } catch {
    return false
  }
}

export function sanitizeURL(url: string): string {
  if (!url) return ''
  
  const trimmed = url.trim()
  
  if (trimmed.startsWith('/') || trimmed.startsWith('#')) {
    return trimmed
  }
  
  if (isValidURL(trimmed)) {
    return trimmed
  }
  
  return ''
}

export function validateInput(input: string, options: {
  minLength?: number
  maxLength?: number
  pattern?: RegExp
  required?: boolean
} = {}): { valid: boolean; error?: string } {
  const { minLength = 0, maxLength = 10000, pattern, required = false } = options

  if (required && !input.trim()) {
    return { valid: false, error: '此字段为必填项' }
  }

  if (input.length < minLength) {
    return { valid: false, error: `最少需要 ${minLength} 个字符` }
  }

  if (input.length > maxLength) {
    return { valid: false, error: `最多允许 ${maxLength} 个字符` }
  }

  if (pattern && !pattern.test(input)) {
    return { valid: false, error: '输入格式不正确' }
  }

  return { valid: true }
}

export function validateEmail(email: string): boolean {
  const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
  return emailPattern.test(email)
}

export function validateCourseName(name: string): { valid: boolean; error?: string } {
  return validateInput(name, {
    minLength: 2,
    maxLength: 100,
    required: true,
    pattern: /^[\u4e00-\u9fa5a-zA-Z0-9\s\-_()（）【】]+$/
  })
}

export function validateNodeContent(content: string): { valid: boolean; error?: string } {
  return validateInput(content, {
    maxLength: 50000
  })
}

export function stripTags(html: string): string {
  const div = document.createElement('div')
  div.innerHTML = html
  return div.textContent || div.innerText || ''
}

export function truncateText(text: string, maxLength: number, suffix: string = '...'): string {
  if (text.length <= maxLength) return text
  return text.slice(0, maxLength - suffix.length) + suffix
}

export function sanitizeFileName(name: string): string {
  return name
    .replace(/[<>:"/\\|?*\x00-\x1f]/g, '_')
    .replace(/^\.+/, '')
    .replace(/\.+$/, '')
    .slice(0, 255)
}

export function sanitizeForJSON(value: unknown): unknown {
  if (typeof value === 'string') {
    return value
      .replace(/\\/g, '\\\\')
      .replace(/"/g, '\\"')
      .replace(/\n/g, '\\n')
      .replace(/\r/g, '\\r')
      .replace(/\t/g, '\\t')
  }
  if (Array.isArray(value)) {
    return value.map(sanitizeForJSON)
  }
  if (typeof value === 'object' && value !== null) {
    const result: Record<string, unknown> = {}
    for (const [key, val] of Object.entries(value)) {
      result[key] = sanitizeForJSON(val)
    }
    return result
  }
  return value
}
