import type {
  PluginContext,
  ReplayController,
  ResolvedTrackOptions,
  TrackPlugin
} from '../../types'
import { createBrowserTransportDeps } from '../../adapters'
import { isSampled } from '../../core/sampler'
import { redactSensitiveUrl } from '../../core/utils'
import { Transport } from '../../core/transport'
import { ReplayRecorder, type ReplayChunkPayload } from './recorder'

/**
 * rrweb.record 入参中插件关心的子集（结构化声明，避免 d.ts 反向依赖 rrweb 类型）。
 * 完整签名见 rrweb recordOptions。
 */
export interface ReplayRecordOptions {
  emit: (event: unknown, isCheckout?: boolean) => void
  maskAllInputs: boolean
  /** rrweb maskInputOptions：插件始终传 { password: true } */
  maskInputOptions?: Record<string, boolean>
  /** 页面文本遮罩选择器；默认不传（录原文） */
  maskTextSelector?: string
  blockSelector: string
  recordCanvas: boolean
  /** rrweb 定时全量快照间隔（ms）；见 ReplayPluginOptions.checkoutEveryNms */
  checkoutEveryNms?: number
  [key: string]: unknown
}

/** rrweb.record 的结构化形态：测试注入 stub 产假事件流；真实实现由插件懒加载 import('rrweb') */
export type ReplayRecordFn = (options: ReplayRecordOptions) => (() => void) | undefined

export interface ReplayPluginOptions {
  /** 切块间隔 ms，默认 5000 */
  chunkIntervalMs?: number
  /** 单块事件数阈值，默认 50 */
  eventsPerChunk?: number
  /** 环形缓冲时长上限 ms，默认 5min */
  bufferMaxAge?: number
  /** 环形缓冲字节上限，默认 10MB */
  bufferMaxBytes?: number
  /** 单块失败重试次数（指数退避后丢弃），默认 3 */
  maxRetries?: number
  /**
   * 定时全量快照间隔 ms（rrweb 内置 `checkoutEveryNms`），默认 180000（3 分钟）；传 false 关闭。
   * 中间某块丢失（收尾额度不够、重试耗尽）时，播放器可以从下一个全量快照接着播，而不是一直错到结尾。
   */
  checkoutEveryNms?: number | false
  /**
   * 页面文本遮罩选择器（rrweb maskTextSelector）。
   * 默认不遮罩（录原文）；传 '*' 遮全页文本，或传更窄的选择器只遮部分区域。false 与不传等价。
   */
  maskTextSelector?: string | false
  /**
   * 遮罩所有输入框的值（rrweb maskAllInputs）。默认 false（录原值）；设 true 时所有输入值录成 ***。
   * 不论取值，password、data-track-mask、银行卡（autocomplete=cc-*）、一次性验证码（autocomplete=one-time-code）
   * 字段始终整块不录，canvas 始终不录
   */
  maskAllInputs?: boolean
  /** 测试注入：替代 rrweb.record（不引真实 DOM 录制） */
  record?: ReplayRecordFn
  /** 测试注入：发送实现（默认内置 beacon→fetch→XHR 降级链，独立通道不占事件队列） */
  send?: (payload: ReplayChunkPayload, opts: { preferBeacon: boolean }) => Promise<boolean>
  /** 测试注入：gzip 实现；传 null 强制走明文降级路径 */
  gzip?: ((body: string) => Promise<ArrayBuffer>) | null
}

/** rrweb Meta 事件（type 4）带完整 location.href：按 URL 敏感参数口径脱敏 */
function redactMetaHref<T>(event: T): T {
  const e = event as { type?: unknown; data?: { href?: unknown } }
  if (e?.type === 4 && e.data && typeof e.data.href === 'string') {
    return { ...e, data: { ...e.data, href: redactSensitiveUrl(e.data.href) } } as T
  }
  return event
}

/** 回放 DOM 里需要按 URL 敏感参数脱敏的属性（属性名小写后比较，HREF 也算） */
const URL_ATTRS = new Set(['href', 'src', 'action', 'xlink:href', 'formaction', 'poster', 'data'])
/** 候选列表属性：`url 1x, url2 2x` 形式，逐个候选脱敏 URL、保留描述符 */
const SRCSET_ATTRS = new Set(['srcset', 'imagesrcset'])

/**
 * 按 HTML 规范的 srcset 候选解析（parse a srcset attribute）：跳过空白与逗号 → 取一段非空白作为 URL
 * （URL 里可以有逗号；末尾的逗号不属于 URL）→ 描述符读到括号外的逗号为止。
 * 只替换每个候选的 URL 部分，其余字符（空白、描述符、逗号）原样保留；data: 候选单独跳过，其他候选照常脱敏
 */
export function redactSrcset(v: string): string {
  let out = ''
  let i = 0
  const n = v.length
  const isWs = (c: string) => c === ' ' || c === '\t' || c === '\n' || c === '\f' || c === '\r'
  while (i < n) {
    let j = i
    while (j < n && (isWs(v[j]) || v[j] === ',')) j++
    out += v.slice(i, j)
    if (j >= n) break
    let k = j
    while (k < n && !isWs(v[k])) k++
    let url = v.slice(j, k)
    let trailing = ''
    let descEnd = k
    if (url.endsWith(',')) {
      // 从末尾往前数逗号（线性），不用 /,+$/：长串逗号时正则回溯是平方级
      let end = url.length
      while (end > 0 && url.charCodeAt(end - 1) === 44) end--
      trailing = url.slice(end)
      url = url.slice(0, end)
    } else {
      let depth = 0
      while (descEnd < n) {
        const c = v[descEnd]
        if (c === '(') depth++
        else if (c === ')') depth = Math.max(0, depth - 1)
        else if (c === ',' && depth === 0) break
        descEnd++
      }
    }
    out += (/^data:/i.test(url) ? url : redactSensitiveUrl(url)) + trailing + v.slice(k, descEnd)
    i = descEnd
  }
  return out
}

function redactAttrs(attrs: unknown): void {
  if (!attrs || typeof attrs !== 'object') return
  const a = attrs as Record<string, unknown>
  for (const name of Object.keys(a)) {
    const v = a[name]
    if (typeof v !== 'string' || !v) continue
    const n = name.toLowerCase()
    const r = URL_ATTRS.has(n) ? redactSensitiveUrl(v) : SRCSET_ATTRS.has(n) ? redactSrcset(v) : v
    if (r !== v) a[name] = r
  }
}

/** 遍历节点树：显式栈，不递归，任意深度都处理（不会因层级过深漏掉子树） */
function redactNodeTree(root: unknown): void {
  const stack: unknown[] = [root]
  while (stack.length) {
    const node = stack.pop()
    if (!node || typeof node !== 'object') continue
    const n = node as { attributes?: unknown; childNodes?: unknown[] }
    redactAttrs(n.attributes)
    if (Array.isArray(n.childNodes)) for (const c of n.childNodes) stack.push(c)
  }
}

/**
 * 回放 DOM 快照里的 URL 属性（a[href]、img/iframe/script[src]、form[action] 等）脱敏。
 * rrweb 2.1.1 的 record 没有属性级钩子（maskAttributeFn 只在 Sentry 分叉里有），
 * 所以在 emit 时处理：全量快照（type 2）遍历节点树；增量快照（type 3）的 DOM 变更
 * （source 0）处理新增节点与属性变更。原地改写 rrweb 刚产出的事件对象
 */
export function redactReplayUrls<T>(event: T): T {
  const e = event as {
    type?: unknown
    data?: {
      source?: unknown
      node?: unknown
      adds?: Array<{ node?: unknown }>
      attributes?: Array<{ attributes?: unknown }>
    }
  }
  if (!e || !e.data) return event
  if (e.type === 2) {
    redactNodeTree(e.data.node)
  } else if (e.type === 3 && e.data.source === 0) {
    if (Array.isArray(e.data.adds)) for (const a of e.data.adds) redactNodeTree(a?.node)
    if (Array.isArray(e.data.attributes)) for (const a of e.data.attributes) redactAttrs(a?.attributes)
  }
  return event
}

/** 默认每 3 分钟一次全量快照（rrweb checkoutEveryNms） */
export const DEFAULT_CHECKOUT_EVERY_MS = 3 * 60 * 1000

/**
 * 内置整块屏蔽（rrweb blockSelector，不可关）：password、平台统一敏感标记，
 * 以及银行卡（autocomplete=cc-*）和一次性验证码（autocomplete=one-time-code）字段
 */
const ALWAYS_BLOCK = [
  'input[type="password"]',
  '[data-track-mask]',
  '[autocomplete^="cc-"]',
  '[autocomplete="one-time-code"]'
].join(', ')

/** 默认发送：独立 Transport（不复用事件队列）；压缩在 payload 字段级完成，传输层不再二次 gzip */
function createDefaultSend(options: ResolvedTrackOptions) {
  const deps = createBrowserTransportDeps()
  delete deps.gzip
  const getHeaders = (): Record<string, string> => {
    const h = options.headers
    return typeof h === 'function' ? h() : (h ?? {})
  }
  const transport = new Transport(`${options.endpoint}/track/replay`, deps, getHeaders)
  return (payload: ReplayChunkPayload, opts: { preferBeacon: boolean }): Promise<boolean> =>
    transport.send(payload, { preferBeacon: opts.preferBeacon })
}

function createDefaultGzip(): ((body: string) => Promise<ArrayBuffer>) | undefined {
  if (typeof CompressionStream !== 'function') return undefined
  return async (body) => {
    const stream = new Blob([body]).stream().pipeThrough(new CompressionStream('gzip'))
    return new Response(stream).arrayBuffer()
  }
}

/**
 * 会话回放（G100）：常录 + 选择性上传。
 * - replayEnabled（本地或远端下发，下次启动生效）才开录：录入内存环形缓冲（5min/10MB 滚动覆盖）
 * - 会话命中 replaySampleRate（`${appKey}:${session_id}` 哈希分桶，会话级一致）→ 会话内分块上传
 * - 会话内出现 $error → 无视采样强制上传（client.onError 钩子，error 插件/vue errorHandler 统一出口）
 * - 未命中且无错误 → 缓冲随会话结束丢弃；回放传输独立通道，不占事件队列
 */
export function replayPlugin(pluginOpts: ReplayPluginOptions = {}): TrackPlugin {
  return {
    name: 'replay',
    setup(ctx: PluginContext) {
      if (typeof window === 'undefined') return
      const { client, options, log } = ctx
      // 主采样未命中/optOut/停用：事件都不采的会话回放无意义（也省下 rrweb 下载）
      if (!client.isEnabled()) return
      // 总开关关闭则无上传路径：不录（远端开启后下次启动生效）
      if (!options.replayEnabled) return

      const recorder = new ReplayRecorder({
        appKey: options.appKey,
        uploadEnabled: options.replayEnabled,
        send: pluginOpts.send ?? createDefaultSend(options),
        gzip: pluginOpts.gzip === null ? undefined : (pluginOpts.gzip ?? createDefaultGzip()),
        canRecord: () => client.isEnabled(),
        chunkIntervalMs: pluginOpts.chunkIntervalMs,
        eventsPerChunk: pluginOpts.eventsPerChunk,
        bufferMaxAge: pluginOpts.bufferMaxAge,
        bufferMaxBytes: pluginOpts.bufferMaxBytes,
        maxRetries: pluginOpts.maxRetries,
        retryBaseDelay: options.retryBaseDelay,
        retryMaxDelay: options.retryMaxDelay,
        log
      })

      // 会话绑定与轮换：采样判定按会话级一致分桶；轮换即重置缓冲与 seq。
      // 首绑读当前持久化会话（跨页面加载会话延续）；之后由 client 钩子驱动
      const bindSession = (sid: string | null) => {
        recorder.bindSession(
          sid,
          sid !== null && isSampled(`${options.appKey}:${sid}`, options.replaySampleRate)
        )
      }
      bindSession(client.peekSessionId())
      const offSession = client.onSessionChange(bindSession)
      const offError = client.onError(() => recorder.forceUpload())
      const onPageHide = () => recorder.flushFinal()
      window.addEventListener('pagehide', onPageHide)
      // 转后台时页面仍存活：先把缓冲压缩后用 beacon/keepalive 发走，pagehide 只剩少量尾巴
      const onVisibility = () => {
        if (document.visibilityState === 'hidden') recorder.flushHidden()
      }
      document.addEventListener('visibilitychange', onVisibility)

      // 挂载点：供调试/测试手动控制（正常路径由内部钩子自动触发）
      const controller: ReplayController = {
        forceUpload: () => recorder.forceUpload(),
        flushFinal: () => recorder.flushFinal(),
        textMasked: Boolean(pluginOpts.maskTextSelector),
        inputsMasked: pluginOpts.maskAllInputs === true
      }
      client.replay = controller

      recorder.start()

      // 懒加载 rrweb：回放录制实现不进主入口首包
      let destroyed = false
      let stopRecord: (() => void) | undefined
      const start = async () => {
        try {
          let record: ReplayRecordFn
          if (pluginOpts.record) {
            record = pluginOpts.record
          } else {
            const mod = await import('rrweb')
            record = mod.record as unknown as ReplayRecordFn
          }
          if (destroyed) return
          stopRecord = record({
            emit: (event) => recorder.push(redactReplayUrls(redactMetaHref(event))),
            // 输入值与页面文本默认录原文（maskAllInputs / maskTextSelector 由接入方开启）；
            // password 另经 maskInputOptions 兜底；password、data-track-mask、cc-*、one-time-code
            // 与 maskSelectors（本地 + 远端下发合并）整块不录；不采 canvas
            maskAllInputs: pluginOpts.maskAllInputs === true,
            maskInputOptions: { password: true },
            ...(pluginOpts.maskTextSelector
              ? { maskTextSelector: pluginOpts.maskTextSelector }
              : {}),
            blockSelector: [ALWAYS_BLOCK, ...options.maskSelectors].join(', '),
            recordCanvas: false,
            ...(pluginOpts.checkoutEveryNms === false
              ? {}
              : { checkoutEveryNms: pluginOpts.checkoutEveryNms ?? DEFAULT_CHECKOUT_EVERY_MS })
          })
        } catch (err) {
          log('replay 启动失败', err)
        }
      }
      void start()

      return () => {
        destroyed = true
        stopRecord?.()
        offSession()
        offError()
        window.removeEventListener('pagehide', onPageHide)
        document.removeEventListener('visibilitychange', onVisibility)
        if (client.replay === controller) client.replay = null
        recorder.destroy()
      }
    }
  }
}

export { ReplayRecorder, FINAL_CHUNK_MAX_BYTES, FINAL_WIRE_BUDGET, CHUNK_MAX_BYTES } from './recorder'
export type { ReplayRecorderOptions } from './recorder'
