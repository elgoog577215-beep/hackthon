/// <reference types="vite/client" />

/** 避免部分环境下 md-editor-v3 类型解析失败（包内类型路径与 ts 解析不一致） */
declare module 'md-editor-v3' {
  import type { Component } from 'vue'
  export const MdEditor: Component
  export function config(options: unknown): void
}

declare module 'dompurify'
