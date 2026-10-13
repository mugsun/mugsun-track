import type { ResolvedTrackOptions } from '../types'

/**
 * 错误是否应被忽略（不上报 $error）。
 * 默认（skipHandledErrors）跳过 name==='HttpError' 与 handled/expected 标记的错误；
 * 再按 ignoreErrors（字符串子串 / RegExp / 谓词）匹配。谓词抛错按不忽略处理
 */
export function isIgnoredError(
  options: Pick<ResolvedTrackOptions, 'ignoreErrors' | 'skipHandledErrors'>,
  error: unknown,
  message: string
): boolean {
  if (options.skipHandledErrors && error && typeof error === 'object') {
    const e = error as { name?: unknown; handled?: unknown; expected?: unknown }
    if (e.name === 'HttpError' || e.handled === true || e.expected === true) return true
  }
  const rules = options.ignoreErrors
  if (!rules) return false
  if (typeof rules === 'function') {
    try {
      return rules(error, message) === true
    } catch {
      return false
    }
  }
  return rules.some((r) => (typeof r === 'string' ? message.includes(r) : r.test(message)))
}
