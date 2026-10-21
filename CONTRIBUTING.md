# 贡献指南

本仓库的贡献流程以账号默认指南为准（中文）：

**[贡献指南](https://github.com/mugsun/.github/blob/main/CONTRIBUTING.md)** · [English](https://github.com/mugsun/.github/blob/main/CONTRIBUTING_EN.md)

安全漏洞请按 [SECURITY.md](https://github.com/mugsun/.github/blob/main/SECURITY.md) 私密报告，不要公开开 Issue。

## 本仓要点

- 默认分支：`main`；不开 PR，分支在本仓跑绿、审过后普通快进推入 `main`（规则详见 [AGENTS.md](./AGENTS.md)）
- 提交信息：Conventional Commits，主题中文；详见 [`.github/COMMIT_CONVENTION.md`](./.github/COMMIT_CONVENTION.md)
- 提交身份：作者和提交者一律用 `Mugsun <100790155+mugsun@users.noreply.github.com>`，用仓库级 config 设置
- 变更记录：见 [CHANGELOG.md](./CHANGELOG.md)
- 文档：[docs.mugsun.com](https://docs.mugsun.com/)
- npm 包 `@mugsun/track-web`，版本以根目录 `package.json` 为准，已发布版本用 `npm view @mugsun/track-web versions` 查

## 发版流程

发布由 [`.github/workflows/release.yml`](./.github/workflows/release.yml) 完成，用 npm Trusted Publishing（OIDC，`--provenance`）。**不要在本地 `npm publish`，也不要配置 npm token。**

1. 在分支上修改 `package.json` 的 `version`，手工同步 `src/version.ts` 的 `SDK_VERSION`（CI 不校验两者一致），在 `CHANGELOG.md` 写好对应版本条目（行为变更须写迁移说明）。
2. 分支上 CI 和 Security scan 全绿、审过后，普通快进推入 `main`。`main` 上 `package.json` 有改动（或手动 `workflow_dispatch`）会触发 Release workflow，共三个 job：
   - `check`：只读，不需审批，跑 `scripts/release-check.sh`。版本已在 npm 上就整个 run 绿色跳过；只有 E404 算未发布，其他错误直接失败；版本须是规范 semver 且严格大于 npm latest；带 `-` 的预发布版本用 `next` 标签，否则 `latest`。
   - `publish`：只在 `main` 上、版本未发布时跑，挂 `npm-release` 环境，**需 mugsun 审批后才执行**。依次 typecheck、test、build，生成 CycloneDX SBOM 并上传，再 `npm publish --provenance --access public --tag <标签>`。
   - `github-release`：发布成功后建 `v<版本>` 的 GitHub Release，附上 SBOM。
3. 发布后用 `npm view @mugsun/track-web version` 确认；文档站（mugsun-docs）的安装版本和更新日志另行对齐。

## Release process (English)

Releases are published by [`.github/workflows/release.yml`](./.github/workflows/release.yml) via npm Trusted Publishing (OIDC, `--provenance`). **Never run `npm publish` locally and do not configure an npm token.**

1. On a branch, bump `version` in `package.json`, keep `SDK_VERSION` in `src/version.ts` in sync by hand (CI does not check this), and add a `CHANGELOG.md` entry (behavior changes need migration notes).
2. Once CI and Security scan are green on the branch and the change is reviewed, fast-forward `main` (no PRs). A `package.json` change on `main` (or a manual `workflow_dispatch`) triggers the Release workflow with three jobs:
   - `check`: read-only, no approval, runs `scripts/release-check.sh`. If the version is already on npm the whole run is skipped (green); only E404 counts as unpublished, any other error fails; the version must be canonical semver and strictly greater than npm `latest`; versions containing `-` are tagged `next`, otherwise `latest`.
   - `publish`: runs only on `main` for an unpublished version, in the `npm-release` environment, **after approval by mugsun**. It runs typecheck, test and build, generates and uploads a CycloneDX SBOM, then `npm publish --provenance --access public --tag <tag>`.
   - `github-release`: after a successful publish, creates the `v<version>` GitHub Release with the SBOM attached.
3. Verify with `npm view @mugsun/track-web version`, then update install versions and the changelog in mugsun-docs.

Commits must be authored and committed as `Mugsun <100790155+mugsun@users.noreply.github.com>` (set via repository-level git config).
