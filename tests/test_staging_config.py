"""Offline guards for the staging gate configuration (scanproof#45). Stdlib only."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WF = ROOT / ".github/workflows"
GATE = WF / "scanproof-gate.yml"
DEPLOY = WF / "deploy-staging.yml"
CHECK = "ScanProof verification"
ACTIONS_APP = 15368
REPO = "abdelrahman-eladwy/scanproof-gate-staging"
SHA_RE = re.compile(r"SCANPROOF_COMMIT: ([0-9a-f]{40})\n")
USES_RE = re.compile(r"uses:\s*([^\s#]+)")


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


class Ruleset(unittest.TestCase):
    """Mirrors scanproof-e2e audit_github_gate.py static criteria."""

    @classmethod
    def setUpClass(cls):
        cls.rs = json.loads(read(ROOT / "admin/ruleset.json"))
        cls.rules = {r["type"]: r.get("parameters", {}) for r in cls.rs["rules"]}

    def test_active_on_default_branch_without_bypass(self):
        self.assertEqual(self.rs["enforcement"], "active")
        self.assertEqual(self.rs["target"], "branch")
        self.assertEqual(self.rs["bypass_actors"], [])
        self.assertEqual(self.rs["conditions"]["ref_name"]["include"], ["~DEFAULT_BRANCH"])

    def test_requires_exact_trusted_check_strictly(self):
        sc = self.rules["required_status_checks"]
        self.assertIs(sc["strict_required_status_checks_policy"], True)
        self.assertEqual(sc["required_status_checks"],
                         [{"context": CHECK, "integration_id": ACTIONS_APP}])

    def test_independent_code_owner_review(self):
        pr = self.rules["pull_request"]
        self.assertGreaterEqual(pr["required_approving_review_count"], 1)
        self.assertIs(pr["require_code_owner_review"], True)
        self.assertIs(pr["dismiss_stale_reviews_on_push"], True)
        self.assertIs(pr["require_last_push_approval"], True)

    def test_no_force_push_or_deletion(self):
        self.assertIn("deletion", self.rules)
        self.assertIn("non_fast_forward", self.rules)


class Environment(unittest.TestCase):
    """Mirrors scanproof-e2e audit_github_environment.py criteria."""

    def test_staging_environment_template(self):
        env = json.loads(read(ROOT / "admin/environment.template.json"))
        self.assertIs(env["prevent_self_review"], True)
        self.assertIs(env["can_admins_bypass"], False)
        self.assertEqual(env["deployment_branch_policy"],
                         {"protected_branches": True, "custom_branch_policies": False})
        self.assertEqual(len(env["reviewers"]), 1)
        self.assertEqual(env["reviewers"][0]["type"], "User")
        self.assertEqual(env["reviewers"][0]["id"], "__SECURITY_OWNER_ID__")


class Workflows(unittest.TestCase):
    def test_gate_check_name_is_exact_and_unique(self):
        names = re.findall(r"^    name: (.+)$", read(GATE), re.M)
        self.assertEqual(names.count(CHECK), 1)
        for wf in WF.glob("*.yml"):
            if wf != GATE:
                self.assertNotIn(f"name: {CHECK}\n", read(wf), wf.name)

    def test_gate_fails_on_scanproof_exit_code(self):
        text = read(GATE)
        self.assertIn("scanproof verify --provider github -P policies/scanproof-gate.yaml", text)
        self.assertIn("          exit $rc\n", text)
        self.assertIn("    if: ${{ always() }}\n", text)
        self.assertNotRegex(text, r"\n\s+continue-on-error:")

    def test_same_pinned_core_commit_everywhere(self):
        shas = {m for wf in (GATE, DEPLOY) for m in SHA_RE.findall(read(wf))}
        self.assertEqual(len(shas), 1, shas)

    def test_actions_pinned_by_sha(self):
        for wf in WF.glob("*.yml"):
            for ref in USES_RE.findall(read(wf)):
                if ref.startswith("./"):
                    continue
                self.assertRegex(ref, r"@[0-9a-f]{40}$", f"{wf.name}: {ref}")

    def test_no_secrets_or_privileged_triggers(self):
        for wf in WF.glob("*.yml"):
            text = read(wf)
            self.assertNotIn("secrets.", text, wf.name)
            self.assertNotIn("pull_request_target", text, wf.name)
            self.assertIn("\npermissions:\n  contents: read\n", text, wf.name)
            self.assertNotRegex(text, r"(contents|deployments|pull-requests): write", wf.name)

    def test_deploy_runs_from_default_branch_and_is_environment_gated(self):
        text = read(DEPLOY)
        self.assertIn("  workflow_run:\n    workflows: [scanproof-gate]", text)
        self.assertNotRegex(text, r"\n  (push|pull_request|workflow_dispatch):")
        for cond in ("conclusion == 'success'", "event == 'push'", "head_branch == 'main'",
                     "head_repository.full_name == github.repository"):
            self.assertIn(cond, text)
        self.assertIn("    needs: [reverify]\n    runs-on: ubuntu-latest\n    environment: staging\n",
                      text)
        self.assertIn('"credentials_used": False', text)


class OwnershipAndPolicy(unittest.TestCase):
    def test_codeowners_covers_trust_paths(self):
        lines = [l.split() for l in read(ROOT / ".github/CODEOWNERS").splitlines()
                 if l.strip() and not l.startswith("#")]
        paths = {l[0] for l in lines}
        self.assertTrue({"*", "/.github/", "/policies/", "/admin/", "/.github/CODEOWNERS"} <= paths)
        owners = {o for l in lines for o in l[1:]}
        self.assertEqual(len(owners), 1, "one independent security owner")

    def test_policy_binds_this_repository_and_scope(self):
        text = read(ROOT / "policies/scanproof-gate.yaml")
        self.assertIn(f"project: {{provider: github, id: {REPO}}}", text)
        self.assertIn('required_paths: ["app/"]', text)
        self.assertIn("minimum_scanned_files: 1", text)
        self.assertIn("scanner_errors_allowed: 0", text)


class Scenarios(unittest.TestCase):
    CASES = ["positive", "missing", "failed", "skipped", "tamper",
             "weaken-policy", "rename-context", "deploy-from-pr"]

    def _apply(self, case: str) -> tuple[Path, dict[str, str]]:
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        dst = tmp / "repo"
        shutil.copytree(ROOT, dst, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        before = {str(p.relative_to(dst)): p.read_text("utf-8")
                  for p in dst.rglob("*") if p.is_file()}
        r = subprocess.run([sys.executable, str(dst / "scenarios/mutate.py"), case],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return dst, before

    def test_every_case_changes_the_tree(self):
        for case in self.CASES:
            with self.subTest(case=case):
                dst, before = self._apply(case)
                after = {str(p.relative_to(dst)): p.read_text("utf-8")
                         for p in dst.rglob("*") if p.is_file()}
                self.assertNotEqual(before, after)

    def test_case_specific_effects(self):
        dst, _ = self._apply("skipped")
        self.assertIn("    if: ${{ false }}\n", read(dst / ".github/workflows/scanproof-gate.yml"))
        dst, _ = self._apply("tamper")
        self.assertIn("exit 0  # tampered", read(dst / ".github/workflows/scanproof-gate.yml"))
        dst, _ = self._apply("missing")
        self.assertFalse((dst / ".github/workflows/scanproof-gate.yml").exists())
        dst, _ = self._apply("rename-context")
        self.assertNotIn(f"name: {CHECK}\n", read(dst / ".github/workflows/scanproof-gate.yml"))
        dst, _ = self._apply("deploy-from-pr")
        self.assertIn("environment: staging", read(dst / ".github/workflows/pr-deploy.yml"))

    def test_unknown_case_is_usage_error(self):
        r = subprocess.run([sys.executable, str(ROOT / "scenarios/mutate.py"), "nope"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 3)

    def test_scenario_docs_list_every_case(self):
        doc = read(ROOT / "scenarios/README.md")
        for case in self.CASES:
            self.assertIn(f"| {case} |", doc)


if __name__ == "__main__":
    unittest.main()
