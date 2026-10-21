#!/usr/bin/env python3
"""校验 .github/workflows 下所有 workflow（清单 3.2、3.8）。

规则：
1. 顶层必须有 permissions，且只有 contents: read。
2. 不许用 pull_request_target 触发。
3. id-token 权限只能写在 job 级，且该 job 必须挂 environment（发布 job）。
   顶层或其他 job 出现 id-token、write-all 即失败。
4. uses: 必须钉 40 位 commit SHA，后面注释版本（# vX）；本地 ./ 和
   docker://...@sha256: 除外。
5. 有 push 触发的 workflow 必须有顶层 concurrency（清单 3.16：分支推送多，旧运行要取消）。
6. 有 issues: write 的 job，if 里必须带 github.ref == 'refs/heads/main'
   （只在 main 上开 issue，功能分支失败不开）。认单行、>- / | 多行写法，以及等号两边
   反过来写、单双引号、${{ }} 包裹的形式。
7. 有 push 触发、cancel-in-progress 不是字面 false 的 workflow，concurrency group 必须在
   main 上按 SHA 分组：含 github.ref == 'refs/heads/main' && format('-{0}', github.sha)，
   否则 main 上排队中的运行会被后来的推送顶掉（代码质量官 B1）。

不依赖 PyYAML：按缩进解析，只认本仓 workflow 用到的写法。
用法：check-workflows.py [workflow 目录]，默认 .github/workflows。
"""
import pathlib
import re
import sys

SHA_RE = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")
USES_RE = re.compile(r"^\s*(?:-\s+)?uses:\s*([^\s#]+)\s*(#.*)?$")
_MAIN = r"['\"]refs/heads/main['\"]"
MAIN_REF = re.compile(rf"github\.ref\s*==\s*{_MAIN}|{_MAIN}\s*==\s*github\.ref")
MAIN_SHA_GROUP = re.compile(r"github\.ref\s*==\s*'refs/heads/main'\s*&&\s*"
                            r"format\(\s*'-\{0\}'\s*,\s*github\.sha\s*\)")


def indent(line):
    return len(line) - len(line.lstrip(" "))


def strip_comment(line):
    # 本仓 workflow 里 # 只出现在注释中；引号里的 # 不处理
    return re.sub(r"\s+#.*$", "", line) if not line.lstrip().startswith("#") else ""


def block(lines, start, base):
    """返回 start 之后缩进大于 base 的连续行（跳过空行和注释）。"""
    out = []
    for i in range(start + 1, len(lines)):
        raw = lines[i]
        s = strip_comment(raw)
        if not s.strip():
            continue
        if indent(s) <= base:
            break
        out.append((i, s))
    return out


def if_text(lines, i, base):
    """job 级 if: 的完整内容：单行，或 >- / | 等块标量的后续缩进行。"""
    head = strip_comment(lines[i]).split(":", 1)[1].strip()
    if head and head[0] not in ">|":
        return head
    return " ".join(s.strip() for _, s in block(lines, i, base))


def perm_map(lines, i, base):
    """解析 permissions: 的值（映射或标量），返回 dict 或字符串。"""
    head = strip_comment(lines[i]).split(":", 1)[1].strip()
    if head:
        return head  # read-all / write-all / {}
    return {s.strip().split(":", 1)[0].strip(): s.split(":", 1)[1].strip()
            for _, s in block(lines, i, base)}


def check(path):
    errs = []
    lines = path.read_text(encoding="utf-8").splitlines()
    rel = path.as_posix()

    def err(ln, msg):
        errs.append(f"{rel}:{ln + 1}: {msg}")

    top_perm = None
    jobs_line = None
    on_line = None
    has_concurrency = False
    conc_line = None
    for i, raw in enumerate(lines):
        s = strip_comment(raw)
        if not s.strip():
            continue
        if indent(s) == 0:
            key = s.split(":", 1)[0].strip()
            if key == "permissions":
                top_perm = (i, perm_map(lines, i, 0))
            elif key == "jobs":
                jobs_line = i
            elif key in ("on", '"on"', "'on'"):
                on_line = i
            elif key == "concurrency":
                has_concurrency = True
                conc_line = i
        if re.search(r"\bpull_request_target\b", s):
            err(i, "禁止 pull_request_target 触发")
        m = USES_RE.match(s if "#" not in raw else raw)
        if m:
            ref, comment = m.group(1), m.group(2)
            if ref.startswith("./"):
                pass
            elif ref.startswith("docker://"):
                if "@sha256:" not in ref:
                    err(i, f"docker 镜像未钉 digest：{ref}")
            elif not SHA_RE.match(ref):
                err(i, f"uses 未钉 40 位 commit SHA：{ref}")
            elif not comment or not re.search(r"v\d", comment):
                err(i, f"钉 SHA 的 uses 后面要注释版本（# vX）：{ref}")
        if re.search(r"\bwrite-all\b", s):
            err(i, "禁止 write-all")

    if top_perm is None:
        err(0, "缺少顶层 permissions（应为 contents: read）")
    elif top_perm[1] != {"contents": "read"}:
        err(top_perm[0], f"顶层 permissions 只能是 contents: read，现在是 {top_perm[1]}")

    if on_line is not None:
        events = {s.strip().split(":", 1)[0] for _, s in block(lines, on_line, 0)
                  if indent(s) == 2}
        head = strip_comment(lines[on_line]).split(":", 1)[1]
        has_push = "push" in events or bool(re.search(r"\bpush\b", head))
        if has_push and not has_concurrency:
            err(on_line, "有 push 触发但缺少顶层 concurrency")
        if has_push and conc_line is not None:
            conc = {s.strip().split(":", 1)[0]: s.split(":", 1)[1].strip()
                    for _, s in block(lines, conc_line, 0) if ":" in s}
            if conc.get("cancel-in-progress", "") != "false" and not MAIN_SHA_GROUP.search(
                    conc.get("group", "")):
                err(conc_line, "concurrency group 必须在 main 上按 SHA 分组（加 ${{ github.ref == "
                               "'refs/heads/main' && format('-{0}', github.sha) || '' }}）")

    if jobs_line is not None:
        job_rows = [(i, s) for i, s in block(lines, jobs_line, 0)]
        job_indent = min((indent(s) for _, s in job_rows), default=2)
        starts = [(i, s.strip().rstrip(":")) for i, s in job_rows
                  if indent(s) == job_indent]
        for i, name in starts:
            body = block(lines, i, job_indent)
            keys = {s.strip().split(":", 1)[0]: j for j, s in body
                    if indent(s) == job_indent + 2}
            if "permissions" in keys:
                p = perm_map(lines, keys["permissions"], job_indent + 2)
                if isinstance(p, dict) and "id-token" in p and "environment" not in keys:
                    err(keys["permissions"],
                        f"job {name} 有 id-token 权限但没挂 environment（只有发布 job 可以）")
                if isinstance(p, dict) and p.get("issues") == "write":
                    cond = if_text(lines, keys["if"], job_indent + 2) if "if" in keys else ""
                    if not MAIN_REF.search(cond):
                        err(keys["permissions"],
                            f"job {name} 有 issues: write，if 里必须限定 github.ref == 'refs/heads/main'")
    return errs


def main():
    d = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".github/workflows")
    files = sorted([*d.glob("*.yml"), *d.glob("*.yaml")])
    if not files:
        print(f"{d} 下没有 workflow")
        return 1
    errs = [e for f in files for e in check(f)]
    for e in errs:
        print(f"::error::{e}")
    print(f"checked {len(files)} workflow(s), {len(errs)} problem(s)")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
