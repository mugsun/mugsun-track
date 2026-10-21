#!/usr/bin/env python3
# 共享文件，禁止各仓单独修改。随 vuln-gate.py 1.1.0 / gate-audit.py 1.1.2 分发、一起校验哈希。
"""变异检查（安全官 S5）：逐个把关键规则改坏，确认测试集能发现。

用法：python3 scripts/mutate_vuln_gate.py
  先跑一遍未改动的测试（必须全过），再对每个变异体在临时目录里重跑对应测试。
  每个变异的原文必须在源文件里恰好出现一次，否则视为本脚本过期，直接失败。
  任何一个变异体「测试仍全过」（存活）都返回 1。不改动仓里的任何文件。
"""
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
GATE, AUDIT = "vuln-gate.py", "gate-audit.py"
TESTS = {GATE: "test_vuln_gate.py", AUDIT: "test_gate_audit.py"}

# (名称, 文件, 原文, 改成)
MUTANTS = [
    ("High 阈值放宽到 9.0", GATE, "HIGH = 7.0", "HIGH = 9.0"),
    ("无法判定严重度时放行", GATE, "if score is None or score >= HIGH:",
     "if score is not None and score >= HIGH:"),
    ("prod 上限放宽到 90 天（安全官 S1）", GATE, '{"prod": 30, "dev": 90}', '{"prod": 90, "dev": 90}'),
    ("dev 上限放宽到 91 天", GATE, '{"prod": 30, "dev": 90}', '{"prod": 30, "dev": 91}'),
    ("scope 改回选填（阻塞 2）", GATE, 'REQUIRED = ("id", "scope", "reason", "added", "ignoreUntil")',
     'REQUIRED = ("id", "reason", "added", "ignoreUntil")'),
    ("scope 不校验取值", GATE, "if not isinstance(scope, str) or scope not in MAX_IGNORE_DAYS:",
     "if False:"),
    ("未归组漏洞被跳过（阻塞 1）", GATE, "                if n in used:\n                    continue",
     "                continue"),
    ("groups / vulnerabilities 只出现一个也放过", GATE, "            if has_g != has_v:",
     "            if False:"),
    ("-0.0 当 0 分（安全官 S3）", GATE, " or math.copysign(1.0, val) < 0:", ":"),
    ("NaN / 超范围丢弃而不是按 10.0（安全官 S4）", GATE,
     "    if not math.isfinite(val) or not 0.0 <= val <= 10.0",
     "    if not math.isfinite(val) or not 0.0 <= val <= 10.0:\n        return None\n    if False"),
    ("解析不了的向量 / v4 丢弃（安全官 S4）", GATE, "    return INVALID if s is None else s", "    return s"),
    ("认不出的等级丢弃（安全官 S4）", GATE, "LABELS.get(label.strip().lower(), INVALID)",
     "LABELS.get(label.strip().lower())"),
    ("npm cvss.score 0 不计", GATE, '("cvss.score", finite(cv.get("score"))),\n                       ("cvss.vectorString"',
     '("cvss.score", finite(cv.get("score")) if cv.get("score") else None),\n                       ("cvss.vectorString"'),
    ("忽略列表过期判断失效", GATE, "if until < today:", "if until < today - dt.timedelta(days=1):"),
    ("v3.0 向上取整写错", GATE, "    return -(-i // 10000) / 10.0", "    return (i // 10000) / 10.0"),
    ("审计不查受保护文件", AUDIT, "    for f in sorted({n for n in names if is_protected(n)}):",
     "    for f in []:"),
    ("审计不保护 osv-scanner.toml", AUDIT, 'PROTECTED_NAMES = ("osv-scanner.toml", ', 'PROTECTED_NAMES = ('),
    ("审计不保护 workflows 目录（G1 / A1）", AUDIT, 'PROTECTED_DIRS = (".github/workflows/", ".github/actions/")',
     'PROTECTED_DIRS = (".github/actions/",)'),
    ("审计不保护本地 action", AUDIT, 'PROTECTED_DIRS = (".github/workflows/", ".github/actions/")',
     'PROTECTED_DIRS = (".github/workflows/",)'),
    ("审计只匹配根目录配置", AUDIT, 'or p.rsplit("/", 1)[-1] in {norm(n) for n in names})',
     "or p in {norm(n) for n in names})"),
    ("审计不保护 CODEOWNERS", AUDIT, '    ".github/CODEOWNERS",\n', ""),
    ("base 有脚本缺哈希表放行", AUDIT, 'if expected is None and show(repo, base, "scripts/gate-audit.py") is not None:',
     "if False:"),
    ("文件名不加 -z、按空白切分（B1）", AUDIT,
     '    names = [n for n in raw.split("\\0") if n]', '    names = raw.split()'),
    # -z 时 git 本来就不转义文件名，所以转义开关只在 -U0 那处 diff 上有意义
    ("diff 里的文件名按 git 默认转义（B1）", AUDIT, 'diff = git(repo, "-c", "core.quotepath=off", "diff"',
     'diff = git(repo, "-c", "core.quotepath=on", "diff"'),
    ("受保护路径不做 NFC 规范化（安全官补充 1）", AUDIT,
     '    return unicodedata.normalize("NFC", path).casefold()', '    return path.casefold()'),
    ("受保护路径区分大小写（安全官补充 1）", AUDIT,
     '    return unicodedata.normalize("NFC", path).casefold()', '    return unicodedata.normalize("NFC", path)'),
    ("带引号或反斜杠的文件名放行（安全官补充 2）", AUDIT, "    if bad:\n        return [", "    if False:\n        return ["),
    ("文件名清单按改名合并，旧路径漏查", AUDIT,
     'raw = git(repo, "-c", "core.quotepath=off", "diff", "--no-renames", "--name-only"',
     'raw = git(repo, "-c", "core.quotepath=off", "diff", "-M", "--name-only"'),
    ("哈希表格式不对的行静默跳过（S2）", AUDIT,
     '                errs.append(f"base 上 {HASH_FILE} 第 {n} 行格式不对',
     '                if False: errs.append(f"base 上 {HASH_FILE} 第 {n} 行格式不对'),
    ("放行注释区分大小写", AUDIT, "ALLOW_MARK in line.lower() and cur:", "ALLOW_MARK in line and cur:"),
    ("审计不查行内放行注释", AUDIT, "elif line.startswith(\"+\") and ALLOW_MARK in line.lower() and cur:",
     "elif False:"),
    ("审计不查 uses: 引用", AUDIT, "        if u0 != u1:", "        if False:"),
    ("审计不查工具钉值", AUDIT, "        if p0 != p1:", "        if False:"),
    ("审计不查删除校验步骤", AUDIT, "            if g1[g] < g0[g]:", "            if False:"),
    ("审计不对比 base 哈希", AUDIT, "            if got != want:", "            if False:"),
    ("审计在 base 全 0 时放行", AUDIT, 'if not base or set(base) == {"0"}:\n        return [',
     'if not base or set(base) == {"0"}:\n        return []\n        return ['),
]


def run_tests(d, test):
    r = subprocess.run([sys.executable, str(d / test)], capture_output=True, text=True,
                       cwd=d, timeout=300)
    return r.returncode == 0


def main():
    with tempfile.TemporaryDirectory() as t:
        d = pathlib.Path(t)
        for name in (GATE, AUDIT, *TESTS.values()):
            shutil.copy2(HERE / name, d / name)
        for test in TESTS.values():
            if not run_tests(d, test):
                print(f"::error::未改动的源码 {test} 就没过，先修测试")
                return 1
        survived, stale = [], []
        for name, f, old, new in MUTANTS:
            src = (HERE / f).read_text(encoding="utf-8")
            if src.count(old) != 1:
                stale.append(name)
                print(f"::error::变异「{name}」的原文在 {f} 里出现 {src.count(old)} 次，本脚本需更新")
                continue
            (d / f).write_text(src.replace(old, new), encoding="utf-8")
            killed = not run_tests(d, TESTS[f])
            (d / f).write_text(src, encoding="utf-8")
            print(f"{'killed  ' if killed else 'SURVIVED'} {name}")
            if not killed:
                survived.append(name)
    print(f"mutants: {len(MUTANTS)}, killed: {len(MUTANTS) - len(survived) - len(stale)}, "
          f"survived: {len(survived)}, stale: {len(stale)}")
    return 1 if survived or stale else 0


if __name__ == "__main__":
    sys.exit(main())
