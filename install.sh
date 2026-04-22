#!/usr/bin/env bash
# ILMUClaw Cookbook — one-command install.
#
# Applies recommended defaults to an existing OpenClaw setup:
#   - thinking mode
#   - tool allowlist
#   - DeepWiki MCP
#   - cookbook-helper SKILL
#
# Each concern lives in its own function so atomic sub-commands can be
# exposed later (e.g. `install.sh apply tool-discipline`) without breaking
# the top-level one-liner.
#
# TODO: implement section bodies, idempotency, and the hosted URL
# rewrite (the README one-liner currently points at raw.githubusercontent.com).

set -euo pipefail

# --- thinking mode -----------------------------------------------------------
apply_thinking_mode() {
  :  # TODO
}

# --- tool allowlist ----------------------------------------------------------
apply_tool_allowlist() {
  :  # TODO
}

# --- deepwiki mcp ------------------------------------------------------------
apply_deepwiki_mcp() {
  :  # TODO
}

# --- cookbook-helper skill ---------------------------------------------------
apply_cookbook_helper_skill() {
  :  # TODO
}

# --- entrypoint --------------------------------------------------------------
main() {
  echo "ilmuclaw-cookbook: install.sh is not yet implemented." >&2
  echo "Track progress at https://github.com/frogasia/ilmuclaw-cookbook" >&2
  exit 1
}

main "$@"
