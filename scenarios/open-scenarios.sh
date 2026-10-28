#!/usr/bin/env bash
# Open the adversarial staging PRs (scanproof#45) as a CONTRIBUTOR without bypass rights.
#
#   GH_TOKEN=<contributor token, env only> scenarios/open-scenarios.sh [case ...]
#
# Writes scenarios/opened.json (case -> PR number) for the e2e trials auditor. Never merges.
set -euo pipefail
cd "$(dirname "$0")/.."
REPO="${REPO:-abdelrahman-eladwy/scanproof-gate-staging}"
ALL=(positive missing failed skipped tamper weaken-policy rename-context deploy-from-pr)
CASES=("${@:-${ALL[@]}}")
STAMP=$(date -u +%Y%m%d%H%M%S)

[ -n "${GH_TOKEN:-}" ] || { echo "set GH_TOKEN in the environment" >&2; exit 1; }
git diff --quiet && git diff --cached --quiet || { echo "working tree not clean" >&2; exit 1; }
git fetch -q origin main

out=scenarios/opened.json
[ -f "$out" ] || echo '{}' > "$out"
for case in "${CASES[@]}"; do
  branch="trial/$case-$STAMP"
  git checkout -q -B "$branch" origin/main
  python3 scenarios/mutate.py "$case"
  git add -A
  git diff --cached --quiet && { echo "$case: mutation produced no change" >&2; exit 1; }
  git commit -q -m "trial($case): scanproof#45 adversarial scenario"
  git push -q origin "$branch"
  pr=$(gh api "repos/$REPO/pulls" -f title="trial($case): scanproof#45 staging scenario" \
    -f head="$branch" -f base=main \
    -f body="Adversarial staging trial **$case** for scanproof#45. Do NOT merge. See scenarios/README.md." \
    --jq .number)
  python3 - "$out" "$case" "$pr" <<'PY'
import json, sys
path, case, pr = sys.argv[1], sys.argv[2], int(sys.argv[3])
data = json.load(open(path)); data[case] = pr
json.dump(data, open(path, "w"), indent=2, sort_keys=True)
PY
  echo "$case -> PR #$pr"
done
git checkout -q main
