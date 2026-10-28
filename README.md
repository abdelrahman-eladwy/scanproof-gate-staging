# scanproof-gate-staging

**Sacrificial, staging-only** repository for [ScanProof #45](https://github.com/abdelrahman-eladwy/scanproof/issues/45):
live acceptance of a protected, independently owned ScanProof release gate on GitHub.

- No production systems, no deployment credentials, no secrets. "Deploy" writes a JSON record.
- `scanproof-gate` runs Semgrep on `app/` and the required check **`ScanProof verification`**
  (`scanproof verify --provider github`, core pinned by commit).
- `deploy-staging` runs from the default branch via `workflow_run`, re-verifies the gate run,
  then enters the protected `staging` environment.
- `admin/` holds the ruleset, environment template and the one-time `bootstrap.sh`.
- `scenarios/` holds eight adversarial PR cases and their expected outcomes.
- `config-selftest` is an offline, non-required check of these files.

**Current mode: single-maintainer (NON-QUALIFYING).** The owner is the only code owner and
environment reviewer, so there is no independent review. Trials in this mode test the
required check and environment rules, and are expected to show the tamper / weaken-policy
gap. Qualifying trials need `admin/bootstrap.sh <distinct-reviewer-login>`.

This repository proves nothing on its own. Evidence counts only once the ruleset and
environment are applied, both e2e preflights pass against it, and contributor merge and
deploy attempts are actually rejected.
