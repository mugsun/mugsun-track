#!/usr/bin/env python3
# 共享文件，禁止各仓单独修改。随 gate-audit.py 1.1.1 一起分发、一起校验哈希。
"""gate-audit.py 反例集（清单 3.15、安全官 S2 / F1）。用法：python3 scripts/test_gate_audit.py"""
import contextlib
import hashlib
import importlib.util
import io
import pathlib
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    "gate_audit", pathlib.Path(__file__).with_name("gate-audit.py"))
ga = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ga)

ALLOW = "gitleaks" + ":allow"
WF = """name: s
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
env:
  OSV_SCANNER_SHA256: aaaa
jobs:
  osv:
    steps:
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4
      - name: Verify
        run: sha256sum -c scripts/vuln-gate.sha256
      - run: python3 scripts/vuln-gate.py results --exit-code "$OSV_RC" --require-packages x
  audit:
    if: github.event_name == 'push' || github.event_name == 'pull_request'
    steps:
      - name: Audit
        env:
          BASE_SHA: ${{ github.event.before }}
        run: python3 scripts/gate-audit.py --base "$BASE_SHA"
"""
WF_PATH = ".github/workflows/security.yml"


class Repo(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = d.name
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")
        self.git("config", "commit.gpgsign", "false")
        self.write("scripts/vuln-gate.py", "print(1)\n")
        self.write("scripts/test_vuln_gate.py", "print(2)\n")
        self.write(".github/workflows/security.yml", WF)
        self.write("src/a.ts", "export const a = 1\n")
        self.write("scripts/vuln-gate.sha256", self.sums())
        self.base = self.commit("base")

    def git(self, *a):
        return subprocess.run(["git", "-C", self.dir, *a], check=True,
                              capture_output=True, text=True).stdout.strip()

    def write(self, rel, text):
        p = pathlib.Path(self.dir) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def sums(self):
        out = []
        for rel in ("scripts/vuln-gate.py", "scripts/test_vuln_gate.py"):
            h = hashlib.sha256((pathlib.Path(self.dir) / rel).read_bytes()).hexdigest()
            out.append(f"{h}  {rel}")
        return "\n".join(out) + "\n"

    def commit(self, msg):
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", msg)
        return self.git("rev-parse", "HEAD")

    def errs(self, base=None):
        return ga.audit(self.dir, self.base if base is None else base)

    def assertFlag(self, needle):
        e = self.errs()
        self.assertTrue(any(needle in x for x in e), e)
        self.assertTrue(all(ga.HINT in x for x in e), e)

    def test_ordinary_change_passes(self):
        self.write("src/a.ts", "export const a = 2\n")
        self.commit("feat")
        self.assertEqual(self.errs(), [])

    def test_any_workflow_change_is_red(self):  # 安全官 G1、代码质量官 A1
        self.write(WF_PATH, WF.replace("name: s", "name: scan"))
        self.commit("rename")
        self.assertFlag(f"受保护的门禁文件 {WF_PATH}")

    def assertWorkflowRed(self, old, new, msg):
        self.assertEqual(WF.count(old), 1, old)
        self.write(WF_PATH, WF.replace(old, new))
        self.commit(msg)
        self.assertFlag(f"受保护的门禁文件 {WF_PATH}")

    def test_bypass_if_false(self):
        self.assertWorkflowRed("  audit:\n    if: github.event_name == 'push' || "
                               "github.event_name == 'pull_request'",
                               "  audit:\n    if: false", "if false")

    def test_bypass_drop_if(self):
        self.assertWorkflowRed("    if: github.event_name == 'push' || "
                               "github.event_name == 'pull_request'\n", "", "drop if")

    def test_bypass_drop_pull_request_trigger(self):
        self.assertWorkflowRed("  pull_request:\n    branches: [main]\n", "", "no pr")

    def test_bypass_continue_on_error(self):
        self.assertWorkflowRed("      - name: Audit\n",
                               "      - name: Audit\n        continue-on-error: true\n", "coe")

    def test_bypass_or_true_on_audit(self):
        self.assertWorkflowRed('--base "$BASE_SHA"', '--base "$BASE_SHA" || true', "or true")

    def test_bypass_base_sha_is_head(self):
        self.assertWorkflowRed("${{ github.event.before }}", "${{ github.sha }}", "base=head")

    def test_bypass_or_true_on_gate(self):
        self.assertWorkflowRed("--require-packages x", "--require-packages x || true", "gate")

    def test_bypass_drop_require_packages(self):
        self.assertWorkflowRed("--require-packages x", "x", "drop require")

    def test_bypass_exit_code_zero(self):
        self.assertWorkflowRed('--exit-code "$OSV_RC"', "--exit-code 0", "rc0")

    def test_bypass_echo_keeps_keywords(self):
        self.assertWorkflowRed('run: python3 scripts/gate-audit.py --base "$BASE_SHA"',
                               'run: echo "python3 scripts/gate-audit.py --base"', "echo")

    def test_protected_dirs_and_names(self):
        for rel in (".github/CODEOWNERS", ".github/actions/gate/action.yml",
                    ".github/workflows/new.yml", "web/osv-scanner.toml",
                    "server/.gitleaks.toml", "pkg/a/.gitleaksignore",
                    "scripts/check-workflows.py", "scripts/test_security_workflow.py"):
            with self.subTest(rel=rel):
                self.write(rel, "x\n")
                self.commit(rel)
                e = self.errs()
                self.assertTrue(any(f"受保护的门禁文件 {rel}" in x for x in e), e)

    def test_non_ascii_workflow_name(self):  # 代码质量官 B1
        rel = ".github/workflows/工作.yml"
        self.write(rel, "on: pull_request_target\n")
        self.commit("cn")
        self.assertFlag(f"受保护的门禁文件 {rel}")

    def test_osv_config_in_non_ascii_dir(self):  # B1
        rel = "中文/osv-scanner.toml"
        self.write(rel, "# x\n")
        self.commit("cn dir")
        self.assertFlag(f"受保护的门禁文件 {rel}")

    def test_workflow_name_with_space(self):  # B1
        rel = ".github/workflows/a b.yml"
        self.write(rel, "on: push\n")
        self.commit("space")
        self.assertFlag(f"受保护的门禁文件 {rel}")

    def test_inline_allow_in_non_ascii_path_with_space(self):
        self.write("源码/a b.ts", f"const k = 'x' // {ALLOW}\n")
        self.commit("allow")
        self.assertFlag("源码/a b.ts 新增了 gitleaks 行内放行注释")

    def test_malformed_hash_line_fails(self):  # 代码质量官 S2
        for i, bad in enumerate(("0" * 64 + "\tscripts/vuln-gate.py",
                                 "abc  scripts/vuln-gate.py", "0" * 64,
                                 "0" * 64 + "scripts/vuln-gate.py")):
            with self.subTest(bad=bad):
                self.write("scripts/vuln-gate.sha256", self.sums() + bad + "\n")
                self.base = self.commit(f"bad table {i}")
                self.write("src/a.ts", f"v{i}\n")
                self.commit(f"feat {i}")
                self.assertFlag("格式不对")

    def test_hash_table_blank_lines_and_star_ok(self):
        star = self.sums().replace("  scripts/", " *scripts/")
        self.write("scripts/vuln-gate.sha256", star + "\n")
        self.base = self.commit("star")
        self.write("src/a.ts", "z\n")
        self.commit("feat")
        self.assertEqual(self.errs(), [])

    def test_other_github_file_passes(self):
        self.write(".github/COMMIT_CONVENTION.md", "x\n")
        self.write("docs/osv-scanner.toml.md", "x\n")
        self.commit("docs")
        self.assertEqual(self.errs(), [])

    def test_base_has_audit_but_no_hash_table(self):
        self.write("scripts/gate-audit.py", "print(0)\n")
        self.git("rm", "-q", "scripts/vuln-gate.sha256")
        self.base = self.commit("no table")
        self.write("src/a.ts", "y\n")
        self.commit("feat")
        self.assertFlag("却没有 scripts/vuln-gate.sha256")

    def test_inline_allow_case_insensitive(self):
        self.write("src/a.ts", f"const k = 'x' // {ALLOW.upper()}\n")
        self.commit("allow")
        self.assertFlag("新增了 gitleaks 行内放行注释")

    def test_protected_files(self):
        for rel in ga.PROTECTED:
            with self.subTest(rel=rel):
                self.write(rel, "changed\n")
                self.commit(rel)
                e = self.errs()
                self.assertTrue(any(f"受保护的门禁文件 {rel}" in x for x in e), e)

    def test_osv_ignore_entry_added(self):
        self.write("osv-scanner.toml", "# only comments\n")
        self.base = self.commit("toml")
        self.write("osv-scanner.toml", '[[IgnoredVulns]]\nid = "GHSA-2v37-7h3g-55p8"\n'
                   'scope = "prod"\nadded = 2026-10-21\nignoreUntil = 2026-11-20\n'
                   'reason = "x"\n')
        self.commit("ignore")
        self.assertFlag("受保护的门禁文件 osv-scanner.toml")

    def test_osv_ignore_entry_modified(self):
        self.write("osv-scanner.toml", '[[IgnoredVulns]]\nid = "GHSA-2v37-7h3g-55p8"\n'
                   'reason = "x"\n')
        self.base = self.commit("toml")
        self.write("osv-scanner.toml", '[[IgnoredVulns]]\nid = "GHSA-2v37-7h3g-55p8"\n'
                   'reason = "延期"\n')
        self.commit("extend")
        self.assertFlag("受保护的门禁文件 osv-scanner.toml")

    def test_delete_protected_file(self):
        self.git("rm", "-q", "scripts/test_vuln_gate.py")
        self.commit("rm")
        self.assertFlag("受保护的门禁文件 scripts/test_vuln_gate.py")

    def test_script_and_hash_changed_together(self):
        self.write("scripts/vuln-gate.py", "print('bypass')\n")
        self.write("scripts/vuln-gate.sha256", self.sums())
        self.commit("both")
        e = self.errs()
        self.assertTrue(any("scripts/vuln-gate.py 与 base" in x for x in e), e)
        self.assertTrue(any("受保护的门禁文件 scripts/vuln-gate.sha256" in x for x in e), e)

    def test_inline_allow_added(self):
        self.write("src/a.ts", f"const k = 'x' // {ALLOW}\n")
        self.commit("allow")
        self.assertFlag("src/a.ts 新增了 gitleaks 行内放行注释")

    def test_inline_allow_removed_is_fine(self):
        self.write("src/a.ts", f"const k = 'x' // {ALLOW}\n")
        self.base = self.commit("allow")
        self.write("src/a.ts", "const k = 'x'\n")
        self.commit("drop allow")
        self.assertEqual(self.errs(), [])

    def test_uses_sha_changed(self):
        self.write(".github/workflows/security.yml",
                   WF.replace("11d5960a326750d5838078e36cf38b85af677262", "0" * 40))
        self.commit("bump")
        self.assertFlag("uses: 引用有变化")

    def test_uses_added(self):
        self.write(".github/workflows/security.yml",
                   WF + "      - uses: mugsun/.github/x.yml@" + "1" * 40 + "\n")
        self.commit("add")
        self.assertFlag("uses: 引用有变化")

    def test_tool_pin_changed(self):
        self.write(".github/workflows/security.yml", WF.replace("aaaa", "bbbb"))
        self.commit("pin")
        self.assertFlag("SHA256 钉值有变化")

    def test_verify_step_deleted(self):
        self.write(".github/workflows/security.yml",
                   WF.replace("        run: sha256sum -c scripts/vuln-gate.sha256\n",
                              "        run: true\n"))
        self.commit("drop verify")
        self.assertFlag("删了校验或门禁步骤（sha256sum -c")

    def test_gate_call_deleted(self):
        self.write(".github/workflows/security.yml",
                   WF.replace('python3 scripts/vuln-gate.py results --exit-code "$OSV_RC" '
                              "--require-packages x", "echo skip"))
        self.commit("drop gate")
        self.assertFlag("scripts/vuln-gate.py 由 1 处减为 0 处")

    def test_audit_call_deleted(self):
        self.write(".github/workflows/security.yml",
                   WF.replace('python3 scripts/gate-audit.py --base "$BASE_SHA"', "true"))
        self.commit("drop audit")
        self.assertFlag("scripts/gate-audit.py 由 1 处减为 0 处")

    def test_workflow_deleted(self):
        self.git("rm", "-q", ".github/workflows/security.yml")
        self.commit("rm wf")
        self.assertFlag("删了校验或门禁步骤")

    def test_guard_commented_out(self):
        self.write(".github/workflows/security.yml",
                   WF.replace("run: sha256sum -c", "run: true # sha256sum -c"))
        self.commit("comment")
        self.assertFlag("删了校验或门禁步骤（sha256sum -c")

    def test_head_out_of_sync_with_base_hash(self):
        # 不改受保护文件也能发现：base 的哈希表与 head 不一致（比如 base 自身已漂移）
        self.write("scripts/vuln-gate.sha256", "0" * 64 + "  scripts/vuln-gate.py\n")
        self.base = self.commit("bad base")
        self.write("src/a.ts", "x\n")
        self.commit("feat")
        self.assertFlag("与 base 上 scripts/vuln-gate.sha256 记录的哈希不一致")

    def test_base_missing_or_zero(self):
        self.commit("x")
        for b in ("", "0" * 40):
            e = self.errs(b)
            self.assertTrue(e and "没有比较基准" in e[0], e)
        e = self.errs("1" * 40)
        self.assertTrue(e and "找不到" in e[0], e)

    def test_main_exit_codes(self):
        self.commit("x")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ga.main(["--base", self.base, "--repo", self.dir]), 0)
            self.write(".gitleaksignore", "abc\n")
            self.commit("ignore")
            out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(ga.main(["--base", self.base, "--repo", self.dir]), 1)
        self.assertIn("::error::", out.getvalue())


class Facts(unittest.TestCase):
    def test_workflow_facts(self):
        u, p, g = ga.workflow_facts(WF)
        self.assertEqual(u, {"actions/checkout@11d5960a326750d5838078e36cf38b85af677262"})
        self.assertEqual(p, {("OSV_SCANNER_SHA256", "aaaa")})
        self.assertEqual(g["sha256sum -c"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=1)
