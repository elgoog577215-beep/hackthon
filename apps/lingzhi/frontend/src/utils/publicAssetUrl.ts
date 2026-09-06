const ABSOLUTE_ASSET_URL = /^(?:[a-z][a-z\d+.-]*:|\/\/)/i

export function resolvePublicAssetUrl(
  assetPath: string | null | undefined,
  baseUrl: string = '/',
) {
  const value = String(assetPath || '').trim()
  if (!value || ABSOLUTE_ASSET_URL.test(value)) return value

  const basePath = `/${String(baseUrl || '/')
    .trim()
    .replace(/^\/+|\/+$/g, '')}/`.replace(/^\/\/$/, '/')
  if (basePath !== '/' && value.startsWith(basePath)) return value

  return `${basePath}${value.replace(/^\/+/, '')}`
}
