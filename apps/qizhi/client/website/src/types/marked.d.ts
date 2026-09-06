declare module 'marked' {
  // 这里仅声明我们实际用到的最小接口，避免额外类型依赖
  export function parse(src: string, options?: unknown): string
  export function use(options?: unknown): void
  export const marked: {
    parse: (src: string, options?: unknown) => string
    use: (options?: unknown) => void
  }
}

declare module 'katex' {
  export interface KatexRenderOptions {
    displayMode?: boolean
    throwOnError?: boolean
    [k: string]: any
  }

  export function renderToString(tex: string, options?: KatexRenderOptions): string

  const katex: {
    renderToString: typeof renderToString
  }

  export default katex
}
