#!/usr/bin/env bash
# ILMUClaw Cookbook — one-command install.
#
# Applies recommended defaults to an OpenClaw installation:
#   - thinking mode       (agents.defaults.thinkingDefault = adaptive)
#   - tool allowlist      (tools.allow / tools.deny)
#   - DeepWiki MCP server (mcp.servers.deepwiki)
#   - cookbook-helper SKILL in the workspace's skills directory
#
# If OpenClaw onboarding has not run yet (no workspace), this script will
# offer to run it non-interactively on your behalf after showing you what
# you'd be acknowledging. You can also set COOKBOOK_ACCEPT_RISK=1 to skip
# that prompt (useful for reruns / automation).
#
# Docs: https://github.com/frogasia/ilmuclaw-cookbook

set -euo pipefail
umask 022

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

COOKBOOK_REF="${COOKBOOK_REF:-main}"
# COOKBOOK_BASE_URL lets you point the script at a local checkout (file://…)
# or a fork without hardcoding. Defaults to raw.githubusercontent.com.
REPO_RAW="${COOKBOOK_BASE_URL:-https://raw.githubusercontent.com/frogasia/ilmuclaw-cookbook/${COOKBOOK_REF}}"
OPENCLAW_HOME="${OPENCLAW_HOME:-$HOME/.openclaw}"
OPENCLAW_WORKSPACE="${OPENCLAW_HOME}/workspace"
SKILL_DIR="${OPENCLAW_WORKSPACE}/skills/cookbook-helper"
SKILL_URL="${REPO_RAW}/skills/cookbook-helper/SKILL.md"

DEEPWIKI_MCP='{"url":"https://mcp.deepwiki.com/mcp","transport":"streamable-http"}'

# Profile: "beginner" — a useful, friendly default for someone running OpenClaw
# on their laptop for the first time. Includes web_search + web_fetch so the
# agent can actually research things, which is the #1 workflow. Users who want
# to tighten down should shrink tools.allow manually.
PROFILE_NAME="beginner"
TOOLS_ALLOW='["read","write","edit","exec","cron","sessions_spawn","sessions_send","sessions_list","sessions_history","memory_search","memory_get","message","web_search","web_fetch"]'
TOOLS_DENY='["canvas","apply_patch"]'

DOCS_URL="https://github.com/frogasia/ilmuclaw-cookbook"
OPENCLAW_SECURITY_URL="https://docs.openclaw.ai/security"
OPENCLAW_INSTALL_URL="https://docs.openclaw.ai/install"

# Exit codes
readonly E_NO_OPENCLAW=10
readonly E_NO_CURL=12
readonly E_NO_TTY=14
readonly E_CONFIG_WRITE=20
readonly E_ONBOARD_FAILED=22
readonly E_DECLINED=30
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
  tool-allowlist         set tools.{allow,deny}
  deepwiki-mcp           register deepwiki MCP server
  cookbook-helper-skill  install skills/cookbook-helper/SKILL.md into the workspace

Prerequisites:
  OpenClaw must be installed and onboarded. If the workspace at
  ~/.openclaw/workspace does not exist, this script will offer to run
  \`openclaw onboard --non-interactive --accept-risk\` for you — after
  showing what --accept-risk means. See: ${OPENCLAW_SECURITY_URL}

Environment:
  OPENCLAW_HOME          override ~/.openclaw (default: \$HOME/.openclaw)
  NO_COLOR               disable ANSI colour
  COOKBOOK_REF           git ref to fetch SKILL from (default: main)
  COOKBOOK_BASE_URL      override the SKILL source base URL (supports file://)
  COOKBOOK_ACCEPT_RISK   set to 1 to skip the consent prompt (for reruns / CI)

Exit codes:
  0   ok
  10  E_NO_OPENCLAW      openclaw CLI not on PATH
  12  E_NO_CURL          curl not on PATH
  14  E_NO_TTY           workspace missing and no tty to ask for consent
  20  E_CONFIG_WRITE     openclaw config/mcp set failed
  22  E_ONBOARD_FAILED   openclaw onboard failed
  30  E_DECLINED         user declined the onboarding consent prompt
  64  E_USAGE            bad argument

SKILL download failures are non-fatal — a loud notice is printed and the
config changes still apply. Rerun \`install.sh apply cookbook-helper-skill\`
to retry.

Docs: ${DOCS_URL}
EOF
}

# ---------------------------------------------------------------------------
# Informed onboarding (option C — show risk, prompt, run onboard)
# ---------------------------------------------------------------------------

print_risk_summary() {
  local pfx="${C_YEL}${C_BOLD}" sfx="$C_RST"
  printf '\n%sOpenClaw onboarding has not run — ~/.openclaw/workspace is missing.%s\n' "$pfx" "$sfx"
  printf '\nThis installer can run it for you non-interactively. Before it does,\n'
  printf 'you should know what you are consenting to:\n\n'
  printf '    OpenClaw is a personal-assistant agent. By default it can execute\n'
  printf '    shell commands, control a browser, and touch files under your user\n'
  printf '    account — without per-action approval prompts. This is intentional\n'
  printf '    UX for single-operator laptops. Do not install it on a machine\n'
  printf '    where that posture is not acceptable.\n\n'
  printf '    Full security model: %s\n\n' "$OPENCLAW_SECURITY_URL"
}

ensure_onboarded() {
  [[ -d "$OPENCLAW_WORKSPACE" ]] && return 0

  if [[ "${COOKBOOK_ACCEPT_RISK:-0}" == "1" ]]; then
    log "COOKBOOK_ACCEPT_RISK=1 set — skipping consent prompt"
  else
    print_risk_summary
    if [[ ! -r /dev/tty ]]; then
      die "E_NO_TTY" "$E_NO_TTY" \
        "~/.openclaw/workspace missing and no controlling tty to read consent from" \
        "either rerun with COOKBOOK_ACCEPT_RISK=1, or run \`openclaw onboard\` yourself first" \
        "${OPENCLAW_SECURITY_URL}"
    fi
    local answer
    printf 'Proceed with non-interactive onboarding? [y/N] '
    read -r answer </dev/tty
    case "$answer" in
      y|Y|yes|YES) ;;
      *)
        log "cancelled. run \`openclaw onboard\` when you're ready, then rerun this installer."
        exit "$E_DECLINED"
        ;;
    esac
  fi

  # --skip-health: onboard otherwise probes the gateway at the end and exits
  # non-zero if it's not running. We don't need the gateway up to apply config.
  log "running: openclaw onboard --non-interactive --accept-risk --skip-health"
  openclaw onboard --non-interactive --accept-risk --skip-health \
    || die "E_ONBOARD_FAILED" "$E_ONBOARD_FAILED" \
      "openclaw onboard --non-interactive --accept-risk --skip-health failed" \
      "run the command manually to see the underlying error" \
      "${DOCS_URL}#troubleshooting"
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

  ensure_onboarded
}

# ---------------------------------------------------------------------------
# Apply sections
# ---------------------------------------------------------------------------

# `openclaw config set` is idempotent — rerunning with the same value yields
# the same state, no duplicate entries.
_cfg_set() {
  openclaw config set "$1" "$2" >/dev/null \
    || die "E_CONFIG_WRITE" "$E_CONFIG_WRITE" \
      "openclaw config set $1 failed" \
      "run the command manually to see the underlying error" \
      "${DOCS_URL}#troubleshooting"
}

apply_thinking_mode() {
  log "applying thinking-mode default → adaptive"
  _cfg_set "agents.defaults.thinkingDefault" "adaptive"
}

apply_tool_allowlist() {
  log "applying tool allowlist (tools.allow + tools.deny)"
  _cfg_set "tools.allow" "$TOOLS_ALLOW"
  _cfg_set "tools.deny"  "$TOOLS_DENY"
}

# `openclaw mcp set` upserts under mcp.servers.<name>.
_mcp_set() {
  openclaw mcp set "$1" "$2" >/dev/null \
    || die "E_CONFIG_WRITE" "$E_CONFIG_WRITE" \
      "openclaw mcp set $1 failed" \
      "run the command manually to see the underlying error" \
      "${DOCS_URL}#troubleshooting"
}

apply_deepwiki_mcp() {
  log "registering deepwiki MCP server"
  _mcp_set "deepwiki" "$DEEPWIKI_MCP"
}

# Non-fatal: a SKILL fetch failure shouldn't wipe out the config writes that
# already succeeded. Sets SKILL_INSTALL_FAILED=1 so the summary can flag it
# loudly at the end.
SKILL_INSTALL_FAILED=0

apply_cookbook_helper_skill() {
  log "fetching cookbook-helper SKILL"
  mkdir -p "$SKILL_DIR"
  local tmp="$SKILL_DIR/SKILL.md.tmp"
  trap 'rm -f "$tmp"' INT TERM EXIT
  if curl -fsSL "$SKILL_URL" -o "$tmp"; then
    mv "$tmp" "$SKILL_DIR/SKILL.md"
  else
    rm -f "$tmp"
    SKILL_INSTALL_FAILED=1
    warn "failed to download ${SKILL_URL}"
    warn "  config changes already applied — rerun \`install.sh apply cookbook-helper-skill\` later"
  fi
  trap - INT TERM EXIT
}

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

print_skill_failure_notice() {
  local pfx="${C_YEL}${C_BOLD}" sfx="$C_RST"
  printf '\n%s!! cookbook-helper SKILL was not installed.%s\n' "$pfx" "$sfx" >&2
  printf '%s   the other configuration changes were applied successfully.%s\n' "$C_YEL" "$sfx" >&2
  printf '%s   rerun this section later with:%s\n' "$C_YEL" "$sfx" >&2
  printf '%s       install.sh apply cookbook-helper-skill%s\n\n' "$C_YEL" "$sfx" >&2
}

print_security_note() {
  local pfx="${C_YEL}${C_BOLD}" sfx="$C_RST"
  printf '\n%snote: applied the "%s" profile — tuned for a friendly local setup.%s\n' \
    "$pfx" "$PROFILE_NAME" "$sfx"
  printf '%sreviewing your agent'\''s tool surface periodically is a good habit —%s\n' "$C_YEL" "$sfx"
  printf '%stight tool allowlists age better than broad ones. see:%s\n' "$C_YEL" "$sfx"
  printf '%s    %s#tool-allowlist--the-beginner-profile%s\n\n' "$C_YEL" "$DOCS_URL" "$sfx"
}

print_done_line() {
  log "done. restart the gateway to apply: \`openclaw gateway restart\`"
}

apply_all() {
  preflight
  apply_thinking_mode
  apply_tool_allowlist
  apply_deepwiki_mcp
  apply_cookbook_helper_skill
  print_done_line
  [[ "$SKILL_INSTALL_FAILED" -eq 1 ]] && print_skill_failure_notice
  print_security_note
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
      print_done_line
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
