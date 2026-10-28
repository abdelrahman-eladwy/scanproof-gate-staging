# Adversarial staging scenarios (scanproof#45)

Open with `scenarios/open-scenarios.sh` using a **contributor** token (no admin, no bypass).
Never merge a negative PR. For each one, the contributor must *attempt* the merge and the
attempt, its error and the time must be recorded. Expected outcomes:

| Case | Mutation | `ScanProof verification` | Expected platform result |
|---|---|---|---|
| positive | benign README change | success | mergeable **only after** security-owner approval; post-merge `deploy-staging` waits for environment approval, then records |
| missing | deletes `scanproof-gate.yml` | absent | merge blocked: required check missing; code-owner review required |
| failed | deletes `app/` (no scanned sources) | failure | merge blocked: required check failed |
| skipped | gate job `if: false` | skipped | merge blocked: required check skipped; code-owner review required |
| tamper | gate forced to `exit 0` | success (forged) | merge blocked **only** by required code-owner review — this is the control under test |
| weaken-policy | drops `required_paths`, `minimum_scanned_files: 0` | success | merge blocked by code-owner review on `/policies/` |
| rename-context | gate job renamed `(v2)` | original context absent | merge blocked: required context missing |
| deploy-from-pr | new PR workflow targeting `environment: staging` | success | deployment to `staging` rejected: branch is not protected; no reviewer approval |

The first four map to `scanproof-e2e/scripts/audit_github_gate_trials.py`
(`--positive-pr --missing-pr --failed-pr --skipped-pr`, from `scenarios/opened.json`).
The other four are recorded manually with PR link, check JSON and the rejected-merge or
rejected-deployment message.

**Why tamper matters:** on `pull_request` GitHub executes the workflow from the PR head, so
a green check alone never proves the gate ran unmodified. Release-gate independence on this
repository rests on the required, independent CODEOWNER review. If tamper becomes mergeable
without that approval, record **POTENTIAL_BYPASS** and stop.

Recording an observation is not GO: GitLab enforcement (blocked pending Ultimate access)
and the remaining #45 items still apply.
