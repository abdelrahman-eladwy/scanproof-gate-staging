#!/usr/bin/env bash
# One-time administrator bootstrap for the SACRIFICIAL staging repository (scanproof#45).
#
# Usage (repository admin, from a clone of this repo on main, ruleset NOT yet applied):
#   GH_TOKEN=<admin token, env only> admin/bootstrap.sh <security-owner-login>
#
# Order matters: CODEOWNERS is committed to main BEFORE the ruleset exists, then the
# environment and ruleset are applied and read back. Nothing here touches the core or e2e
# repositories, and no deployment credential is created.
set -euo pipefail

OWNER_LOGIN="${1:-}"
REPO="${REPO:-abdelrahman-eladwy/scanproof-gate-staging}"
API="repos/$REPO"

die() { echo "bootstrap: $*" >&2; exit 1; }
[[ "$OWNER_LOGIN" =~ ^[A-Za-z0-9](-?[A-Za-z0-9]){0,38}$ ]] || die "invalid GitHub login"
[ -n "${GH_TOKEN:-}" ] || die "set GH_TOKEN (admin) in the environment, never as an argument"
[ "$(git rev-parse --abbrev-ref HEAD)" = main ] || die "run from main"
git diff --quiet && git diff --cached --quiet || die "working tree not clean"

repo_owner=$(gh api "$API" --jq .owner.login)
admin_login=$(gh api user --jq .login)
lc() { tr '[:upper:]' '[:lower:]' <<<"$1"; }
[ "$(lc "$OWNER_LOGIN")" != "$(lc "$repo_owner")" ] || die "security owner must differ from repo owner"
[ "$(lc "$OWNER_LOGIN")" != "$(lc "$admin_login")" ] || die "security owner must differ from the admin"
owner_id=$(gh api "users/$OWNER_LOGIN" --jq .id)
[[ "$owner_id" =~ ^[0-9]+$ ]] || die "could not resolve $OWNER_LOGIN"

if gh api "$API/rulesets" --jq 'length' | grep -qv '^0$'; then
  die "repository already has rulesets; refusing to bypass them for the CODEOWNERS commit"
fi

echo "1/5 CODEOWNERS -> @$OWNER_LOGIN"
sed -i.bak "s/@SECURITY_OWNER/@$OWNER_LOGIN/g" .github/CODEOWNERS && rm .github/CODEOWNERS.bak
! grep -q SECURITY_OWNER .github/CODEOWNERS || die "placeholder remains"
git add .github/CODEOWNERS
git commit -q -m "chore: assign independent security CODEOWNER @$OWNER_LOGIN"
git push -q origin main

echo "2/5 invite @$OWNER_LOGIN as collaborator (push) — they must accept"
gh api -X PUT "$API/collaborators/$OWNER_LOGIN" -f permission=push >/dev/null

echo "3/5 protected staging environment"
sed "s/\"__SECURITY_OWNER_ID__\"/$owner_id/" admin/environment.template.json \
  | gh api -X PUT "$API/environments/staging" --input - >/dev/null

echo "4/5 branch ruleset"
ruleset_id=$(gh api -X POST "$API/rulesets" --input admin/ruleset.json --jq .id)

echo "5/5 read back"
gh api "$API/rulesets/$ruleset_id" \
  --jq '{id, enforcement, bypass_actors, rules: [.rules[].type]}'
gh api "$API/environments/staging" \
  --jq '{can_admins_bypass, deployment_branch_policy, protection_rules}'
gh api "$API/codeowners/errors" --jq '.errors | length' | grep -qx 0 || die "CODEOWNERS errors"

cat <<EOF
Done. Ruleset $ruleset_id active. Next:
  * @$OWNER_LOGIN accepts the collaborator invite.
  * Run scanproof-e2e 'github-protection-preflight' (repository=$REPO, environment=staging).
  * Open scenarios with scenarios/open-scenarios.sh using a CONTRIBUTOR token (not admin).
EOF
