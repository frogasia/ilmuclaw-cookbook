#!/usr/bin/env bash
# Runs inside the OpenClaw container. Exercises install.sh end-to-end and
# asserts the expected config state landed.
#
# install.sh handles onboarding itself when the workspace is missing — we
# set COOKBOOK_ACCEPT_RISK=1 so the consent prompt is skipped in this
# non-interactive container.

set -euo pipefail

export COOKBOOK_ACCEPT_RISK=1
# Fetch the SKILL from the bind-mounted repo at /work instead of GitHub.
# Decouples this test from the repo being public on GitHub.
export COOKBOOK_BASE_URL="file:///work"

echo "--- first install.sh run (workspace will be bootstrapped)"
/work/install.sh

echo "--- second install.sh run (idempotency check)"
/work/install.sh

echo "--- assertions"
thinking="$(openclaw config get agents.defaults.thinkingDefault)"
[[ "$thinking" == *adaptive* ]] || { echo "FAIL: thinkingDefault=$thinking"; exit 1; }

deny="$(openclaw config get tools.deny)"
[[ "$deny" == *canvas* && "$deny" == *apply_patch* ]] || { echo "FAIL: deny=$deny"; exit 1; }

allow="$(openclaw config get tools.allow)"
[[ "$allow" == *read* && "$allow" == *edit* && "$allow" == *web_search* ]] || { echo "FAIL: allow=$allow"; exit 1; }

mcp="$(openclaw mcp show deepwiki 2>&1)"
[[ "$mcp" == *mcp.deepwiki.com* ]] || { echo "FAIL: deepwiki MCP not registered: $mcp"; exit 1; }

[[ -f "$HOME/.openclaw/workspace/skills/cookbook-helper/SKILL.md" ]] \
  || { echo "FAIL: SKILL missing"; exit 1; }

echo "--- atomic sub-command smoke test"
/work/install.sh apply deepwiki-mcp

echo "all assertions passed"
