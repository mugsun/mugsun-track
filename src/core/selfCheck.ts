import type { ResolvedTrackOptions } from '../types'

export type CheckStatus = 'ok' | 'warn' | 'fail'

export interface SelfCheckItem {
  /** 检查项 id：config.endpoint / config.appKey / config.conflict / ping / sampling / consent / privacy / queue / replay / filters */
  id: string
  status: CheckStatus
  message: string
  /** 修复建议；status=ok 时为空串 */
  fix: string
}

export interface SelfCheckReport {
  /** 最差一项的状态 */
  status: CheckStatus
  /** 生成时刻 epoch ms */
  at: number
  sdkVersion: string
  items: SelfCheckItem[]
}

/** 自检连通性探测结果：status=0 表示网络层失败（断网/CORS/超时） */
export interface PingResult {
  status: number
  /** 应用在服务端是否启用（/track/config 下发的 enabled） */
  enabled?: boolean
}

export type Pinger = (url: string) => Promise<PingResult>

/** 自检所需的客户端只读快照（不含任何用户数据：无 distinct_id / 事件内容） */
export interface SelfCheckState {
  options: ResolvedTrackOptions
  disabled: boolean
  dnt: boolean
  optedOut: boolean
  sampled: boolean
  queueSize: number
  replayLoaded: boolean
  pluginNames: string[]
}

export type SelfCheckRunner = (
  s: SelfCheckState,
  ping: Pinger | undefined,
  now: number,
  sdkVersion: string
) => Promise<SelfCheckReport>

const RANK: Record<CheckStatus, number> = { ok: 0, warn: 1, fail: 2 }

/**
 * 接入自检：配置 / 连通性（真实轻量 GET /track/config，只带 app_key）/ 采样与同意 / 隐私默认值 /
 * 队列 / 回放 / 错误过滤。不发送任何用户数据，不写入事件队列
 */
export async function runSelfCheck(
  s: SelfCheckState,
  ping: Pinger | undefined,
  now: number,
  sdkVersion: string
): Promise<SelfCheckReport> {
  const o = s.options
  const items: SelfCheckItem[] = []
  const add = (id: string, status: CheckStatus, message: string, fix = '') =>
    items.push({ id, status, message, fix: status === 'ok' ? '' : fix })

  // ---- config
  const endpointOk = /^https?:\/\/[^/\s]+/i.test(o.endpoint)
  add(
    'config.endpoint',
    endpointOk ? 'ok' : 'fail',
    endpointOk ? `endpoint=${o.endpoint}` : `endpoint 不是合法的 http(s) 地址：${o.endpoint}`,
    'endpoint 填服务端根地址，如 https://api.example.com（SDK 自动拼 /track/collect）'
  )
  if (endpointOk && /\/track(\/collect)?$/.test(o.endpoint)) {
    add(
      'config.endpoint',
      'warn',
      'endpoint 已包含 /track 路径，实际上报地址会重复拼接',
      '去掉 endpoint 末尾的 /track 或 /track/collect'
    )
  }
  if (
    endpointOk &&
    typeof location !== 'undefined' &&
    location.protocol === 'https:' &&
    o.endpoint.startsWith('http:')
  ) {
    add(
      'config.endpoint',
      'fail',
      'HTTPS 页面上报到 HTTP 地址会被浏览器拦截（混合内容）',
      'endpoint 改用 https://'
    )
  }
  const keyOk = /^[A-Za-z0-9_-]{4,64}$/.test(o.appKey)
  add(
    'config.appKey',
    keyOk ? 'ok' : 'warn',
    keyOk ? 'appKey 格式正常' : 'appKey 含空白或异常字符',
    '从管理后台「埋点应用」复制 appKey，注意首尾空格'
  )
  const conflicts: string[] = []
  if (o.batchSize > o.maxBatchSize) conflicts.push('batchSize > maxBatchSize')
  if (o.apiBodyEnabled && o.apiMonitorEnabled === false)
    conflicts.push('apiBodyEnabled 开启但 apiMonitorEnabled 关闭')
  if ((o.apiMonitorEnabled || o.apiBodyEnabled) && !s.pluginNames.includes('api-monitor'))
    conflicts.push('开启了接口监控但未加载 api-monitor 插件')
  if (o.geoEnabled && !s.pluginNames.includes('geo'))
    conflicts.push('geoEnabled 开启但未加载 geo 插件')
  if (o.visualRules?.length && !s.pluginNames.includes('visual-track'))
    conflicts.push('配置了 visualRules 但未加载 visual-track 插件')
  add(
    'config.conflict',
    conflicts.length ? 'warn' : 'ok',
    conflicts.length ? conflicts.join('；') : '无冲突配置',
    '按提示补齐插件或调整选项'
  )
  if (!o.enabled) {
    add(
      'config.enabled',
      'fail',
      '采集总开关关闭（本地 enabled=false 或服务端停用应用）',
      '检查 enabled 选项与后台应用状态'
    )
  }

  // ---- ping
  if (!endpointOk) {
    add('ping', 'fail', 'endpoint 非法，跳过连通性探测', '先修正 endpoint')
  } else if (!ping) {
    add('ping', 'warn', '当前环境无 fetch，跳过连通性探测', '在浏览器环境运行自检')
  } else {
    const url = `${o.endpoint}/track/config?app_key=${encodeURIComponent(o.appKey)}`
    let r: PingResult
    try {
      r = await ping(url)
    } catch {
      r = { status: 0 }
    }
    if (r.status === 0) {
      add(
        'ping',
        'fail',
        '无法连接服务端（网络错误/CORS/超时）',
        '确认 endpoint 可达，并把当前站点加入服务端 CORS 白名单'
      )
    } else if (r.status === 400 || r.status === 404) {
      add(
        'ping',
        'fail',
        `服务端返回 ${r.status}：应用不存在或地址错误`,
        '核对 appKey 是否属于该服务端，endpoint 是否指向 mugsun 服务'
      )
    } else if (r.status >= 300) {
      add('ping', 'fail', `服务端返回 HTTP ${r.status}`, '检查网关/反向代理是否放行 /track/*')
    } else if (r.enabled === false) {
      add('ping', 'fail', '服务端应用已停用，上报会被拒绝', '在管理后台启用该埋点应用')
    } else {
      add('ping', 'ok', '服务端可达，应用存在')
    }
  }

  // ---- sampling / consent
  if (o.sampleRate <= 0) {
    add('sampling', 'fail', 'sampleRate=0，不会采集任何事件', '调大本地或后台下发的采样率')
  } else {
    add(
      'sampling',
      s.sampled ? 'ok' : 'warn',
      s.sampled
        ? `sampleRate=${o.sampleRate}，当前设备在样本内`
        : `sampleRate=${o.sampleRate}，当前设备不在样本内（本机不上报属正常）`,
      '调试时临时把 sampleRate 设为 100'
    )
  }
  if (s.dnt) {
    add(
      'consent',
      'warn',
      '浏览器开启 Do Not Track，SDK 已停用',
      '尊重用户选择；调试可设 respectDnt=false'
    )
  } else if (s.optedOut) {
    add('consent', 'warn', '用户已 optOut，SDK 不采集', '用户同意后调用 optIn()')
  } else {
    add('consent', 'ok', 'DNT 未生效、未 optOut')
  }

  // ---- privacy
  const priv: string[] = []
  // 默认（未设置）也提示：个人信息字段默认原文上传；只是提示（warn），不会 fail
  if (o.apiBodyEnabled && o.apiBodyMaskEnabled !== true)
    priv.push('响应体采集已开启，个人信息字段未脱敏（凭证类键始终脱敏）')
  if (!o.respectDnt) priv.push('respectDnt=false')
  add(
    'privacy',
    priv.length ? 'warn' : 'ok',
    priv.length ? priv.join('；') : `隐私默认值生效（屏蔽选择器 ${o.maskSelectors.length} 个）`,
    '响应体含敏感字段时设 apiBodyMaskEnabled: true；如无必要不要关闭 respectDnt'
  )

  // ---- queue
  const ratio = s.queueSize / o.queueCapacity
  add(
    'queue',
    ratio >= 0.8 ? 'warn' : 'ok',
    `队列积压 ${s.queueSize}/${o.queueCapacity}`,
    '积压持续偏高说明上报失败在退避重试，检查 ping 项与服务端拒绝原因'
  )

  // ---- replay
  if (o.replayEnabled && !s.replayLoaded) {
    add(
      'replay',
      'warn',
      'replayEnabled 开启但回放插件未加载',
      "从 '@mugsun/track-web/replay' 引入 replayPlugin 并加入 plugins"
    )
  } else {
    add('replay', 'ok', s.replayLoaded ? '回放插件已加载' : '未启用回放')
  }

  // ---- filters
  const f: string[] = []
  if (o.beforeSend) f.push(`beforeSend(抛错${o.beforeSendOnError === 'keep' ? '保留' : '丢弃'})`)
  if (o.ignoreErrors)
    f.push(
      typeof o.ignoreErrors === 'function'
        ? 'ignoreErrors(谓词)'
        : `ignoreErrors(${o.ignoreErrors.length} 条)`
    )
  f.push(o.skipHandledErrors ? '跳过 HttpError/已处理错误' : '上报全部错误')
  add('filters', 'ok', f.join('，'))

  let status: CheckStatus = 'ok'
  for (const it of items) if (RANK[it.status] > RANK[status]) status = it.status
  return { status, at: now, sdkVersion, items }
}
