"""Deterministic adversarial mutations for scanproof#45 staging trials.

Each case edits the working tree exactly as a malicious or careless contributor would and
fails loudly if the edit did not apply, so a no-op scenario can never be recorded as a
blocked attack. Stdlib only.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GATE = ROOT / ".github/workflows/scanproof-gate.yml"
POLICY = ROOT / "policies/scanproof-gate.yaml"
APP = ROOT / "app/greeter.py"
README = ROOT / "README.md"


def _replace(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"{path.name}: expected exactly one {old!r}")
    path.write_text(text.replace(old, new), encoding="utf-8")


def positive() -> None:
    # Benign, non-security change; gate must pass and only review should be pending.
    with README.open("a", encoding="utf-8") as fh:
        fh.write("\n<!-- staging trial: benign documentation change -->\n")


def missing() -> None:
    GATE.unlink()


def failed() -> None:
    # Remove the scanned sources: Semgrep has nothing in required_paths -> gate must fail.
    APP.unlink()
    (ROOT / "app").rmdir()


def skipped() -> None:
    _replace(GATE, "    if: ${{ always() }}\n    runs-on: ubuntu-latest\n    permissions:\n"
             "      contents: read\n      actions: read",
             "    if: ${{ false }}\n    runs-on: ubuntu-latest\n    permissions:\n"
             "      contents: read\n      actions: read")


def tamper() -> None:
    # Gate rewritten to always succeed: check is green; only code-owner review stops it.
    _replace(GATE, '          exit $rc\n', '          exit 0  # tampered\n')


def weaken_policy() -> None:
    _replace(POLICY, "      minimum_scanned_files: 1\n", "      minimum_scanned_files: 0\n")
    _replace(POLICY, '      required_paths: ["app/"]\n', "")


def rename_context() -> None:
    _replace(GATE, "    name: ScanProof verification\n",
             "    name: ScanProof verification (v2)\n")


def deploy_from_pr() -> None:
    # A PR-triggered job that targets the protected environment directly.
    (ROOT / ".github/workflows/pr-deploy.yml").write_text(
        "name: pr-deploy\n"
        "on: pull_request\n"
        "permissions:\n  contents: read\n"
        "jobs:\n"
        "  deploy:\n"
        "    runs-on: ubuntu-latest\n"
        "    environment: staging\n"
        "    steps:\n"
        "      - run: echo 'unauthorized staging deployment attempt from PR branch'\n",
        encoding="utf-8",
    )


CASES = {
    "positive": positive,
    "missing": missing,
    "failed": failed,
    "skipped": skipped,
    "tamper": tamper,
    "weaken-policy": weaken_policy,
    "rename-context": rename_context,
    "deploy-from-pr": deploy_from_pr,
}


def main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0] not in CASES:
        print(f"usage: mutate.py {{{','.join(CASES)}}}", file=sys.stderr)
        return 3
    CASES[argv[0]]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
