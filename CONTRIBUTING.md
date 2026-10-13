# 贡献指南

本仓库的贡献流程以账号默认指南为准（中文）：

**[贡献指南](https://github.com/mugsun/.github/blob/main/CONTRIBUTING.md)** · [English](https://github.com/mugsun/.github/blob/main/CONTRIBUTING_EN.md)

安全漏洞请按 [SECURITY.md](https://github.com/mugsun/.github/blob/main/SECURITY.md) 私密报告，不要公开开 Issue。

## 本仓要点

- 默认分支：`main`
- 提交信息：Conventional Commits，主题中文；详见 [`.github/COMMIT_CONVENTION.md`](./.github/COMMIT_CONVENTION.md)（若存在）
- 变更记录：见 [CHANGELOG.md](./CHANGELOG.md)
- 文档：[docs.mugsun.com](https://docs.mugsun.com/)
- 埋点 SDK / 看板相关；npm 包 `@mugsun/track-web` 当前版本 `0.2.0`（已发布）
- 提交规范见 `.github/COMMIT_CONVENTION.md`

## 发版流程

发布由 [`.github/workflows/release.yml`](./.github/workflows/release.yml) 通过 npm Trusted Publishing（OIDC，`--provenance`）自动完成，**不需要也不要在本地 `npm publish` 或配置 npm token**。

1. 在 PR 中修改 `package.json` 的 `version`，同步 `src/version.ts` 的 `SDK_VERSION`；在 `CHANGELOG.md` 新增对应版本条目（行为变更须写迁移说明）。
2. CI 通过、评审后合入 `main`。
3. `main` 上 `package.json` 变化（或手动 `workflow_dispatch`）触发 release：若 `name@version` 已在 npm 上则跳过；否则执行 `pnpm install --frozen-lockfile`、`pnpm typecheck && pnpm test && pnpm build`，再 `npm publish --provenance --access public`。
4. 发布后可用 `npm view @mugsun/track-web version` 确认；文档站（mugsun-docs）安装版本与更新日志需另开 PR 对齐。

## Release process (English)

Releases are published automatically by [`.github/workflows/release.yml`](./.github/workflows/release.yml) via npm Trusted Publishing (OIDC, `--provenance`). **Do not run `npm publish` locally; no npm token is needed.**

1. In a PR, bump `version` in `package.json`, keep `SDK_VERSION` in `src/version.ts` in sync, and add a `CHANGELOG.md` entry (behavior changes need migration notes).
2. Merge into `main` after CI passes and review.
3. A `package.json` change on `main` (or a manual `workflow_dispatch`) triggers the release: if `name@version` is already on npm it is skipped; otherwise it runs `pnpm install --frozen-lockfile`, `pnpm typecheck && pnpm test && pnpm build`, then `npm publish --provenance --access public`.
4. Verify with `npm view @mugsun/track-web version`, then open a mugsun-docs PR to update install versions and the changelog.
