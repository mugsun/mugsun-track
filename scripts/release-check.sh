#!/usr/bin/env bash
# 发版前检查（release.yml 的 check job 调用）。向 $GITHUB_OUTPUT 写 skip=true|false 和 tag=latest|next（未设置时打印）。
# - npm view <pkg>@<ver> 成功且返回该版本 → 已发布，skip=true
# - 只有 `npm error code E404`（或 --json 的 "code": "E404"）算「未发布」；网络、鉴权、5xx 等其他错误一律失败
# - 版本号先用 semver 校验格式（包从未发布过也校验）
# - 未发布时要求 package.json 版本严格大于 npm latest（semver@7.6.3，含预发布版本），否则失败
# - 版本含 `-`（预发布）→ tag=next，否则 tag=latest
# NPM 环境变量可替换 npm 命令（本地用 mock 测试）；SEMVER 可替换 semver 命令
set -euo pipefail

NPM_BIN="${NPM:-npm}"
OUT="${GITHUB_OUTPUT:-/dev/stdout}"
if [ -n "${SEMVER:-}" ]; then read -r -a SEMVER_CMD <<<"$SEMVER"; else SEMVER_CMD=(npx --yes semver@7.6.3); fi
NAME=$(node -p "require('./package.json').name")
VER=$(node -p "require('./package.json').version")

fail() { echo "::error::$1"; exit 1; }
is_404() { grep -Eq '^npm (error|ERR!) code E404$|"code": *"E404"' <<<"$1"; }
# semver 命令：满足返回 0 并打印版本；不满足返回 1；其他退出码说明工具本身出错（npx 下载失败、命令不存在等）
semver_run() {
  local rc=0 out
  out=$("${SEMVER_CMD[@]}" "$@" 2>&1) || rc=$?
  if [ "$rc" -gt 1 ]; then echo "semver tool failed (rc=$rc): $out" >&2; return 2; fi
  printf '%s' "$out"
  return "$rc"
}
# 用法：semver_run ... || semver_fail $? "不满足时的错误信息"
semver_fail() { [ "$1" -eq 1 ] || fail "semver tool failed, see log above"; fail "$2"; }

# 1. 校验版本格式：必须是严格 semver，且规范化后与原文一致（拒绝 v 前缀、空格等）
NORM=$(semver_run "$VER") || semver_fail $? "package.json version '$VER' is not valid semver"
[ "$NORM" = "$VER" ] || fail "package.json version '$VER' is not canonical semver (normalizes to '$NORM')"

# 2. 该版本是否已发布
set +e
OUT_VER=$("$NPM_BIN" view "$NAME@$VER" version 2>&1)
RC=$?
set -e
if [ "$RC" -eq 0 ] && [ "$(printf '%s' "$OUT_VER" | tr -d '[:space:]')" = "$VER" ]; then
  { echo "skip=true"; echo "tag="; } >> "$OUT"
  echo "$NAME@$VER already on npm"
  exit 0
fi
if [ "$RC" -eq 0 ] || ! is_404 "$OUT_VER"; then
  printf '%s\n' "$OUT_VER" >&2
  fail "npm view $NAME@$VER failed or returned unexpected output (rc=$RC); not treating as unpublished"
fi

# 3. 未发布：和 latest 比较
set +e
LATEST=$("$NPM_BIN" view "$NAME" version 2>&1)
RC=$?
set -e
if [ "$RC" -ne 0 ]; then
  if is_404 "$LATEST"; then
    LATEST=""
    echo "$NAME has never been published"
  else
    printf '%s\n' "$LATEST" >&2
    fail "npm view $NAME version failed (rc=$RC)"
  fi
else
  LATEST=$(printf '%s' "$LATEST" | tr -d '[:space:]')
  [ -n "$LATEST" ] || fail "npm view $NAME version returned rc=0 with empty output"
  semver_run "$LATEST" >/dev/null || semver_fail $? "npm latest '$LATEST' is not valid semver"
  semver_run -p -r ">$LATEST" "$VER" >/dev/null \
    || semver_fail $? "package.json version $VER is not greater than npm latest $LATEST"
fi

case "$VER" in *-*) TAG=next ;; *) TAG=latest ;; esac
{ echo "skip=false"; echo "tag=$TAG"; } >> "$OUT"
echo "Will publish $NAME@$VER with --tag $TAG (npm latest: ${LATEST:-none})"
