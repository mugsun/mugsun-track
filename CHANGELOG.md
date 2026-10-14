# 更新日志

本文件记录 [mugsun-track](https://github.com/mugsun/mugsun-track) 的重要变更，格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。包版本以根目录 `package.json` 中 `@mugsun/track-web` 为准。

## [Unreleased]

> 计划版本：**0.3.0**（minor，含下方行为变更）。本 PR 不改 `package.json` 版本号，避免合入即触发自动发布；发版另走版本 PR。

### 行为变更

- **`skipHandledErrors` 默认 `true`**：error 插件（window error / unhandledrejection）与 Vue errorHandler 默认不再上报 `name === 'HttpError'` 及 `handled === true` / `expected === true` 的错误。升级后 `$error` 数量可能下降；需要旧行为请设 `skipHandledErrors: false`，或用 `trackApiError` 单独统计接口失败。
- collect 上报地址追加 `?app_key=`（网关/CDN 访问日志会出现 appKey；appKey 本就公开，非机密）。

### 修复

- 回放收尾块丢失：pagehide 时原来把剩余缓冲（最多 10MB）合成一个明文块用 beacon 发出，超过 sendBeacon 的 64KB 限额或服务端单块上限（明文约 1.07MB）就整块丢失。现在：① 页面转后台（`visibilitychange → hidden`）时先把缓冲走 gzip 管道，以 beacon / fetch keepalive 发出，移动端切后台也能覆盖；② pagehide 剩余部分按 44KB 明文拆块，每块都低于 beacon 限额，卸载期总量上限约 88KB，超出部分丢弃最晚的事件并记日志；③ 普通切块也按 1MB 明文拆分，避免触发服务端的 413
- 错误堆栈：`sanitizeProps` 对顶层 `stack` 放宽到 4096 字符，与 error 插件的截断和服务端（mugsun-boot `PROPS_STACK_MAX_LEN`）一致。之前所有字符串一律截到 1024，`$error` 的堆栈实际只剩 1024 字符；其它字符串属性仍是 1024

- endpoint 末尾斜杠/空白统一归一，collect、config 与自检 ping 不再出现 `//track/...`

### 新增

- `tracker.selfCheck()`：结构化接入自检（config / ping / sampling / consent / privacy / queue / replay / filters，每项 ok/warn/fail + message + fix），只真实请求一次 `GET /track/config?app_key=`，不发送用户数据。实现由 `createTracker` 注入，不进 core 入口
- `beforeSend(event)` 钩子（返回 null/false 丢弃；只合并返回的 props；抛错默认丢弃，`beforeSendOnError: 'keep'` 可改为发送原事件；不覆盖回放与接口响应体）、`ignoreErrors`（字符串/RegExp/谓词）、`skipHandledErrors` 开关（默认值见上方「行为变更」）
- `trackApiError({ url, method, status, bizCode, message, durationMs })`：手动上报 `api_request`（success=false, source=manual）；url 与 api-monitor 同口径脱敏敏感 query（`token` / `access_token` 等值替换为 `***`）后截断 512
- 服务端可凭 collect 地址上的 `app_key` 对解析失败/超限的请求归因（接入健康）

### 体积

- core.js gzip 5.48 → 6.33 KB（门禁 8 KB）；index.js gzip 14.99 → 18.06 KB；vue/index.js 9.94 → 13.28 KB

### 文档

- CONTRIBUTING 补充发版流程（改版本号 + CHANGELOG → 合入 main → release.yml 自动发布），中英双语

## [0.2.0] - 2026-10-13

### 变更

- api-monitor：上报 URL 剥离敏感 query（`token` / `access_token` / `authorization` / `id_token` / `refresh_token` 等，大小写不敏感，值替换为 `***`；业务参数保留）。与 [隐私与合规](https://docs.mugsun.com/track/privacy) 对齐；docs 站正文若仍写旧行为需另改 `mugsun-docs`

### 变更（行为 / Breaking）

- **回放默认遮罩页面文本**：`rrweb.record` 默认传入 `maskTextSelector: '*'`（此前仅 `maskAllInputs`）。调试可在 `replayPlugin({ maskTextSelector: false })` 显式关闭，或传入自定义选择器。
- **`apiBodyMaskEnabled` 默认改为 `true`**：开启响应体采集时，JSON body 按内置敏感键清单脱敏后再上传。依赖全文 body 的接入请显式设置 `apiBodyMaskEnabled: false`（或远端下发 `0`）。

### 迁移

1. 升级至 `0.2.0` 后，回放画面中的页面文本默认被遮罩；若需可读文本回放，在注册 replay 插件时传 `maskTextSelector: false`（或更窄的选择器）。
2. 若业务依赖 api-body 原文（含 password/token/phone 等字段），升级后须显式 `apiBodyMaskEnabled: false`，否则敏感键值会变为 `***`。
3. 已于 2026-10-13 经 release 工作流（npm Trusted Publishing）发布至 npm。

### 说明

- URL 敏感 query 剥离来自 #2（T1），已合入 main。
- 隐私页源码在 `mugsun-docs`；本仓 README/CHANGELOG 已对齐 docs.mugsun.com/track/privacy 承诺。

## [0.1.1] - 2026-10-12

相对 npm 已发布的 `0.1.0`，main tip 含以下未发包变更；本版本对齐 `package.json` / `SDK_VERSION`，**尚未**执行 `npm publish`（需维护者令牌）。

### 新增

- `geo` 可选定位插件：每会话采集一次，支持配置透传；默认不进入 `defaultPlugins`
- 圈选埋点：草稿提交失败时展示服务端说明；事件名不合法时提示仅可用字母、数字与下划线

### 变更

- 包元数据仓库地址改为 `mugsun/mugsun-track`（npm `0.1.0` 仍指向旧 `curdx/mugsun-track`）
- README / 贡献指南与架构说明更新（文档向，不影响运行时）

### 说明

- 尚未打 GitHub Release / git tag；发布前以本仓 CI（typecheck / test / build）为准

## [0.1.0] - 2026-08-19

### 新增

- `@mugsun/track-web` `0.1.0`：嵌入式采集 SDK（core、默认插件、Vue 集成、replay 独立入口）
- 与 `mugsun-boot` track 模块、看板路径的对接说明见 README

### 说明

- 已发布至 npm；当时无 GitHub Release tag

[Unreleased]: https://github.com/mugsun/mugsun-track/commits/main
[0.2.0]: https://github.com/mugsun/mugsun-track/compare/3a36902...HEAD
[0.1.1]: https://github.com/mugsun/mugsun-track/compare/c20fa8b...3a36902
[0.1.0]: https://github.com/mugsun/mugsun-track/commits/main?since=2026-08-01&until=2026-08-20
