/**
 * 前端加密工具（用于登录/注册传参前对密码做哈希，避免明文传输）
 * 使用 js-sha256，支持所有环境（包括 HTTP）
 */
import { sha256 } from 'js-sha256'

/**
 * 对字符串做 SHA-256 哈希，返回十六进制字符串
 * 用于登录/注册时前端对密码哈希后再传给后端（后端需按相同方式校验/存储）
 */
export function sha256Hex(text: string): string {
  return sha256(text)
}
