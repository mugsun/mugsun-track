#!/usr/bin/env python3
# CHANGELOG 新增行检查（清单 3.3）。只查本次 diff 新增的行，历史条目不管。
# 规则：每行 python len <= 80；子项缩进两格。
# 用法: check-changelog.py <base_sha> [file]
#   CI：push 用 github.event.before，PR 用 base sha；本地 pre-commit 用 HEAD。
import subprocess, sys
base = sys.argv[1]
f = sys.argv[2] if len(sys.argv) > 2 else "CHANGELOG.md"
if set(base) == {"0"}:  # 新分支首推
    base = "HEAD~1"
diff = subprocess.run(
    ["git", "diff", "-U0", base, "HEAD", "--", f],
    capture_output=True, text=True, check=True).stdout
bad, ln = [], 0
for line in diff.splitlines():
    if line.startswith("@@"):
        ln = int(line.split("+")[1].split(",")[0].split(" ")[0])
        continue
    if line.startswith("+") and not line.startswith("+++"):
        text = line[1:]
        s = text.lstrip()
        if len(text) > 80:
            bad.append(f"{f}:{ln} 超 80 字({len(text)})")
        # 条目体：顶层 "- " 是说明句，子项须缩进
        if s.startswith("- ") and text != s and not text.startswith("  "):
            bad.append(f"{f}:{ln} 子项缩进应为两格")
        ln += 1
if bad:
    print("\n".join(bad)); sys.exit(1)
print(f"{f}: 新增行检查通过")
