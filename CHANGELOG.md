# 更新日志

本文件记录 [mugsun-track](https://github.com/mugsun/mugsun-track) 的重要变更，格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。包版本以根目录 `package.json` 中 `@mugsun/track-web` 为准。

## [Unreleased]

### 变更

- api-monitor：上报 URL 剥离敏感 query（`token` / `access_token` / `authorization` / `id_token` / `refresh_token` 等，大小写不敏感，值替换为 `***`；业务参数保留）。与 [隐私与合规](https://docs.mugsun.com/track/privacy) 对齐；docs 站正文若仍写旧行为需另改 `mugsun-docs`

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
[0.1.1]: https://github.com/mugsun/mugsun-track/compare/c20fa8b...HEAD
[0.1.0]: https://github.com/mugsun/mugsun-track/commits/main?since=2026-08-01&until=2026-08-20
