/** 通用工具：core 纯逻辑，不触碰 DOM */

export function uuid(): string {
  const c = (globalThis as { crypto?: Crypto }).crypto
  if (c?.randomUUID) return c.randomUUID()
  // 低版本/非安全上下文兜底
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (ch) => {
    const r = (Math.random() * 16) | 0
    return (ch === 'x' ? r : (r & 0x3) | 0x8).toString(16)
  })
}

/** FNV-1a 32bit，采样分桶与错误指纹共用 */
export function fnv1a(str: string): number {
  let h = 0x811c9dc5
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i)
    h = Math.imul(h, 0x01000193)
  }
  return h >>> 0
}

export function hashHex(str: string): string {
  return fnv1a(str).toString(16).padStart(8, '0')
}

/** 稳定 JSON 序列化（键排序），用于曝光去重参数指纹 */
export function stableStringify(value: unknown): string {
  if (value === null || typeof value !== 'object') return JSON.stringify(value) ?? ''
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(',')}]`
  const obj = value as Record<string, unknown>
  const keys = Object.keys(obj).sort()
  return `{${keys.map((k) => `${JSON.stringify(k)}:${stableStringify(obj[k])}`).join(',')}}`
}

/** 按 UTF-16 码元截断，不拆代理对（截断点落在高位代理之后时再退一位，避免产生孤立代理） */
export function truncate(str: string, max: number): string {
  if (str.length <= max) return str
  let end = max
  const c = str.charCodeAt(end - 1)
  if (end > 0 && c >= 0xd800 && c <= 0xdbff) end--
  return str.slice(0, end)
}

/** 按 UTF-8 字节截断，不拆字符（码点为单位） */
export function truncateBytes(str: string, maxBytes: number): string {
  if (maxBytes <= 0) return ''
  let bytes = 0
  let i = 0
  for (const ch of str) {
    const cp = ch.codePointAt(0) as number
    const n = cp < 0x80 ? 1 : cp < 0x800 ? 2 : cp < 0x10000 ? 3 : 4
    if (bytes + n > maxBytes) break
    bytes += n
    i += ch.length
  }
  return str.slice(0, i)
}

/**
 * 堆栈帧 URL 去掉 query / hash（常带 token、签名），保留末尾的 :行:列。
 * 例：`https://cdn.x/app.js?token=abc:10:5` → `https://cdn.x/app.js:10:5`
 */
const STACK_URL_QUERY_RE = /(\b[a-z][\w+.-]*:\/\/[^\s?#()]*)[?#][^\s()]*?(:\d+(?::\d+)?)?(?=[\s()]|$)/gi
export function stripStackUrlQuery(stack: string): string {
  return stack.replace(STACK_URL_QUERY_RE, (_m, base: string, pos?: string) => base + (pos ?? ''))
}

/** 自定义事件名白名单（$ 为服务端保留字；远端圈选规则过滤与圈选面板校验共用） */
export const CUSTOM_EVENT_NAME_RE = /^[A-Za-z][A-Za-z0-9_]{0,63}$/

export function byteLength(str: string): number {
  return new TextEncoder().encode(str).length
}

export function safeParse<T>(raw: string | null): T | null {
  if (!raw) return null
  try {
    return JSON.parse(raw) as T
  } catch {
    return null
  }
}

/** 字符串属性值上限 */
export const PROP_VALUE_MAX_LEN = 1024
/** 顶层 stack（错误堆栈）上限：与服务端 PROPS_STACK_MAX_LEN 一致 */
export const PROP_STACK_MAX_LEN = 4096

/** 单事件 props 总量上限（JSON UTF-8 字节）：与服务端 PROPS_TOTAL_MAX_BYTES 一致 */
export const PROPS_TOTAL_MAX_BYTES = 16384

/**
 * 属性清洗：键 ≤64、字符串值 ≤1024（顶层 stack ≤4096，且去掉帧 URL 的 query），剔除 undefined。
 * 总量超过 16KB 时**先缩 stack**（按字节，不拆字符），仍超再由服务端从尾部摘键。
 */
export function sanitizeProps(props: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(props)) {
    if (v === undefined) continue
    const key = truncate(k, 64)
    out[key] =
      typeof v === 'string'
        ? key === 'stack'
          ? truncate(stripStackUrlQuery(v), PROP_STACK_MAX_LEN)
          : truncate(v, PROP_VALUE_MAX_LEN)
        : v
  }
  if (typeof out.stack === 'string' && out.stack) {
    let size: number
    try {
      size = byteLength(JSON.stringify(out))
    } catch {
      return out
    }
    if (size > PROPS_TOTAL_MAX_BYTES) {
      const stack = out.stack as string
      // JSON 转义使字节数 ≥ 原文：按超出量缩，再复核一次（转义字符多时再退）
      let target = byteLength(stack) - (size - PROPS_TOTAL_MAX_BYTES)
      for (let i = 0; i < 3; i++) {
        out.stack = truncateBytes(stack, target)
        const now = byteLength(JSON.stringify(out))
        if (now <= PROPS_TOTAL_MAX_BYTES || target <= 0) break
        target -= now - PROPS_TOTAL_MAX_BYTES
      }
    }
  }
  return out
}

/**
 * 敏感键名归一：去掉 - 和 _ 再小写，accessToken / access-token / ACCESS_TOKEN 都归为 accesstoken。
 * URL 查询键与响应体键共用这一口径；归一后精确匹配，不做子串匹配（tokenCount、sessionTimeout 不算）。
 */
export const normalizeKey = (k: string): string => k.replace(/[-_]/g, '').toLowerCase()

/** 上报 URL 敏感 query 键（normalizeKey 归一后精确匹配）：命中则值替换为 ***，业务参数保留 */
const SENSITIVE_QUERY_KEYS = new Set(
  [
    'token',
    'access_token',
    'authorization',
    'id_token',
    'refresh_token',
    'api_key',
    'apikey',
    'auth',
    'secret',
    'password'
  ].map(normalizeKey)
)

/**
 * 剥离 URL 查询串中的敏感键值（normalizeKey 归一，忽略大小写与 -、_）。
 * 非法 URL 原样返回；无查询串不动；命中键的值替换为 ***（与 api-body 脱敏口径一致）。
 */
/** endpoint 归一：去首尾空白与末尾所有斜杠，避免拼出 //track/collect、//track/config */
export function normalizeEndpoint(endpoint: string): string {
  return String(endpoint).trim().replace(/\/+$/, '')
}

export function redactSensitiveUrl(url: string): string {
  try {
    const u = new URL(url, 'https://placeholder.invalid')
    let changed = false
    const keys = Array.from(new Set(u.searchParams.keys()))
    for (const key of keys) {
      if (SENSITIVE_QUERY_KEYS.has(normalizeKey(key))) {
        u.searchParams.set(key, '***')
        changed = true
      }
    }
    if (!changed) return url
    // 相对 URL 输入时保留相对形态（去掉占位 origin）
    if (!/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(url)) {
      return `${u.pathname}${u.search}${u.hash}`
    }
    return u.href
  } catch {
    return url
  }
}
