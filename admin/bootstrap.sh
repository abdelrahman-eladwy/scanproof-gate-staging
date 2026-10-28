#!/usr/bin/env bash
# One-time administrator setup for the SACRIFICIAL staging repository (scanproof#45).
#
#   GH_TOKEN=<admin token, env only> admin/bootstrap.sh --single-maintainer
#       Repo owner is the only code owner and environment reviewer. Required check
#       enforced; approvals/code-owner review OFF. Evidence only, NON-QUALIFYING.
#
#   GH_TOKEN=<admin token, env only> admin/bootstrap.sh <security-owner-login>
#       Qualifying mode: a distinct reviewer becomes code owner and environment reviewer;
#       1 approval + code-owner review + last-push approval required.
#
# Run from a clone of this repo on main, BEFORE any ruleset exists. Creates no credential
# and touches no other repository.
set -euo pipefail

REPO="${REPO:-abdelrahman-eladwy/scanproof-gate-staging}"
API="repos/$REPO"
die() { echo "bootstrap: $*" >&2; exit 1; }
lc() { tr '[:upper:]' '[:lower:]' <<<"$1"; }

ARG="${1:-}"
[ -n "$ARG" ] || die "usage: bootstrap.sh --single-maintainer | <security-owner-login>"
[ -n "${GH_TOKEN:-}" ] || die "set GH_TOKEN (admin) in the environment, never as an argument"
command -v gh >/dev/null || die "GitHub CLI 'gh' is required"
[ "$(git rev-parse --abbrev-ref HEAD)" = main ] || die "run from main"
git diff --quiet && git diff --cached --quiet || die "working tree not clean"
git pull -q --ff-only origin main

repo_owner=$(gh api "$API" --jq .owner.login)
[ "$(gh api "$API" --jq .permissions.admin)" = true ] || die "token lacks admin on $REPO"
[ "$(gh api "$API/rulesets" --jq length)" = 0 ] || die "rulesets already exist; refusing"

if [ "$ARG" = "--single-maintainer" ]; then
  MODE=single-maintainer
  OWNER_LOGIN="$repo_owner"
  RULESET=admin/ruleset.single-maintainer.json
  ENV_TEMPLATE=admin/environment.single-maintainer.template.json
else
  MODE=qualifying
  OWNER_LOGIN="$ARG"
  [[ "$OWNER_LOGIN" =~ ^[A-Za-z0-9](-?[A-Za-z0-9]){0,38}$ ]] || die "invalid GitHub login"
  [ "$(lc "$OWNER_LOGIN")" != "$(lc "$repo_owner")" ] || die "security owner must differ from repo owner"
  [ "$(lc "$OWNER_LOGIN")" != "$(lc "$(gh api user --jq .login)")" ] || die "security owner must differ from the admin"
  RULESET=admin/ruleset.json
  ENV_TEMPLATE=admin/environment.template.json
fi
owner_id=$(gh api "users/$OWNER_LOGIN" --jq .id)
[[ "$owner_id" =~ ^[0-9]+$ ]] || die "could not resolve $OWNER_LOGIN"
echo "mode: $MODE   code owner / environment reviewer: @$OWNER_LOGIN ($owner_id)"

if [ "$MODE" = qualifying ]; then
  echo "1/4 CODEOWNERS -> @$OWNER_LOGIN, invite as collaborator (they must accept)"
  sed -i.bak "s/@$repo_owner\$/@$OWNER_LOGIN/" .github/CODEOWNERS && rm .github/CODEOWNERS.bak
  git add .github/CODEOWNERS
  git commit -q -m "chore: assign independent security CODEOWNER @$OWNER_LOGIN"
  git push -q origin main
  gh api -X PUT "$API/collaborators/$OWNER_LOGIN" -f permission=push >/dev/null
else
  echo "1/4 CODEOWNERS already names @$OWNER_LOGIN (single-maintainer)"
fi
grep -q "@$OWNER_LOGIN" .github/CODEOWNERS || die "CODEOWNERS does not name @$OWNER_LOGIN"

echo "2/4 protected staging environment"
sed "s/\"__SECURITY_OWNER_ID__\"/$owner_id/" "$ENV_TEMPLATE" \
  | gh api -X PUT "$API/environments/staging" --input - >/dev/null

echo "3/4 branch ruleset ($RULESET)"
ruleset_id=$(gh api -X POST "$API/rulesets" --input "$RULESET" --jq .id)

echo "4/4 read back"
gh api "$API/rulesets/$ruleset_id" --jq \
  '{id, name, enforcement, bypass_actors, rules: [.rules[] | {type, parameters}]}'
gh api "$API/environments/staging" --jq \
  '{name, can_admins_bypass, deployment_branch_policy,
    protection_rules: [.protection_rules[] | {type, prevent_self_review,
      reviewers: [.reviewers[]? | {type, login: .reviewer.login, id: .reviewer.id}]}]}'
[ "$(gh api "$API/codeowners/errors" --jq '.errors | length')" = 0 ] || die "CODEOWNERS errors"
echo "DONE mode=$MODE ruleset=$ruleset_id — paste this output to Claude, then delete the token."
