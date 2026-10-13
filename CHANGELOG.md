# 更新日志

本文件记录 [mugsun-track](https://github.com/mugsun/mugsun-track) 的重要变更，格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。包版本以根目录 `package.json` 中 `@mugsun/track-web` 为准。

## [Unreleased]

### 计划

- （暂无已定条目）

## [0.2.0] - 2026-10-13

### 变更（行为 / Breaking）

- **回放默认遮罩页面文本**：`rrweb.record` 默认传入 `maskTextSelector: '*'`（此前仅 `maskAllInputs`）。调试可在 `replayPlugin({ maskTextSelector: false })` 显式关闭，或传入自定义选择器。
- **`apiBodyMaskEnabled` 默认改为 `true`**：开启响应体采集时，JSON body 按内置敏感键清单脱敏后再上传。依赖全文 body 的接入请显式设置 `apiBodyMaskEnabled: false`（或远端下发 `0`）。

### 迁移

1. 升级至 `0.2.0` 后，回放画面中的页面文本默认被遮罩；若需可读文本回放，在注册 replay 插件时传 `maskTextSelector: false`（或更窄的选择器）。
2. 若业务依赖 api-body 原文（含 password/token/phone 等字段），升级后须显式 `apiBodyMaskEnabled: false`，否则敏感键值会变为 `***`。
3. 本版本**尚未** `npm publish`；以仓内 `package.json` / `SDK_VERSION` 为准。

### 说明

- URL 敏感 query 剥离见并行 PR（T1），不在本版本 diff 内。
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
