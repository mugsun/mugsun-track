import { byteLength } from '../../core/utils'

/** POST {endpoint}/track/replay 单块协议体（G100，与后端约定） */
export interface ReplayChunkPayload {
  app_key: string
  session_id: string
  /** 会话内自增块序号，0 起；切块时分配，丢块留空洞，服务端按 seq 排序组装 */
  seq: number
  event_count: number
  /** payload base64 解码后是否还需 gunzip；false = 明文 JSON 数组（pagehide 收尾块/降级路径） */
  gzip: boolean
  /** base64(gzip(rrweb 事件 JSON 数组))，gzip=false 时为 base64(明文 JSON 数组) */
  payload: string
}

export interface ReplayRecorderOptions {
  appKey: string
  /** 回放总开关（本地或远端下发，下次启动生效）；false 永不切块上传 */
  uploadEnabled: boolean
  /** 发送实现；preferBeacon 在 pagehide 收尾块与转后台块时为 true */
  send: (payload: ReplayChunkPayload, opts: { preferBeacon: boolean }) => Promise<boolean>
  /** CompressionStream 包装；缺省或失败降级明文（gzip:false 标记） */
  gzip?: (body: string) => Promise<ArrayBuffer>
  /** 采集门控：false 时不入缓冲、待发块直接丢弃（对齐 optOut/停用即停语义），默认恒 true */
  canRecord?: () => boolean
  /** 切块间隔 ms，默认 5000 */
  chunkIntervalMs?: number
  /** 单块事件数阈值，默认 50 */
  eventsPerChunk?: number
  /** 环形缓冲时长上限 ms（以事件自身 timestamp 为锚），默认 5min */
  bufferMaxAge?: number
  /** 环形缓冲字节上限，默认 10MB */
  bufferMaxBytes?: number
  /** 单块失败重试次数（指数退避后丢弃），默认 3 */
  maxRetries?: number
  /** 退避基数 ms，默认 1000（base * 2^n 封顶 retryMaxDelay） */
  retryBaseDelay?: number
  /** 退避上限 ms，默认 30000 */
  retryMaxDelay?: number
  now?: () => number
  log?: (...args: unknown[]) => void
}

interface BufItem {
  ts: number
  len: number
  json: string
}

interface OutboxChunk {
  payload: ReplayChunkPayload
  /** 已安排的重试次数 */
  attempts: number
  /** 页面转后台时切出的块：走 beacon / fetch keepalive，页面随后卸载也尽量送达 */
  urgent: boolean
}

/** 转后台块的编码凭据：gzip 未完成前页面就卸载时，flushFinal 接管其事件同步明文发出并作废凭据 */
interface PendingUrgent {
  items: BufItem[]
  seq: number
  /** true = 已被 flushFinal 接管，gzip 完成后不得再入 outbox（防双发） */
  superseded: boolean
}

/**
 * pagehide 收尾总预算（请求体字节，即 JSON.stringify(payload) 的 UTF-8 长度）：sendBeacon 与
 * fetch keepalive 共用每个文档约 64KB 的在途额度，而 pagehide 时普通事件队列的收尾 beacon、
 * 以及可能仍在途的回放块也占这份额度，回放收尾只取 44KB。
 * 按 seq 顺序发送，第一块放不下即停止，后面的全部丢弃（保留最早的事件、不在中间留空洞）。
 */
export const FINAL_WIRE_BUDGET = 44 * 1024
/**
 * pagehide 收尾块单块明文上限（JSON 字节）：base64 膨胀 4/3 后约 42.7KB，加信封仍在
 * FINAL_WIRE_BUDGET 内，单块总能放进预算。
 */
export const FINAL_CHUNK_MAX_BYTES = 32 * 1024
/** 收尾块信封（app_key/session_id/seq/event_count/gzip 等字段名与引号）估算余量 */
const ENVELOPE_OVERHEAD = 160
/**
 * 普通/后台块单块明文上限（JSON 字节）：服务端 base64 上限 1,442,802 字符（≈1.08MB 原文），
 * gzip 失败降级明文时也不能超；压缩时再受服务端解压上限 4MB 约束，取 1MB 两者都满足。
 */
export const CHUNK_MAX_BYTES = 1024 * 1024

/** 按字节预算切组（保持顺序）：单条超出 max 的事件自成一组，由调用方决定是否丢弃 */
function splitByBytes(items: BufItem[], max: number): BufItem[][] {
  const groups: BufItem[][] = []
  let cur: BufItem[] = []
  let size = 2
  for (const item of items) {
    const add = item.len + (cur.length > 0 ? 1 : 0)
    if (cur.length > 0 && size + add > max) {
      groups.push(cur)
      cur = []
      size = 2
    }
    cur.push(item)
    size += item.len + (cur.length > 1 ? 1 : 0)
  }
  if (cur.length > 0) groups.push(cur)
  return groups
}

const B64_CHUNK = 0x8000

function base64FromBytes(bytes: Uint8Array): string {
  let bin = ''
  for (let i = 0; i < bytes.length; i += B64_CHUNK) {
    bin += String.fromCharCode(...bytes.subarray(i, i + B64_CHUNK))
  }
  return btoa(bin)
}

function base64FromString(s: string): string {
  return base64FromBytes(new TextEncoder().encode(s))
}

/**
 * 回放录制器（纯逻辑，不触碰 DOM）：
 * - 常录：事件入内存环形缓冲（时间窗/字节双上限，滚动覆盖丢最旧）
 * - 选择性上传：会话被选中（命中采样或 $error 强传）才切块；未选中缓冲滚动覆盖、随会话结束丢弃
 * - 分块：每 chunkIntervalMs 或 eventsPerChunk 事件切一块，seq 会话内自增
 * - 独立通道：自带串行发送泵与指数退避重试，不占用事件队列；回放可丢，重试耗尽即丢弃
 */
export class ReplayRecorder {
  private opts: Required<Omit<ReplayRecorderOptions, 'gzip' | 'now' | 'log'>> &
    Pick<ReplayRecorderOptions, 'gzip' | 'log'>
  private now: () => number

  private buf: BufItem[] = []
  private bufBytes = 0
  private lastTs = 0
  private seq = 0
  private sessionId: string | null = null
  private sampled = false
  private forced = false

  private outbox: OutboxChunk[] = []
  private pendingUrgent: PendingUrgent[] = []
  private pumping = false
  private encodeChain: Promise<void> = Promise.resolve()
  private intervalTimer: ReturnType<typeof setInterval> | null = null
  private retryTimer: ReturnType<typeof setTimeout> | null = null
  private stopped = false

  constructor(options: ReplayRecorderOptions) {
    this.opts = {
      send: options.send,
      canRecord: options.canRecord ?? (() => true),
      chunkIntervalMs: options.chunkIntervalMs ?? 5000,
      eventsPerChunk: options.eventsPerChunk ?? 50,
      bufferMaxAge: options.bufferMaxAge ?? 5 * 60 * 1000,
      bufferMaxBytes: options.bufferMaxBytes ?? 10 * 1024 * 1024,
      maxRetries: options.maxRetries ?? 3,
      retryBaseDelay: options.retryBaseDelay ?? 1000,
      retryMaxDelay: options.retryMaxDelay ?? 30000,
      appKey: options.appKey,
      uploadEnabled: options.uploadEnabled,
      gzip: options.gzip,
      log: options.log
    }
    this.now = options.now ?? (() => Date.now())
  }

  /** 开启定时切块（5s 触发：不足 50 的尾巴也切走） */
  start(): void {
    if (this.intervalTimer) return
    this.intervalTimer = setInterval(() => {
      if (this.selected()) this.cutChunks(this.opts.eventsPerChunk, true)
    }, this.opts.chunkIntervalMs)
  }

  /** rrweb emit 入口：序列化入环形缓冲；选中会话达 50 事件立即切块 */
  push(event: unknown): void {
    if (this.stopped || !this.opts.canRecord()) return
    let json: string
    try {
      json = JSON.stringify(event)
    } catch {
      return
    }
    if (!json) return
    const raw = (event as { timestamp?: unknown }).timestamp
    const ts = typeof raw === 'number' ? raw : this.now()
    const len = byteLength(json)
    this.buf.push({ ts, len, json })
    this.bufBytes += len
    if (ts > this.lastTs) this.lastTs = ts
    // 环形驱逐：超出时间窗（锚定最新事件时间）或字节上限，丢最旧
    while (this.buf.length > 0 && this.buf[0].ts < this.lastTs - this.opts.bufferMaxAge) {
      this.shiftOldest()
    }
    while (this.bufBytes > this.opts.bufferMaxBytes && this.buf.length > 0) {
      this.shiftOldest()
    }
    // 50 事件触发
    if (this.selected() && this.buf.length >= this.opts.eventsPerChunk) {
      this.cutChunks(this.opts.eventsPerChunk, false)
    }
  }

  /**
   * 会话绑定/轮换/解绑：旧会话若已选中，先把剩余缓冲切为收尾块（走 gzip + 重试管道），
   * 再重置缓冲与 seq；首绑（null → sid）保留建会话前的录制，归入新会话；
   * sessionId 为 null 表示暂无会话（继续常录，等下次绑定）。
   */
  bindSession(sessionId: string | null, sampled: boolean): void {
    if (sessionId === this.sessionId) {
      this.sampled = sampled
      return
    }
    const rotating = this.sessionId !== null
    if (rotating && this.selected()) this.cutRemainder()
    if (rotating) {
      this.buf = []
      this.bufBytes = 0
      this.lastTs = 0
    }
    this.sessionId = sessionId
    this.sampled = sampled
    this.forced = false
    this.seq = 0
  }

  /** $error 钩子：无视采样强制上传本会话（含已录缓冲，即错误发生前的上下文） */
  forceUpload(): void {
    this.forced = true
    if (this.selected()) this.cutChunks(this.opts.eventsPerChunk, true)
  }

  /**
   * 页面转后台（visibilitychange → hidden）：页面此时仍存活，剩余缓冲走正常 gzip 管道切块，
   * 标记 urgent 以 beacon / fetch keepalive 发出。压缩后通常远小于 64KB，之后即使页面直接卸载也能送达；
   * 移动端切后台不触发 pagehide，也靠这一步把尾巴传走。
   */
  flushHidden(): void {
    if (this.stopped || !this.opts.canRecord() || !this.selected()) return
    if (this.buf.length === 0) return
    for (const group of splitByBytes(this.takeAll(), CHUNK_MAX_BYTES)) {
      const token: PendingUrgent = { items: group, seq: this.seq, superseded: false }
      this.pendingUrgent.push(token)
      this.enqueue(group, true, token)
    }
  }

  /**
   * pagehide 收尾：全部同步发出，不进重试管道（卸载场景重试无意义），按 seq 顺序：
   * ① outbox 里已压缩好、尚未发出的转后台块，直接 beacon；
   * ② 转后台块 gzip 还没完成的：作废其凭据（gzip 完成后不再入队，防双发），事件改为同步明文发出，
   *    放得进一块时沿用原 seq，否则重新编号（原 seq 留空洞，播放器跳过）；
   * ③ 缓冲剩余事件，明文按 FINAL_CHUNK_MAX_BYTES 拆块。
   * 所有块合计请求体不超过 FINAL_WIRE_BUDGET（beacon / keepalive 共用约 64KB 额度），
   * 第一块放不下即停止，其余丢弃并记日志。
   */
  flushFinal(): void {
    if (this.stopped || !this.opts.canRecord() || !this.selected()) return
    let budget = FINAL_WIRE_BUDGET
    let dropped = 0
    let full = false
    /** 预检：按估算的请求体大小判断还放不放得下；放不下即进入「已满」，后续块都不再编码 */
    const fits = (estimate: number): boolean => {
      if (full || estimate > budget) full = true
      return !full
    }
    const fire = (payload: ReplayChunkPayload): void => {
      const wire = byteLength(JSON.stringify(payload))
      if (full || wire > budget) {
        full = true
        dropped += payload.event_count
        return
      }
      budget -= wire
      try {
        void this.opts.send(payload, { preferBeacon: true }).catch(() => {
          // beacon 失败不再降级重试：页面正在卸载
        })
      } catch {
        // 发送实现同步异常忽略
      }
    }

    // ① 已编码未发出的转后台块（在途的队首块不动，避免重复）
    // 普通块留在 outbox：pagehide 也可能进 bfcache，页面恢复后照常重试
    const inFlight = this.pumping ? this.outbox[0] : undefined
    const ready = this.outbox.filter((c) => c.urgent && c !== inFlight)
    this.outbox = this.outbox.filter((c) => !ready.includes(c))
    for (const c of ready) fire(c.payload)

    // ② gzip 未完成的转后台块：接管为明文
    const late = this.pendingUrgent.splice(0)
    for (const token of late) {
      token.superseded = true
      const groups = splitByBytes(token.items, FINAL_CHUNK_MAX_BYTES)
      groups.forEach((group, i) => {
        this.sendPlain(group, groups.length === 1 && i === 0 ? token.seq : this.seq++, fits, fire, (n) => {
          dropped += n
        })
      })
    }

    // ③ 缓冲剩余
    if (this.buf.length > 0) {
      for (const group of splitByBytes(this.takeAll(), FINAL_CHUNK_MAX_BYTES)) {
        this.sendPlain(group, this.seq++, fits, fire, (n) => {
          dropped += n
        })
      }
    }
    if (dropped > 0) this.log(`replay 收尾超出卸载期发送额度，丢弃 ${dropped} 条事件`)
  }

  /**
   * 明文成块交给 fire。先用字节数估算请求体（base64 = 4·⌈n/3⌉ + 信封），预算已满或放不下时
   * 直接丢弃，不做 base64 和 JSON 拼接（卸载期主线程时间宝贵）；单条超出单块上限的事件
   * （如大 DOM 全量快照）卸载期无法送达，同样丢弃。
   */
  private sendPlain(
    group: BufItem[],
    seq: number,
    fits: (estimate: number) => boolean,
    fire: (p: ReplayChunkPayload) => void,
    drop: (n: number) => void
  ): void {
    const raw = group.reduce((n, i) => n + i.len, 0) + group.length + 1
    if (raw > FINAL_CHUNK_MAX_BYTES) {
      drop(group.length)
      return
    }
    const sid = this.sessionId as string
    const estimate = 4 * Math.ceil(raw / 3) + byteLength(this.opts.appKey) + byteLength(sid) + ENVELOPE_OVERHEAD
    if (!fits(estimate)) {
      drop(group.length)
      return
    }
    fire({
      app_key: this.opts.appKey,
      session_id: this.sessionId as string,
      seq,
      event_count: group.length,
      gzip: false,
      payload: base64FromString(`[${group.map((i) => i.json).join(',')}]`)
    })
  }

  destroy(): void {
    this.stopped = true
    if (this.intervalTimer) clearInterval(this.intervalTimer)
    if (this.retryTimer) clearTimeout(this.retryTimer)
    this.intervalTimer = null
    this.retryTimer = null
    this.buf = []
    this.bufBytes = 0
    this.outbox = []
    this.pendingUrgent = []
  }

  // ---------------------------------------------------------------- internal

  private log(...args: unknown[]): void {
    this.opts.log?.(...args)
  }

  /** 会话是否被选中上传：总开关开 + 已绑会话 +（命中采样 或 $error 强传） */
  private selected(): boolean {
    return this.opts.uploadEnabled && this.sessionId !== null && (this.sampled || this.forced)
  }

  private takeAll(): BufItem[] {
    const items = this.buf.splice(0, this.buf.length)
    this.bufBytes = 0
    return items
  }

  private shiftOldest(): void {
    const item = this.buf.shift()
    if (!item) return
    this.bufBytes -= item.len
  }

  /** 切块：满 maxPerChunk 的整批 + （includeRemainder 时）不足一批的尾巴 */
  private cutChunks(maxPerChunk: number, includeRemainder: boolean): void {
    if (!this.sessionId) return
    while (this.buf.length >= maxPerChunk) this.cut(maxPerChunk)
    if (includeRemainder && this.buf.length > 0) this.cut(this.buf.length)
  }

  /** 旧会话收尾：剩余缓冲合成一块（不拆 50，轮换/会话结束场景一次性带走） */
  private cutRemainder(): void {
    if (this.buf.length > 0) this.cut(this.buf.length)
  }

  /** 切出 n 条（超过 CHUNK_MAX_BYTES 时再按字节拆块），进编码与发送管道 */
  private cut(n: number): void {
    const items = this.buf.splice(0, n)
    for (const item of items) this.bufBytes -= item.len
    for (const group of splitByBytes(items, CHUNK_MAX_BYTES)) this.enqueue(group, false)
  }

  /** 一组事件成块：seq 在此时分配；编码串行入链，保证 outbox 顺序与 seq 一致 */
  private enqueue(items: BufItem[], urgent: boolean, token?: PendingUrgent): void {
    const sessionId = this.sessionId as string
    const seq = this.seq++
    const jsons = items.map((i) => i.json)
    this.encodeChain = this.encodeChain
      .then(() => this.encodeChunk(jsons, sessionId, seq))
      .then((payload) => {
        if (token) {
          // 已被 pagehide 接管（明文发出）：丢弃压缩结果，防双发
          if (token.superseded) return
          this.pendingUrgent = this.pendingUrgent.filter((t) => t !== token)
        }
        if (this.stopped) return
        this.outbox.push({ payload, attempts: 0, urgent })
        this.pump()
      })
      .catch((err) => this.log('replay 切块编码失败', err))
  }

  private async encodeChunk(
    jsons: string[],
    sessionId: string,
    seq: number
  ): Promise<ReplayChunkPayload> {
    const arr = `[${jsons.join(',')}]`
    let gzip = false
    let encoded: string
    if (this.opts.gzip) {
      try {
        encoded = base64FromBytes(new Uint8Array(await this.opts.gzip(arr)))
        gzip = true
      } catch {
        // gzip 失败降级明文标记
        encoded = base64FromString(arr)
      }
    } else {
      encoded = base64FromString(arr)
    }
    return {
      app_key: this.opts.appKey,
      session_id: sessionId,
      seq,
      event_count: jsons.length,
      gzip,
      payload: encoded
    }
  }

  /** 串行发送泵：逐块发送，失败按指数退避重试，重试耗尽丢弃后继续下一块 */
  private pump(): void {
    if (this.pumping || this.stopped || this.retryTimer) return
    const head = this.outbox[0]
    if (!head) return
    // 门控关闭（optOut/停用）：待发块直接丢弃（对齐 optOut 清空待发语义）
    if (!this.opts.canRecord()) {
      this.outbox.shift()
      this.log(`replay 块 seq=${head.payload.seq} 丢弃（采集已停用）`)
      this.pump()
      return
    }
    this.pumping = true
    this.opts
      .send(head.payload, { preferBeacon: head.urgent })
      .then((ok) => {
        this.pumping = false
        if (this.stopped) return
        if (ok) {
          this.outbox.shift()
          this.pump()
        } else {
          this.scheduleRetry(head)
        }
      })
      .catch(() => {
        this.pumping = false
        if (!this.stopped) this.scheduleRetry(head)
      })
  }

  private scheduleRetry(head: OutboxChunk): void {
    if (head.attempts >= this.opts.maxRetries) {
      this.outbox.shift()
      this.log(`replay 块 seq=${head.payload.seq} 重试 ${this.opts.maxRetries} 次仍失败，丢弃`)
      this.pump()
      return
    }
    head.attempts++
    const delay = Math.min(
      this.opts.retryBaseDelay * 2 ** (head.attempts - 1),
      this.opts.retryMaxDelay
    )
    this.retryTimer = setTimeout(() => {
      this.retryTimer = null
      this.pump()
    }, delay)
  }
}
