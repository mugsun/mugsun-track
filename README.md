# @mugsun/track-web

[English](./README_EN.md) | 简体中文

Web 端行为采集 SDK。核心产物体积约 5.5KB（gzip）。默认将事件报送至可私有化部署的服务端，并与管理端分析能力配合使用。

[文档](https://docs.mugsun.com/track/) · [接入说明](https://docs.mugsun.com/track/first-event) · [npm](https://www.npmjs.com/package/@mugsun/track-web)

[![npm](https://img.shields.io/npm/v/@mugsun/track-web)](https://www.npmjs.com/package/@mugsun/track-web)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)

## 安装与初始化

```bash
pnpm add @mugsun/track-web
```

```ts
import { createTracker } from '@mugsun/track-web'

const track = createTracker({
  endpoint: 'https://your-server.com', // 报送地址为 {endpoint}/track/collect
  appKey: 'your-app-key',              // 于管理端「埋点分析 → 接入管理」创建
})

track.track('button_click', { name: 'buy' })
```

Vue 3：

```ts
import MugsunTrack from '@mugsun/track-web/vue'
app.use(MugsunTrack, { endpoint, appKey, router })
```

完整接入步骤见 [文档 · 第一个事件](https://docs.mugsun.com/track/first-event)。公网演示环境尚未提供，请按文档在本地部署 boot 与 pc 进行验证。

## 功能概述

本 SDK 面向需自主掌控采集、存储与展示链路的部署场景。默认对接 [mugsun-boot](https://github.com/mugsun/mugsun-boot) 的 `/track/collect` 接口及 [mugsun-pc](https://github.com/mugsun/mugsun-pc) 管理端；亦可对接符合事件协议的自建服务。

默认启用 pageview、pageleave、autocapture、exposure、web-vitals、error 等插件。会话回放、圈选埋点、接口监控及精确地理位置采集需显式注册，并以独立入口加载。事件队列持久化于 IndexedDB，在网络中断或页面刷新后按指数退避重试；传输依次尝试 sendBeacon、fetch keepalive、XHR。每条事件携带稳定的 `event_id`，供服务端去重。

默认遵循 Do Not Track；提供 `optOut()` / `optIn()`；不采集输入框内容；对 password 及 `maskSelectors` 匹配的子树实施屏蔽；会话回放默认遮罩输入。隐私说明见 [隐私与合规](https://docs.mugsun.com/track/privacy)。接口与配置以 [文档](https://docs.mugsun.com/track/) 为准。

## 架构

<p align="center">
  <img src="https://raw.githubusercontent.com/mugsun/mugsun-docs/main/public/brand/arch/track-iso-zh.jpg" alt="Architecture" width="100%" />
</p>

`appKey` 可在浏览器端被读取，不作为机密凭证。服务端通过应用存在性校验、基于 appKey 与 IP 的限流、有界队列及事件校验实施防护。

## 相关仓库

| 仓库 | 说明 |
| --- | --- |
| 本仓库 | 浏览器端 SDK（npm 发布；亦可 `file:` 本地引用） |
| [mugsun-boot](https://github.com/mugsun/mugsun-boot) | 事件摄入、配置下发与聚合 |
| [mugsun-pc](https://github.com/mugsun/mugsun-pc) | 接入管理与分析界面 |
| [mugsun-docs](https://github.com/mugsun/mugsun-docs) | 文档站点 [docs.mugsun.com](https://docs.mugsun.com/) |

与 mugsun-pc 并列开发时，本仓库不提交 `dist/`，须先执行 `pnpm build`，或在 pc 仓库执行 `pnpm setup:sdk`。

## 本地构建

```bash
pnpm install
pnpm test
pnpm build
```

当前版本为 **0.1.0**。单元测试约 155 例。核心产物 gzip 体积门禁不超过 8KB。导出入口：主包、`/vue`、`/replay`、`/core`。

## 许可证

[MIT](./LICENSE)
