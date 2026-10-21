#!/usr/bin/env python3
# ============================================================================
#  gate-audit.py  门禁文件变更审计  版本 1.0.0
#  共享文件，禁止各仓单独修改（与 vuln-gate.py 同一套分发和哈希）。
#  只依赖 git 和 Python 标准库，参数全走命令行，以后可原样搬进
#  mugsun/.github 的 reusable workflow（inputs.base -> --base）。
# ============================================================================
"""对比 base..head，发现门禁被改动就判失败（清单 3.15、安全官 S2 / F1）。

用法: gate-audit.py --base <sha> [--head HEAD] [--repo .]
  push：base = github.event.before；pull_request：base = pull_request.base.sha。

判失败（每条都提示「提交说明写清理由，并交安全官复核」）：
  1. 改动（含新增、删除、改名）了受保护文件：.gitleaksignore、.gitleaks.toml、
     osv-scanner.toml（新增或修改忽略条目都要复核）、
     scripts/vuln-gate.py、scripts/vuln-gate.sha256、scripts/test_vuln_gate.py、
     scripts/gate-audit.py、scripts/test_gate_audit.py、scripts/mutate_vuln_gate.py。
  2. 新增行里出现 gitleaks 的行内放行注释（gitleaks 加 :allow）。
  3. .github/workflows/ 下：uses: 引用（含 @SHA）有增删改；*_SHA256 钉值有变化；
     校验或门禁调用（sha256sum -c、vuln-gate.py、gate-audit.py）的次数变少。
  4. head 里的共享脚本和 base 上 scripts/vuln-gate.sha256 记录的哈希不一致。
  5. base 为空、全 0 或在仓库里找不到（无法比较也按失败处理）。
"""
import argparse
import hashlib
import pathlib
import re
import subprocess
import sys

__version__ = "1.0.0"

PROTECTED = (
    ".gitleaksignore", ".gitleaks.toml", "osv-scanner.toml",
    "scripts/vuln-gate.py", "scripts/vuln-gate.sha256", "scripts/test_vuln_gate.py",
    "scripts/gate-audit.py", "scripts/test_gate_audit.py", "scripts/mutate_vuln_gate.py",
)
HASH_FILE = "scripts/vuln-gate.sha256"
WORKFLOWS = ".github/workflows/"
ALLOW_MARK = "gitleaks" + ":allow"   # 拆开写，免得本文件自己命中
GUARDS = ("sha256sum -c", "scripts/vuln-gate.py", "scripts/gate-audit.py")
HINT = "提交说明写清理由，并交安全官复核"


def git(repo, *args, check=True):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 失败：{r.stderr.strip()}")
    return r


def show(repo, rev, path):
    r = git(repo, "show", f"{rev}:{path}", check=False)
    return r.stdout if r.returncode == 0 else None


def workflow_facts(text):
    uses, pins, guards = set(), set(), {g: 0 for g in GUARDS}
    for line in (text or "").splitlines():
        s = line.split(" #", 1)[0].strip()
        m = re.match(r"^-?\s*uses:\s*(\S+)", s)
        if m:
            uses.add(m.group(1).strip("'\""))
        m = re.match(r"^([A-Z0-9_]*_SHA256)\s*:\s*(\S+)", s)
        if m:
            pins.add((m.group(1), m.group(2).strip("'\"")))
        for g in GUARDS:
            guards[g] += s.count(g)
    return uses, pins, guards


def audit(repo, base, head="HEAD"):
    errs = []
    if not base or set(base) == {"0"}:
        return [f"没有比较基准（base 为空或全 0），无法审计门禁改动；{HINT}"]
    if git(repo, "cat-file", "-e", f"{base}^{{commit}}", check=False).returncode != 0:
        return [f"base {base} 在仓库里找不到（checkout 需 fetch-depth: 0）；{HINT}"]
    names = git(repo, "diff", "--no-renames", "--name-only", base, head).stdout.split()
    for f in sorted(set(names) & set(PROTECTED)):
        errs.append(f"改动了受保护的门禁文件 {f}；{HINT}")
    diff = git(repo, "diff", "--no-renames", "-U0", base, head).stdout
    cur = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            cur = line[6:] if line.startswith("+++ b/") else None
        elif line.startswith("+") and ALLOW_MARK in line and cur:
            errs.append(f"{cur} 新增了 gitleaks 行内放行注释；{HINT}")
    wf = sorted({n for n in names if n.startswith(WORKFLOWS)})
    for f in wf:
        u0, p0, g0 = workflow_facts(show(repo, base, f))
        u1, p1, g1 = workflow_facts(show(repo, head, f))
        if u0 != u1:
            ch = sorted(u0 ^ u1)
            errs.append(f"{f} 的 uses: 引用有变化（{', '.join(ch)}）；{HINT}")
        if p0 != p1:
            errs.append(f"{f} 的工具 SHA256 钉值有变化；{HINT}")
        for g in GUARDS:
            if g1[g] < g0[g]:
                errs.append(f"{f} 删了校验或门禁步骤（{g} 由 {g0[g]} 处减为 {g1[g]} 处）；{HINT}")
    expected = show(repo, base, HASH_FILE)
    if expected is not None:
        for line in expected.splitlines():
            parts = line.split()
            if len(parts) != 2:
                continue
            want, path = parts
            r = subprocess.run(["git", "-C", repo, "show", f"{head}:{path}"],
                               capture_output=True)  # 按字节算哈希
            got = hashlib.sha256(r.stdout).hexdigest() if r.returncode == 0 else None
            if got != want:
                errs.append(f"{path} 与 base 上 {HASH_FILE} 记录的哈希不一致；{HINT}")
    return errs


def main(argv=None):
    ap = argparse.ArgumentParser(description=f"门禁文件变更审计 {__version__}")
    ap.add_argument("--version", action="version", version=__version__)
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--repo", default=".")
    a = ap.parse_args(argv)
    try:
        errs = audit(a.repo, a.base.strip(), a.head)
    except RuntimeError as e:
        errs = [f"{e}；{HINT}"]
    for e in errs:
        print(f"::error::{e}")
    print(f"gate-audit {__version__}: {len(errs)} error（base {a.base[:12]}）")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
