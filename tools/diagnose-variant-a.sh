#!/usr/bin/env bash
# Diagnoses why DeepWiki MCP doesn't appear in variant-a's Control UI after
# running install.sh via the in-container agent.
#
# Checks the two known failure modes:
#   1. Gateway was PID 1 → `openclaw gateway restart` killed the container.
#   2. Container restart re-runs `cp openclaw.base.json openclaw.json`,
#      wiping install.sh's mcp/tools/thinking writes.
#
# Run from the repo root:   ./tools/diagnose-variant-a.sh

set -u
cd "$(dirname "$0")/.." || exit 1

STATE="./.state-a"
CFG="$STATE/openclaw.json"
BASE="./openclaw.base.json"

bold=$'\033[1m'; red=$'\033[31m'; grn=$'\033[32m'; yel=$'\033[33m'; dim=$'\033[2m'; rst=$'\033[0m'
ok()   { printf '  %s✓%s %s\n' "$grn" "$rst" "$*"; }
bad()  { printf '  %s✗%s %s\n' "$red" "$rst" "$*"; }
warn() { printf '  %s!%s %s\n' "$yel" "$rst" "$*"; }
note() { printf '    %s%s%s\n' "$dim" "$*" "$rst"; }

printf '%s== variant-a diagnostic ==%s\n\n' "$bold" "$rst"

# 1. Container state -----------------------------------------------------------
printf '%s[1] container state%s\n' "$bold" "$rst"
if docker compose ps --status running --services 2>/dev/null | grep -qx variant-a; then
  ok "variant-a is running"
  CONTAINER_UP=1
else
  bad "variant-a is NOT running"
  note "this is expected if the agent ran 'openclaw gateway restart' —"
  note "the gateway is PID 1 (exec'd), so restarting it kills the container."
  CONTAINER_UP=0
fi
echo

# 2. On-disk config ------------------------------------------------------------
printf '%s[2] on-disk config (%s)%s\n' "$bold" "$CFG" "$rst"
if [[ ! -f "$CFG" ]]; then
  bad "$CFG does not exist"
  note "variant-a never booted far enough to write config, or state was wiped."
  echo; exit 1
fi
ok "file exists ($(wc -c <"$CFG" | tr -d ' ') bytes)"

has_jq=0; command -v jq >/dev/null 2>&1 && has_jq=1

if [[ $has_jq -eq 1 ]]; then
  # Is it valid JSON?
  if ! jq empty "$CFG" 2>/dev/null; then
    bad "openclaw.json is not valid JSON"
    echo; exit 1
  fi
  ok "valid JSON"

  # install.sh's three writes:
  deepwiki=$(jq -r '.mcp.servers.deepwiki.url // empty' "$CFG")
  thinking=$(jq -r '.agents.defaults.thinkingDefault // empty' "$CFG")
  tools_allow_count=$(jq -r '(.tools.allow // []) | length' "$CFG")

  if [[ -n "$deepwiki" ]]; then
    ok "mcp.servers.deepwiki present → $deepwiki"
  else
    bad "mcp.servers.deepwiki MISSING from openclaw.json"
    note "install.sh's MCP write is not on disk — either install.sh never"
    note "ran, or the container was restarted and openclaw.base.json was"
    note "cp'd over the top (docker-compose.yml:87)."
  fi

  if [[ "$thinking" == "adaptive" ]]; then
    ok "agents.defaults.thinkingDefault = adaptive (install.sh write present)"
  else
    warn "agents.defaults.thinkingDefault = '${thinking:-<unset>}' (expected 'adaptive')"
    note "install.sh sets this to 'adaptive'; base config ships with 'off'."
  fi

  if [[ "$tools_allow_count" -gt 0 ]]; then
    ok "tools.allow has $tools_allow_count entries"
  else
    warn "tools.allow is empty or absent"
  fi
else
  warn "jq not installed — falling back to grep"
  grep -q '"deepwiki"' "$CFG" && ok "string 'deepwiki' found in openclaw.json" \
                              || bad "string 'deepwiki' NOT found in openclaw.json"
fi
echo

# 3. Base-vs-current divergence ------------------------------------------------
printf '%s[3] base template vs. current config%s\n' "$bold" "$rst"
if [[ -f "$BASE" ]]; then
  if cmp -s "$BASE" "$CFG"; then
    warn "openclaw.json is byte-identical to openclaw.base.json"
    note "meaning: the last container boot cp'd the base over your install.sh"
    note "writes (docker-compose.yml:87). install.sh's effects were wiped."
  else
    ok "openclaw.json has diverged from openclaw.base.json (install.sh writes likely intact)"
  fi
else
  warn "$BASE not found — cannot compare"
fi
echo

# 4. Live gateway MCP list -----------------------------------------------------
printf '%s[4] running gateway MCP list%s\n' "$bold" "$rst"
if [[ $CONTAINER_UP -eq 1 ]]; then
  if docker compose exec -T variant-a openclaw mcp list 2>/dev/null | tee /tmp/.mcp-list.$$ | grep -qi deepwiki; then
    ok "live gateway reports deepwiki in its MCP list"
  else
    bad "live gateway does NOT list deepwiki"
    note "config on disk may include it, but the running gateway hasn't reloaded."
    note "you need to restart the gateway — but see the warning below."
  fi
  rm -f /tmp/.mcp-list.$$
else
  warn "skipped (container not running)"
fi
echo

# 5. Guidance ------------------------------------------------------------------
printf '%s== what to do ==%s\n' "$bold" "$rst"
cat <<EOF

Root cause summary
  • install.sh writes to ~/.openclaw/openclaw.json and tells you to restart the
    gateway. But variant-a exec's the gateway as PID 1, so 'openclaw gateway
    restart' inside the container kills PID 1 → container exits.
  • When you then 'docker compose up variant-a', the boot script cp's
    openclaw.base.json over openclaw.json, wiping install.sh's writes.

Short-term workaround
  • Re-run install.sh from the in-container agent, then instead of restarting
    the gateway, restart the whole container in a way that preserves the writes:
      1. On the host: edit openclaw.base.json to include the mcp.servers.deepwiki
         block (or remove the cp line from docker-compose.yml:87 once the state
         is seeded).
      2. docker compose up -d variant-a

Proper fix (recommended)
  • Change variant-a's command to run install.sh *after* the cp, so every boot
    re-applies the cookbook on top of the base. That's what variant-b already
    does (docker-compose.yml:117). This makes install.sh's effects durable
    across container restarts and removes the PID-1-restart trap.
EOF
