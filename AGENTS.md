# AGENTS.md — mugsun-track

本文件写给在本仓工作的开发者和 AI 助手。内容以本仓代码为准；与代码不一致时以代码为准，并请顺手修正本文件。

## 仓库是什么

浏览器端行为采集 SDK，npm 包 `@mugsun/track-web`（版本以根 `package.json` 为准；`src/version.ts` 的 `SDK_VERSION` 是手写常量，需手工同步，构建不注入、CI 和 release-check 都不校验）。对接 mugsun-boot：`endpoint` 与 `appKey` 都必填、没有默认值，上报地址为 `${endpoint}/track/collect?app_key=…`。

本仓**没有** Flyway、Java 分层或服务端租户实现。

## 目录分层

| 路径 | 作用 |
| --- | --- |
| `src/index.ts` | 浏览器入口：`createTracker`、默认插件集 |
| `src/core.ts` | 精简 core 入口（体积门禁作用于此，gzip ≤ 8KB） |
| `src/core/` | 客户端内核（`client`、`queue`、`transport`、`session`、`storage` 等） |
| `src/plugins/` | 插件：`pageview`、`pageleave`、`autocapture`、`error`、`exposure`、`web-vitals`、`replay`、`visual-track`、`api-monitor`、`geo`；`page-tracker.ts` 不是插件，是 pageview / pageleave 共用的计时器 |
| `src/vue/` | Vue 插件（`app.use(MugsunTrack, …)`），见下文 |
| `src/adapters.ts` | 浏览器适配（KV、传输、DNT/GPC、`IdbQueueStore`、`defaultConfigFetcher`、`browserContextProvider`） |
| `tests/` | Vitest 用例 |
| `scripts/` | `check-changelog.py`、`check-workflows.py`、`report-size.mjs`、`release-check.sh`，以及下文「门禁与共享脚本」里的共享门禁脚本 |

导出子路径见 `package.json` 的 `exports`：`.`、`./core`、`./vue`、`./replay`，各有 `types` / `import` / `require` 三个条件，另配 `typesVersions`。`./replay` 对应 `src/plugins/replay`，rrweb 是外部依赖、运行时按需动态加载。

## 命名与约定

- 对外主 API：`createTracker(options: TrackOptions): TrackClient`（`src/index.ts`）：
  - 传 `plugins` 会**整体替换**默认插件，不是追加。
  - 没有 IndexedDB 时退回内存队列（`MemoryQueueStore`）。
  - `visibilitychange` 变为 hidden 和 `pagehide` 时用 beacon 冲刷。
  - `selfCheck` 走 `GET /track/config`。
- `./core` 入口没有 `createTracker`，需自行注入 deps；没注入 `deps.selfCheck` 时 `selfCheck()` 会直接 reject。
- 默认插件集 `defaultPlugins()` 只有 `pageview`、`pageleave`、`autocapture`、`exposure`、`web-vitals`、`error` 六个。`api-monitor`、`visual-track`、`geo` 必须显式加入；`replay` 只能从 `./replay` 引入。这关系到采集范围，改动属于隐私敏感变更。
- 插件契约：工厂函数返回 `TrackPlugin { name, setup(ctx) }`，`setup` 可返回 teardown；`ctx` 含 `client`、`options`、`log`（`src/types.ts`）。
- Vue 插件 `app.use(MugsunTrack, …)`：provide 实例并挂 `$track`，注册 `v-track` 指令，链式接管 `errorHandler`；传了 `router` 时切到手动 pageview，`route_path` 取 matched 叶子记录的路由模板。
- 行为变更（默认值、脱敏、采样）必须在 `CHANGELOG.md` 写清迁移说明。

## 发布

`CONTRIBUTING.md` 有面向贡献者的中英文发版说明；以本节和 `.github/workflows/release.yml` 为准。

- 改 `package.json` 的 `version`（同时手工同步 `SDK_VERSION`）并推入 `main`，会触发 Release workflow；也可手动 `workflow_dispatch`。共三个 job：
  1. `check`：不挂 environment，跑 `scripts/release-check.sh`。版本已在 npm 上则 `skip=true`，整个 run 绿色跳过；只有 E404 算未发布，其他错误直接失败；版本须是规范 semver 且严格大于 npm latest；带 `-` 的版本发到 `next`，否则 `latest`。
  2. `publish`：只在 `main` 且 `skip=false` 时跑，挂 `npm-release` 环境，**需 mugsun 审批**后才执行；只有这个 job 有 `id-token: write`。依次 typecheck、test、build，生成并上传 CycloneDX SBOM，再 `npm publish --provenance --tag $TAG`（OIDC Trusted Publishing）。
  3. `github-release`：`contents: write`，建 `v<版本>` 的 GitHub Release 并附 SBOM。
- **不要**本地 `npm publish`，也不要配置 npm token。

## 隐私与安全相关默认值

以当前代码与 CHANGELOG 为准，改默认值属于敏感行为变更。常见开关包括：`respectDnt`、`respectGpc`、`apiBodyMaskEnabled`、回放 `maskTextSelector` / `maskAllInputs` 等。不要在文档或示例里写死与代码不符的默认值。

## 组件速查

| 需求 | 位置 |
| --- | --- |
| 创建实例 | `createTracker`（`src/index.ts`） |
| 自检 | `runSelfCheck` / `TrackClient` 上的 selfCheck |
| 版本常量 | `SDK_VERSION`、`SCHEMA_VERSION`（`src/version.ts`） |
| 会话回放 | `src/plugins/replay`、导出 `./replay` |
| Vue 插件 / 指令 | `src/vue`（`index.ts`、`directive.ts`） |
| CHANGELOG 门禁 | `scripts/check-changelog.py`（新增行 `len <= 80`，子项缩进两格） |

## 测试与构建

```bash
pnpm install --frozen-lockfile
pnpm run typecheck    # tsc --noEmit
pnpm run test         # vitest run
pnpm run build        # tsup + report-size
python3 scripts/check-changelog.py origin/main
python3 scripts/check-workflows.py
```

- 体积门禁（`scripts/report-size.mjs`，`pnpm build` 内执行）：core 入口 gzip ≤ 8KB；replay 入口（ESM 和 CJS）gzip ≤ 6KB，且禁止把 rrweb 打包进去。超限时 `pnpm build` 退出码为 1。
- `check-changelog.py` 只检查相对基准新增的行；CI 里 push 用 before、PR 用 base 作基准。本地用 `origin/main`，用 `HEAD~1` 只会查最后一个提交。
- `.github/workflows/security.yml`（Security scan）跑 osv-scanner、`pnpm audit --audit-level=high`、gitleaks（全历史）和 gate audit；触发：push 到任意分支、PR 指向 main、每天定时一次、可手动触发；main 上定时任务失败或取消、main 上 push 的 gate audit 失败会开 issue（以 security.yml 为准）。本地可跑 `pnpm audit --audit-level=high` 和 `gitleaks git --redact --no-banner --exit-code 1 .`；osv 步骤照 workflow 执行。
- 版本要求：`engines` 为 node ≥ 22.13、pnpm ≥ 11.11（另见 `packageManager`）；CI 用 Node 22，Release 用 Node 24。

## 门禁与共享脚本

- 共享文件：`scripts/` 下的 `vuln-gate.py`、`gate-audit.py`、`test_vuln_gate.py`、`test_gate_audit.py`、`mutate_vuln_gate.py`、`vuln-gate.sha256`。各仓共用一份，**禁止在本仓单独修改**；升级照共享副本 README 的流程整套替换，并同步哈希表。
- `osv-scanner.toml` 的忽略条目（`[[IgnoredVulns]]`）必须有 `id`、`scope`、`added`、`ignoreUntil`、`reason` 五项，不许多写其他键。`scope` 只能是 `prod`（`ignoreUntil` 距 `added` 不超过 30 天）或 `dev`（不超过 90 天），日期用 TOML 原生日期。新增或修改条目要找安全官审，复核时要核对 scope 是否属实。
- gate audit（`security.yml` 的 `gate-audit` job，脚本 `scripts/gate-audit.py`）：比较 base 和 head，下列任一情况判红：
  - 改动 `.github/workflows/`、`.github/actions/`、`.github/CODEOWNERS`；
  - 改动共享脚本、哈希表、`check-workflows.py`、`test_security_workflow.py`；
  - 改动任意目录下的 `osv-scanner.toml`、`.gitleaks.toml`、`.gitleaksignore`；
  - 新增行里出现 gitleaks 行内放行注释；共享脚本和 base 上哈希表不一致；
  - base 为空、全 0 或找不到。
  - 路径先做 NFC 规范化再忽略大小写比较；文件名含引号开头或反斜杠直接判红。
  - main 上的 push 判红时自动开 issue「门禁审计失败，需安全官复核」。提交说明要写清理由，并交安全官复核。
- 敏感文件清单（改动属于敏感改动、需安全官复核）：`.github/` 下全部文件（含 `CODEOWNERS`）、上面的共享脚本和哈希表、`osv-scanner.toml`、`.gitleaks.toml`、`.gitleaksignore`、gitleaks 行内放行注释，以及下文「提交与推送」列的脱敏默认值、采集范围、新依赖。
- `.github/CODEOWNERS` 只起标注作用：本仓不走 PR，也没开「需要 code owner 审核」，真正的拦截靠 gate audit。

## 本地构建

- 重型任务（构建、类型检查、e2e、测试容器、dev server 等）一律经仓库父目录 `mugsun/` 下的 `_locks/heavy.sh` 排队，同一时间只跑一个：
  ```bash
  ../_locks/heavy.sh <名字> <做什么> -- <命令...>
  # 例：../_locks/heavy.sh <名字> "全量测试" -- pnpm test
  ```
- 前面有任务时脚本每 30 秒重试并打印当前占用者；空闲内存低于 30% 时不开跑（退出码 75），先停掉闲置的 dev server 再试。
- 脚本会在未设置时自动设 `NODE_OPTIONS=--max-old-space-size=3072`，不要在命令里再调大。
- dev server 用完即停，不要挂着。

## 提交与推送

- Conventional Commits，主题中文，不超过 50 字，不用 emoji；详见 `.github/COMMIT_CONVENTION.md`。
- `CHANGELOG.md` 写在 `## [Unreleased]` 下，**每行不超过 80 字**（CI 用 `scripts/check-changelog.py` 检查本次新增行）。
- 不用 `git stash`；切换工作用 `git worktree`。
- 不开 PR：本地分支实测 → 推分支 → 代码质量官审（敏感改动加安全官）→ 作者普通快进推入 `main`。
- **推送规则（3.16）：本仓没有配置必需检查和分支保护。`CI` 和 `Security scan` 推任意分支都会跑；分支最新的提交必须先在分支上跑完这两个 workflow 且全绿（`gh run list --commit <sha>`），才能快进合入 main。不要 force push，不要 rebase 已推送分支。**
  - 例外：改动 `.github/` 或受保护文件的提交，gate audit 必然判红。只要除 gate audit 外全绿、且安全官已复核，也可以快进。推入 main 后 gate audit 自动开的 issue，要在里面写明改动原因和 `gate-audit.py` 的 sha256，再关闭。
  - 涉及 `.github/` 的提交不能只看红绿，要看日志里的 `::error::`：gate audit 跑的是本次提交里的 workflow，同一提交可以把它改掉，所以必须确认报错只是预期的几类，并已交安全官复核。
  - main 上每个 SHA 的运行单独一组、不会被后来的推送取消，每次推送的结果都会保留；功能分支上同一事件的新推送会取消旧运行。
- **提交身份（3.18）：新提交的作者和提交者一律用 `mugsun <bydongxin@gmail.com>`。** 用仓库级 config（`git config user.name` / `user.email`）或 `git -c` 设置，不改全局 config；已经推送的历史不改写。
- 脱敏默认值、采集范围、CI / 发布 workflow、新依赖，以及上文「门禁与共享脚本」的敏感文件清单，都属于敏感改动，需安全审查。
