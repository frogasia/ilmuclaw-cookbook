#!/usr/bin/env bash
# ILMUClaw Cookbook — one-command install.
#
# Applies recommended defaults to an existing OpenClaw setup:
#   - thinking mode (agents.defaults.thinkingDefault = adaptive)
#   - tool allowlist (agents.defaults.tools.{allow,deny})
#   - DeepWiki MCP server (mcp.servers.deepwiki)
#   - cookbook-helper SKILL (~/.openclaw/workspace/skills/cookbook-helper/SKILL.md)
#
# Each concern lives in its own function so atomic sub-commands can be
# invoked individually (e.g. `install.sh apply tool-allowlist`) without
# breaking the top-level one-liner.
#
# Docs: https://github.com/frogasia/ilmuclaw-cookbook

set -euo pipefail
umask 022

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

COOKBOOK_REF="${COOKBOOK_REF:-main}"
REPO_RAW="https://raw.githubusercontent.com/frogasia/ilmuclaw-cookbook/${COOKBOOK_REF}"
OPENCLAW_HOME="${OPENCLAW_HOME:-$HOME/.openclaw}"
OPENCLAW_CONFIG="${OPENCLAW_HOME}/openclaw.json"
SKILL_DIR="${OPENCLAW_HOME}/workspace/skills/cookbook-helper"
SKILL_URL="${REPO_RAW}/skills/cookbook-helper/SKILL.md"

DEEPWIKI_MCP='{"url":"https://mcp.deepwiki.com/mcp","transport":"streamable-http"}'

TOOLS_ALLOW='["read","write","edit","exec","cron","sessions_spawn","sessions_send","sessions_list","sessions_history","memory_search","memory_get","message"]'
TOOLS_DENY='["canvas","apply_patch"]'

DOCS_URL="https://github.com/frogasia/ilmuclaw-cookbook"
OPENCLAW_INSTALL_URL="https://openclaw.dev/docs/install"

# Exit codes
readonly E_NO_OPENCLAW=10
readonly E_NO_CONFIG=11
readonly E_NO_CURL=12
readonly E_NO_NETWORK=13
readonly E_CONFIG_WRITE=20
readonly E_SKILL_FETCH=21
readonly E_USAGE=64

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
  C_DIM=$'\033[2m'; C_BOLD=$'\033[1m'; C_RED=$'\033[31m'; C_YEL=$'\033[33m'; C_RST=$'\033[0m'
else
  C_DIM=""; C_BOLD=""; C_RED=""; C_YEL=""; C_RST=""
fi

log()  { printf '%s[cookbook]%s %s\n' "$C_DIM" "$C_RST" "$*"; }
warn() { printf '%s[cookbook]%s %swarn:%s %s\n' "$C_DIM" "$C_RST" "$C_YEL" "$C_RST" "$*" >&2; }

# die <code-name> <code-num> <what> <hint> <url>
die() {
  local name="$1" code="$2" what="$3" hint="$4" url="$5"
  printf '%serror[%s]:%s %s\n' "${C_RED}${C_BOLD}" "$name" "$C_RST" "$what" >&2
  printf '  hint: %s\n' "$hint" >&2
  printf '  see:  %s\n' "$url" >&2
  exit "$code"
}

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

print_help() {
  cat <<EOF
ilmuclaw-cookbook installer — apply recommended defaults to OpenClaw.

Usage:
  install.sh                         apply all sections (thinking, tools, mcp, skill)
  install.sh apply <section>         apply one section
  install.sh --help                  show this message

Sections:
  thinking-mode          set agents.defaults.thinkingDefault = adaptive
  tool-allowlist         set agents.defaults.tools.{allow,deny}
  deepwiki-mcp           register deepwiki MCP server
  cookbook-helper-skill  install skills/cookbook-helper/SKILL.md

Environment:
  OPENCLAW_HOME          override ~/.openclaw (default: \$HOME/.openclaw)
  NO_COLOR               disable ANSI colour
  COOKBOOK_REF           git ref to fetch SKILL from (default: main)

Exit codes:
  0   ok
  10  E_NO_OPENCLAW      openclaw CLI not on PATH
  11  E_NO_CONFIG        ~/.openclaw/openclaw.json missing
  12  E_NO_CURL          curl not on PATH
  13  E_NO_NETWORK       cannot reach raw.githubusercontent.com
  20  E_CONFIG_WRITE     openclaw config/mcp set failed
  21  E_SKILL_FETCH      SKILL download failed
  64  E_USAGE            bad argument

Docs: ${DOCS_URL}
EOF
}

# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

preflight() {
  log "preflight…"

  command -v openclaw >/dev/null 2>&1 || die "E_NO_OPENCLAW" "$E_NO_OPENCLAW" \
    "openclaw CLI not found on PATH" \
    "install OpenClaw first, then rerun this script" \
    "${OPENCLAW_INSTALL_URL}"

  command -v curl >/dev/null 2>&1 || die "E_NO_CURL" "$E_NO_CURL" \
    "curl not found on PATH" \
    "install curl (e.g. brew install curl / apt install curl) and rerun" \
    "${DOCS_URL}#prerequisites"

  [[ -f "$OPENCLAW_CONFIG" ]] || die "E_NO_CONFIG" "$E_NO_CONFIG" \
    "${OPENCLAW_CONFIG} not found" \
    "initialise OpenClaw first with \`openclaw init\`, then rerun this script" \
    "${DOCS_URL}#prerequisites"

  curl -fsSL --max-time 5 -o /dev/null "$REPO_RAW/README.md" 2>/dev/null || die "E_NO_NETWORK" "$E_NO_NETWORK" \
    "cannot reach ${REPO_RAW}" \
    "check your network / proxy settings and try again" \
    "${DOCS_URL}#troubleshooting"
}

# ---------------------------------------------------------------------------
# Apply sections
# ---------------------------------------------------------------------------

# `openclaw config set` is idempotent — rerunning with the same value yields
# the same state, no duplicate entries.
_cfg_set() {
  openclaw config set "$1" "$2" >/dev/null || die "E_CONFIG_WRITE" "$E_CONFIG_WRITE" \
    "openclaw config set $1 failed" \
    "run the command manually to see the underlying error" \
    "${DOCS_URL}#troubleshooting"
}

apply_thinking_mode() {
  log "applying thinking-mode default → adaptive"
  _cfg_set "agents.defaults.thinkingDefault" "adaptive"
}

apply_tool_allowlist() {
  log "applying tool allowlist (global defaults)"
  _cfg_set "agents.defaults.tools.allow" "$TOOLS_ALLOW"
  _cfg_set "agents.defaults.tools.deny"  "$TOOLS_DENY"
}

# `openclaw mcp set` upserts under mcp.servers.<name>.
_mcp_set() {
  openclaw mcp set "$1" "$2" >/dev/null || die "E_CONFIG_WRITE" "$E_CONFIG_WRITE" \
    "openclaw mcp set $1 failed" \
    "run the command manually to see the underlying error" \
    "${DOCS_URL}#troubleshooting"
}

apply_deepwiki_mcp() {
  log "registering deepwiki MCP server"
  _mcp_set "deepwiki" "$DEEPWIKI_MCP"
}

apply_cookbook_helper_skill() {
  log "fetching cookbook-helper SKILL"
  mkdir -p "$SKILL_DIR"
  local tmp="$SKILL_DIR/SKILL.md.tmp"
  trap 'rm -f "$tmp"' INT TERM EXIT
  curl -fsSL "$SKILL_URL" -o "$tmp" || die "E_SKILL_FETCH" "$E_SKILL_FETCH" \
    "failed to download ${SKILL_URL}" \
    "verify the ref '${COOKBOOK_REF}' exists on github.com/frogasia/ilmuclaw-cookbook" \
    "${DOCS_URL}#troubleshooting"
  mv "$tmp" "$SKILL_DIR/SKILL.md"
  trap - INT TERM EXIT
}

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

apply_all() {
  preflight
  apply_thinking_mode
  apply_tool_allowlist
  apply_deepwiki_mcp
  apply_cookbook_helper_skill
  log "done. restart your openclaw session for changes to take effect."
}

main() {
  case "${1:-}" in
    ""|all)
      apply_all
      ;;
    apply)
      case "${2:-}" in
        thinking-mode)         preflight; apply_thinking_mode ;;
        tool-allowlist)        preflight; apply_tool_allowlist ;;
        deepwiki-mcp)          preflight; apply_deepwiki_mcp ;;
        cookbook-helper-skill) preflight; apply_cookbook_helper_skill ;;
        "")                    warn "\`apply\` requires a section name"; print_help >&2; exit "$E_USAGE" ;;
        *)                     warn "unknown section: ${2}"; print_help >&2; exit "$E_USAGE" ;;
      esac
      log "done. restart your openclaw session for changes to take effect."
      ;;
    -h|--help|help)
      print_help
      ;;
    *)
      warn "unknown argument: ${1}"
      print_help >&2
      exit "$E_USAGE"
      ;;
  esac
}

main "$@"
