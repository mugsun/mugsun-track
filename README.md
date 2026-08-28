# @mugsun/track-web

**[English](./README_EN.md)** | 简体中文

<p>
  <a href="https://www.npmjs.com/package/@mugsun/track-web"><img src="https://img.shields.io/npm/v/@mugsun/track-web" alt="npm version"></a>
  <a href="https://bundlephobia.com/package/@mugsun/track-web"><img src="https://img.shields.io/bundlephobia/minzip/@mugsun/track-web" alt="bundle size"></a>
  <img src="https://img.shields.io/badge/core_gzip-~5.5KB-blue" alt="core gzip">
  <img src="https://img.shields.io/badge/tests-149_passed-brightgreen" alt="tests">
</p>

Web 埋点 SDK，框架无关。core gzip 约 5.5KB（门禁 ≤ 8KB），会话回放走独立入口懒加载。

## 特点

- 6 个默认插件 + 3 个可选（接口监控 / 回放 / 圈选）
- 批量队列 + IndexedDB，断网补发；sendBeacon → fetch → XHR 降级
- `event_id` 用 UUID，服务端按 id 去重
- 会话 30 分钟滑动过期，多标签共享
- 采样按 anonymous_id 哈希，同会话结果一致
- 默认不采输入框 value，password 和 mask 选择器屏蔽

## 数据流

```mermaid
flowchart LR
  P[插件] --> Q[队列] --> T[上报]
  T --> I[/track/collect]
  I --> DB[(track_event)]
```

配套服务端是 mugsun-boot 埋点模块；协议见下文，也可接自建后端。

## 安装

```bash
npm i @mugsun/track-web
```

本地联调：

```bash
cd mugsun-track && pnpm install && pnpm build
pnpm add @mugsun/track-web@file:../mugsun-track
```

## appKey

管理端 **埋点分析 → 接入管理** 新建应用。浏览器里的 appKey 不是机密，靠限流和校验防滥用。

## 快速开始

```ts
import { createTracker } from '@mugsun/track-web'

const track = createTracker({
  endpoint: 'https://your-server.com',
  appKey: 'your-app-key',
  release: '1.0.0'
})

track.track('button_click', { name: 'buy' })
```

Vue 3：

```ts
import MugsunTrack from '@mugsun/track-web/vue'
app.use(MugsunTrack, { endpoint, appKey, release, router })
```

登录后 `track.identify(userId)`，登出 `track.reset()`。

## API（常用）

| 方法 | 说明 |
| --- | --- |
| `track(event, props?)` | 自定义事件 |
| `identify(userId)` | 绑定登录用户 |
| `reset()` | 登出，换 anonymous_id |
| `flush()` / `flushBeacon()` | 立即上报 |
| `optOut()` / `optIn()` | 停止/恢复采集 |
| `destroy()` | 卸载 |

`v-track:click` / `v-track:exposure` 见英文文档或源码注释。

## 插件

| 插件 | 默认 | 事件 |
| --- | --- | --- |
| pageview / pageleave | 开 | `$pageview` / `$pageleave` |
| autocapture | 开 | `$click` / `form_submit` |
| exposure | 开 | `$exposure` |
| web-vitals | 开 | `$web_vitals` |
| error | 开 | `$error` |
| api-monitor | 关 | `api_request` |
| replay | 关 | rrweb 回放块 |
| visual-track | 关 | 圈选规则命中 |

回放：`import { replayPlugin } from '@mugsun/track-web/replay'`，细节见源码 `packages/replay`。

## 配置下发

启动读缓存，`GET /track/config?app_key=` 拉采样率、开关、mask、回放等。**新配置下次启动生效**，会话中不热更。

## 事件协议

```
POST {endpoint}/track/collect
{ app_key, schema_version, sdk, sent_at, events: [...] }
```

`$` 开头为保留事件名；自定义名 `^[A-Za-z][A-Za-z0-9_]{0,63}$`。

## 工程

```bash
pnpm install
pnpm build
pnpm test
pnpm typecheck
```

入口：`@mugsun/track-web`、`/core`、`/vue`、`/replay`。

提交信息见 [.github/COMMIT_CONVENTION.md](.github/COMMIT_CONVENTION.md)。

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=mugsun/mugsun-track&type=Date)](https://star-history.com/#mugsun/mugsun-track&Date)

## License

MIT
