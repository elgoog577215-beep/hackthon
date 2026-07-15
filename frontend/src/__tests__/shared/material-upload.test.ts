import { describe, expect, it } from 'vitest'
import { materialUploadErrorMessage, validateMaterialFile } from '@/shared/material-upload'

const messages = {
  unsupported: (extension: string) => `unsupported:${extension}`,
  tooLarge: (maxMb: number) => `too-large:${maxMb}`,
  empty: 'empty',
}

describe('material upload helpers', () => {
  it('将 FastAPI 缺少 file 的原始数组转换为用户可读错误', () => {
    const error = {
      response: { data: { detail: [{ type: 'missing', loc: ['body', 'file'], msg: 'Field required', input: null }] } },
    }
    expect(materialUploadErrorMessage(error, 'fallback')).toBe('上传请求中没有识别到文件，请重新选择后重试')
  })

  it('保留后端返回的可读字符串错误', () => {
    expect(materialUploadErrorMessage({ response: { data: { detail: '文件名不安全' } } }, 'fallback')).toBe('文件名不安全')
  })

  it('在上传前拒绝不支持、空文件和超限文件', () => {
    expect(validateMaterialFile(new File(['x'], 'demo.exe'), messages)).toBe('unsupported:exe')
    expect(validateMaterialFile(new File([], 'empty.pdf'), messages)).toBe('empty')
    const oversized = new File(['x'], 'large.pdf')
    Object.defineProperty(oversized, 'size', { value: 50 * 1024 * 1024 + 1 })
    expect(validateMaterialFile(oversized, messages)).toBe('too-large:50')
    expect(validateMaterialFile(new File(['ok'], 'notes.pdf'), messages)).toBe('')
  })
})
