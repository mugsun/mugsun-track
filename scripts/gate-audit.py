#!/usr/bin/env python3
# ============================================================================
#  gate-audit.py  门禁文件变更审计  版本 1.1.2
#  共享文件，禁止各仓单独修改（与 vuln-gate.py 同一套分发和哈希）。
#  只依赖 git 和 Python 标准库，参数全走命令行，以后可原样搬进
#  mugsun/.github 的 reusable workflow（inputs.base -> --base）。
# ============================================================================
"""对比 base..head，发现门禁被改动就判失败（清单 3.15、安全官 S2 / F1）。

用法: gate-audit.py --base <sha> [--head HEAD] [--repo .]
  push：base = github.event.before；pull_request：base = merge-base(pull_request.base.sha, HEAD)
  （merge-base 由 workflow 的 shell 算好再传入，脚本接口保持不变）。

判失败（每条都提示「提交说明写清理由，并交安全官复核」）：
  1. 改动（含新增、删除、改名）了受保护文件：
     - 整个 .github/workflows/ 和 .github/actions/ 目录（安全官 G1、代码质量官 A1：
       if: false、|| true、continue-on-error、改 BASE_SHA 等改法逐行比较拦不全，
       所以任何改动都判红，交安全官复核）；.github/CODEOWNERS；
     - 任意目录下的 osv-scanner.toml、.gitleaks.toml、.gitleaksignore；
     - scripts/ 下的共享门禁脚本、哈希表，以及 check-workflows.py、test_security_workflow.py。
  2. 新增行里出现 gitleaks 的行内放行注释（gitleaks 加 :allow，不区分大小写）。
  3. workflow 的细粒度提示（只用来说明改了什么，判红已由第 1 条保证）：uses: 引用
     （含 @SHA）有增删改；*_SHA256 钉值有变化；sha256sum -c、vuln-gate.py、gate-audit.py
     的出现次数变少。这几条不作为判红依据，删掉第 1 条就没有兜底。
  4. head 里的共享脚本和 base 上 scripts/vuln-gate.sha256 记录的哈希不一致；
     base 上已有 gate-audit.py 却没有哈希表；哈希表里有格式不对的行（不是「64 位小写
     十六进制 + 两个空格或空格加 * + 路径」，空行除外）。
文件名一律用 core.quotepath=off 和 -z 读取（代码质量官 B1）：git 默认把非 ASCII
文件名转义成带引号的八进制形式，会让受保护路径的判断失效。
受保护路径的匹配两边都先做 NFC 规范化再 casefold（安全官补充 1），大小写变体和 NFD
形式的路径照样命中。解析出的文件名仍以引号开头或含反斜杠（说明转义没去掉），直接判失败
（安全官补充 2）。改名用 --no-renames 拆成删除旧路径 + 新增新路径，两个路径都会检查。
  5. base 为空、全 0 或在仓库里找不到（无法比较也按失败处理）。
"""
import argparse
import hashlib
import pathlib
import re
import subprocess
import sys
import unicodedata

__version__ = "1.1.2"

PROTECTED = (
    ".github/CODEOWNERS",
    "scripts/vuln-gate.py", "scripts/vuln-gate.sha256", "scripts/test_vuln_gate.py",
    "scripts/gate-audit.py", "scripts/test_gate_audit.py", "scripts/mutate_vuln_gate.py",
    "scripts/check-workflows.py", "scripts/test_security_workflow.py",
)
PROTECTED_DIRS = (".github/workflows/", ".github/actions/")
PROTECTED_NAMES = ("osv-scanner.toml", ".gitleaks.toml", ".gitleaksignore")  # 任意目录
HASH_FILE = "scripts/vuln-gate.sha256"
WORKFLOWS = ".github/workflows/"
ALLOW_MARK = "gitleaks" + ":allow"   # 拆开写，免得本文件自己命中；比较时不区分大小写
GUARDS = ("sha256sum -c", "scripts/vuln-gate.py", "scripts/gate-audit.py")
HINT = "提交说明写清理由，并交安全官复核"
HASH_LINE = re.compile(r"^([0-9a-f]{64}) [ *](\S.*)$")
BAD_NAME = re.compile(r'^"|\\')   # 引号开头或含反斜杠：转义没去掉


def git(repo, *args, check=True):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 失败：{r.stderr.strip()}")
    return r


def show(repo, rev, path):
    r = git(repo, "show", f"{rev}:{path}", check=False)
    return r.stdout if r.returncode == 0 else None


def norm(path):
    """NFC 规范化后再 casefold；路径和匹配规则都过这一道。"""
    return unicodedata.normalize("NFC", path).casefold()


def is_protected(path, protected=PROTECTED, dirs=PROTECTED_DIRS, names=PROTECTED_NAMES):
    p = norm(path)
    return (p in {norm(x) for x in protected} or p.startswith(tuple(norm(d) for d in dirs))
            or p.rsplit("/", 1)[-1] in {norm(n) for n in names})


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
    raw = git(repo, "-c", "core.quotepath=off", "diff", "--no-renames", "--name-only", "-z",
              base, head).stdout
    names = [n for n in raw.split("\0") if n]
    bad = sorted({n for n in names if BAD_NAME.search(n)})
    if bad:
        return [f"文件名 {n!r} 仍带引号或反斜杠转义，无法可靠判断是否受保护；{HINT}" for n in bad]
    for f in sorted({n for n in names if is_protected(n)}):
        errs.append(f"改动了受保护的门禁文件 {f}；{HINT}")
    diff = git(repo, "-c", "core.quotepath=off", "diff", "--no-renames", "-U0",
               base, head).stdout
    cur = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            # 文件名含空格时 git 会在 +++ 行末尾加一个 TAB
            cur = line[6:].rstrip("\t") if line.startswith("+++ b/") else None
        elif line.startswith("+") and ALLOW_MARK in line.lower() and cur:
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
    if expected is None and show(repo, base, "scripts/gate-audit.py") is not None:
        errs.append(f"base 上有 scripts/gate-audit.py 却没有 {HASH_FILE}，无法核对共享脚本；{HINT}")
    if expected is not None:
        for n, line in enumerate(expected.splitlines(), 1):
            if not line.strip():
                continue
            m = HASH_LINE.match(line)
            if not m:
                errs.append(f"base 上 {HASH_FILE} 第 {n} 行格式不对（{line[:80]!r}），"
                            f"不能跳过校验；{HINT}")
                continue
            want, path = m.groups()
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
