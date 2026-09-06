let fallbackSequence = 0

const formatUuid = (bytes: Uint8Array): string => {
  const hex = Array.from(bytes, value => value.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}

const fillFallbackBytes = (bytes: Uint8Array): void => {
  fallbackSequence = (fallbackSequence + 1) >>> 0
  const time = Date.now()

  for (let index = 0; index < bytes.length; index += 1) {
    bytes[index] = Math.floor(Math.random() * 256)
  }

  for (let index = 0; index < 6; index += 1) {
    bytes[index] = (bytes[index] ?? 0) ^ (Math.floor(time / (2 ** (index * 8))) & 0xff)
  }
  bytes[12] = (bytes[12] ?? 0) ^ ((fallbackSequence >>> 24) & 0xff)
  bytes[13] = (bytes[13] ?? 0) ^ ((fallbackSequence >>> 16) & 0xff)
  bytes[14] = (bytes[14] ?? 0) ^ ((fallbackSequence >>> 8) & 0xff)
  bytes[15] = (bytes[15] ?? 0) ^ (fallbackSequence & 0xff)
}

/**
 * Generate an RFC 4122 version 4 UUID in browsers that do not expose
 * crypto.randomUUID, including production pages served over plain HTTP.
 */
export const createUuid = (): string => {
  const webCrypto = typeof globalThis !== 'undefined' ? globalThis.crypto : undefined
  if (typeof webCrypto?.randomUUID === 'function') return webCrypto.randomUUID()

  const bytes = new Uint8Array(16)
  if (typeof webCrypto?.getRandomValues === 'function') {
    webCrypto.getRandomValues(bytes)
  } else {
    fillFallbackBytes(bytes)
  }

  bytes[6] = ((bytes[6] ?? 0) & 0x0f) | 0x40
  bytes[8] = ((bytes[8] ?? 0) & 0x3f) | 0x80
  return formatUuid(bytes)
}
