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

/**
 * 凭证键清单：URL 查询 / hash 参数、referrer 与响应体 JSON 键**共用这一份**。
 * 按 normalizeKey 归一后精确匹配，不做子串匹配（tokenCount、sessionTimeout 都不算）。
 * 命中则值整值替换为 ***；响应体里不受 apiBodyMaskEnabled 控制。
 */
export const SENSITIVE_KEYS: ReadonlySet<string> = new Set(
  [
    // 令牌与鉴权头
    'token',
    'access_token',
    'refresh_token',
    'id_token',
    'authorization',
    'auth',
    'jwt',
    // API key 与密钥
    'api_key',
    'apikey',
    'x-api-key',
    'secret',
    'client_secret',
    'private_key',
    'access_key',
    'secret_key',
    // 云存储预签名 URL
    'x-amz-signature',
    'x-amz-security-token',
    'x-goog-signature',
    // 口令
    'password',
    'passwd',
    'pwd',
    // 会话标识与 cookie
    'cookie',
    'set-cookie',
    'session',
    'session_id',
    'jsessionid'
  ].map(normalizeKey)
)

/**
 * 只在 URL（查询串、hash、referrer）里脱敏的键：OAuth 授权码、签名、CAS/SSO 票据、一次性验证码。
 * 这些键在响应体里常是业务字段（如 {code:0}、{sign:true}），响应体里**不**替换，便于看接口错误、复现问题。
 */
export const URL_ONLY_SENSITIVE_KEYS: ReadonlySet<string> = new Set(
  [
    'code',
    'sign',
    'signature',
    'ticket',
    'otp',
    // 云存储预签名：Azure SAS、腾讯云 COS（含临时密钥 token）、阿里云 OSS
    'sig',
    'q-signature',
    'x-oss-signature',
    'x-oss-security-token',
    'x-cos-security-token'
  ].map(normalizeKey)
)

const isSensitiveUrlKey = (key: string): boolean => {
  const k = normalizeKey(key)
  return SENSITIVE_KEYS.has(k) || URL_ONLY_SENSITIVE_KEYS.has(k)
}

/**
 * 对 `k=v&k2=v2` 形式的参数串做敏感键替换；返回 null 表示未命中。
 * 按 & 切分，只替换命中键的值，其他参数逐字保留（不经 URLSearchParams 重新编码，%20、/ 不变）
 */
function redactParamString(qs: string): string | null {
  let changed = false
  const parts = qs.split('&').map((part) => {
    const eq = part.indexOf('=')
    const rawKey = eq >= 0 ? part.slice(0, eq) : part
    if (!rawKey) return part
    // 比较前去掉开头多余的 ?（/a??token=x 的键是 ?token），输出保留原文
    let key = rawKey.replace(/^\?+/, '')
    try {
      key = decodeURIComponent(key.replace(/\+/g, ' '))
    } catch {
      // 非法转义：按原文比较
    }
    // 解码后再去一次开头的 ?（/a?%3Ftoken=x 解码后是 ?token）
    key = key.replace(/^\?+/, '')
    if (!isSensitiveUrlKey(key)) return part
    changed = true
    return `${rawKey}=***`
  })
  return changed ? parts.join('&') : null
}

/**
 * hash 里的参数：OAuth 隐式流 `#access_token=...`、hash 路由 `#/cb?code=...`。
 * 只处理含 `=` 的部分；返回 null 表示未命中
 */
function redactHash(hash: string): string | null {
  if (!hash || !hash.includes('=')) return null
  const body = hash.slice(1)
  const q = body.indexOf('?')
  if (q >= 0) {
    const r = redactParamString(body.slice(q + 1))
    return r === null ? null : `#${body.slice(0, q + 1)}${r}`
  }
  const r = redactParamString(body)
  return r === null ? null : `#${r}`
}

/** endpoint 归一：去首尾空白与末尾所有斜杠，避免拼出 //track/collect、//track/config */
export function normalizeEndpoint(endpoint: string): string {
  return String(endpoint).trim().replace(/\/+$/, '')
}

/**
 * 剥离 URL 中的敏感信息（键名经 normalizeKey 归一，忽略大小写与 -、_）：userinfo、路径参数、查询串与 hash 参数。
 * 无命中原样返回；命中键的值替换为 ***（与 api-body 脱敏口径一致），其他参数逐字保留。
 */
export function redactSensitiveUrl(url: string): string {
  // 只改 userinfo、路径参数（;key=v）、查询串和 hash，其余部分（协议、主机、相对路径、// 前缀）逐字保留
  if (typeof url !== 'string' || !url) return url
  // 浏览器解析 URL 时会删掉 TAB/LF/CR（to\nken=x 等价于 token=x）：先删掉再匹配，命中时返回删后的形态
  // 浏览器还会去掉开头的空白与 C0 控制字符（\x00-\x20，本身已含 TAB/LF/CR，开头的这些两步都会删）；两步都是线性替换
  const src = url.replace(/[\t\n\r]/g, '').replace(/^[\x00-\x20]+/, '')
  const out = redactCleanUrl(src)
  return out === src ? url : out
}

/**
 * userinfo：scheme://user:pass@host 或 //user:pass@host，整段替换为 ***，取到 authority 里最后一个 @。按协议区分：
 * - 特殊协议（http、https、ws、wss、ftp、file）与协议相对 URL：// 可写成 \\，且 \\ 和 / 一样结束 authority
 *   （与浏览器一致），所以 https://h\\@evil/x 不动，https:\\\\u:p@h 遮住。
 * - 其他协议（mongodb、redis、自定义）：必须是 //，\\ 是普通字符，mongodb://u:p\\w@h 整段遮住。
 * 都是 ^ 锚定、单个贪婪字符类，回溯线性。已知漏判：缺 // 的 https:u:p@h
 */
const SPECIAL_USERINFO_RE = /^((?:(?:https?|wss?|ftp|file):)?[\\/]{2})([^/\\?#]*)@/i
/** 特殊协议或协议相对（含反斜杠写法）开头 */
const SPECIAL_SCHEME_RE = /^(?:(?:https?|wss?|ftp|file):|[\\/]{2})/i
const OTHER_USERINFO_RE = /^([a-zA-Z][a-zA-Z0-9+.-]*:\/\/)([^/?#]*)@/

/** 路径参数：/a;jsessionid=xxx/b，键命中敏感清单时替换值 */
const PATH_PARAM_RE = /;([^;=/?#]+)=([^;/?#]*)/g

function redactCleanUrl(url: string): string {
  const hashAt = url.indexOf('#')
  const beforeHash = hashAt >= 0 ? url.slice(0, hashAt) : url
  const hashPart = hashAt >= 0 ? url.slice(hashAt) : ''
  const qAt = beforeHash.indexOf('?')
  let base = qAt >= 0 ? beforeHash.slice(0, qAt) : beforeHash
  let query = qAt >= 0 ? beforeHash.slice(qAt + 1) : null
  let hash = hashPart
  let changed = false
  const ui = SPECIAL_SCHEME_RE.test(base) ? SPECIAL_USERINFO_RE.exec(base) : OTHER_USERINFO_RE.exec(base)
  if (ui && ui[2]) {
    base = `${ui[1]}***@${base.slice(ui[0].length)}`
    changed = true
  }
  if (base.includes(';')) {
    const pb = base.replace(PATH_PARAM_RE, (m, k: string) => (isSensitiveUrlKey(k) ? `;${k}=***` : m))
    if (pb !== base) {
      base = pb
      changed = true
    }
  }
  try {
    if (query) {
      const r = redactParamString(query)
      if (r !== null) {
        query = r
        changed = true
      }
    }
    const h = redactHash(hashPart)
    if (h !== null) {
      hash = h
      changed = true
    }
  } catch {
    return url
  }
  if (!changed) return url
  return `${base}${query !== null ? `?${query}` : ''}${hash}`
}
