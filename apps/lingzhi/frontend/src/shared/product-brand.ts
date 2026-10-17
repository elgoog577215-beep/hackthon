import { resolvePublicAssetUrl } from '../utils/publicAssetUrl'

export type ProductSurface = 'teacher' | 'student'

export function productSurface(configured: unknown, path: string, teacherPreview: unknown): ProductSurface {
  if (configured === 'teacher' || configured === 'student') return configured
  if (/^\/study(?:\/|$)/.test(path) || (/^\/course\/[^/]+\/learn(?:\/|$)/.test(path) && teacherPreview !== '1')) return 'student'
  return 'teacher'
}

export function productIdentity(surface: ProductSurface, locale: string) {
  const english = locale === 'en'
  const name = surface === 'teacher' ? (english ? 'Qizhi' : '启智') : (english ? 'Lingzhi' : '灵知')
  const role = surface === 'teacher' ? (english ? 'Teacher' : '教师端') : (english ? 'Student' : '学生端')
  return {
    name, role, title: `${name} · ${role}`,
    home: surface === 'teacher' ? '/courses' : '/study',
    icon: surface === 'teacher' ? 'qizhi-favicon.svg' : 'lingzhi-favicon.svg',
  }
}

// Branding follows the selected application, without changing its API identity.
export function syncProductDocument(surface: ProductSurface, locale: string, base = import.meta.env.BASE_URL) {
  const identity = productIdentity(surface, locale)
  document.title = identity.title
  const icon = document.querySelector<HTMLLinkElement>('link[rel="icon"]') || document.createElement('link')
  icon.rel = 'icon'
  icon.type = 'image/svg+xml'
  icon.href = resolvePublicAssetUrl(identity.icon, base)
  if (!icon.isConnected) document.head.appendChild(icon)
}
