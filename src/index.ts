import {
  browserContextProvider,
  browserIsDnt,
  createBrowserKv,
  createBrowserTransportDeps,
  defaultConfigFetcher,
  IdbQueueStore
} from './adapters'
import { TrackClient } from './core/client'
import { normalizeEndpoint } from './core/utils'
import { runSelfCheck, type PingResult } from './core/selfCheck'
import { SystemClock } from './core/clock'
import { MemoryQueueStore } from './core/storage'
import { Transport } from './core/transport'
import { autocapturePlugin } from './plugins/autocapture'
import { apiMonitorPlugin } from './plugins/api-monitor'
import { errorPlugin } from './plugins/error'
import { exposurePlugin } from './plugins/exposure'
import { pageleavePlugin } from './plugins/pageleave'
import { pageviewPlugin } from './plugins/pageview'
import { visualTrack } from './plugins/visual-track'
import { webVitalsPlugin } from './plugins/web-vitals'
import { geoPlugin } from './plugins/geo'
import type { TrackOptions, TrackPlugin } from './types'

/** selfCheck 连通性探测：GET /track/config，不带 cookie、不缓存、5s 超时 */
async function browserPing(url: string): Promise<PingResult> {
  const ctrl = typeof AbortController === 'undefined' ? undefined : new AbortController()
  const timer = ctrl ? setTimeout(() => ctrl.abort(), 5000) : undefined
  try {
    const res = await fetch(url, { credentials: 'omit', cache: 'no-store', signal: ctrl?.signal })
    let enabled: boolean | undefined
    try {
      const body = (await res.json()) as { data?: { enabled?: boolean } }
      enabled = body?.data?.enabled
    } catch {
      // 非 JSON 应答忽略
    }
    return { status: res.status, enabled }
  } catch {
    return { status: 0 }
  } finally {
    if (timer) clearTimeout(timer)
  }
}

/** 默认插件集：api-monitor / visual-track 默认关闭，需显式加入 */
export function defaultPlugins(): TrackPlugin[] {
  return [
    pageviewPlugin(),
    pageleavePlugin(),
    autocapturePlugin(),
    exposurePlugin(),
    webVitalsPlugin(),
    errorPlugin()
  ]
}

/**
 * 浏览器环境一键初始化：装配 localStorage / IndexedDB / 传输降级链 / 公共属性，
 * hidden 与 pagehide 时自动 beacon 冲刷。
 */
export function createTracker(options: TrackOptions): TrackClient {
  const endpoint = normalizeEndpoint(options.endpoint)
  const getHeaders = (): Record<string, string> => {
    const h = options.headers
    return typeof h === 'function' ? h() : (h ?? {})
  }
  const transport = new Transport(
    // app_key 冗余进 query：请求体解析失败/超限被拒时服务端仍能把拒绝原因归到应用（接入健康页）
    `${endpoint}/track/collect?app_key=${encodeURIComponent(options.appKey)}`,
    createBrowserTransportDeps(),
    getHeaders
  )
  const client = new TrackClient(
    { ...options, plugins: options.plugins ?? defaultPlugins() },
    {
      kv: createBrowserKv(),
      queueStore: typeof indexedDB === 'undefined' ? new MemoryQueueStore() : new IdbQueueStore(),
      transport,
      clock: new SystemClock(),
      contextProvider:
        typeof window === 'undefined' ? undefined : browserContextProvider(options.release),
      configFetcher: defaultConfigFetcher,
      isDnt: browserIsDnt,
      ping: typeof fetch === 'undefined' ? undefined : browserPing,
      selfCheck: runSelfCheck
    }
  )
  if (typeof document !== 'undefined') {
    document.addEventListener(
      'visibilitychange',
      () => {
        if (document.visibilityState === 'hidden') void client.flushBeacon()
      },
      { passive: true }
    )
  }
  if (typeof window !== 'undefined') {
    window.addEventListener('pagehide', () => void client.flushBeacon())
  }
  return client
}

export { TrackClient } from './core/client'
export type { ApiErrorParams, ClientDeps, ExposureParams } from './core/client'
export { runSelfCheck } from './core/selfCheck'
export type {
  CheckStatus,
  PingResult,
  Pinger,
  SelfCheckItem,
  SelfCheckReport,
  SelfCheckRunner,
  SelfCheckState
} from './core/selfCheck'
export { Transport } from './core/transport'
export type { SendResult, TransportDeps } from './core/transport'
export { EventQueue } from './core/queue'
export { SessionManager } from './core/session'
export { IdentityManager } from './core/identity'
export { TimeEventTracker } from './core/timeEvent'
export { MemoryKeyValueStore, MemoryQueueStore } from './core/storage'
export { isSampled } from './core/sampler'
export { SDK_PLATFORM, SDK_VERSION, SCHEMA_VERSION } from './version'
export {
  pageviewPlugin,
  pageleavePlugin,
  autocapturePlugin,
  exposurePlugin,
  webVitalsPlugin,
  errorPlugin,
  apiMonitorPlugin,
  visualTrack,
  geoPlugin
}
export type { GeoPluginOptions, GeoFix } from './plugins/geo'
export { generateSelector, matchesRule } from './plugins/visual-track'
export type { PageviewPluginOptions } from './plugins/pageview'
export type { ApiMonitorPluginOptions } from './plugins/api-monitor'
export { ApiBodyUploader, maskSensitiveBody } from './plugins/api-monitor'
export type {
  ApiBodyPayload,
  ApiBodySendOutcome,
  ApiBodyUploaderOptions
} from './plugins/api-monitor'
export { fingerprintOf } from './plugins/error'
export type {
  KeyValueStore,
  PluginContext,
  Props,
  QueueStore,
  RemoteConfig,
  ReplayController,
  RouteInfo,
  TrackEvent,
  IgnoreErrors,
  TrackOptions,
  TrackPayload,
  TrackPlugin,
  VisualRule
} from './types'
