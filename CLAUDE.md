# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

An opinionated cookbook of defaults for [OpenClaw](https://openclaw.dev), shipped as a one-command installer. The product is `install.sh`; the recipes are documentation that teaches the patterns those defaults encode. There is also an independent Python diagnostic under `tools/session-analyzer/`.

This is not an application. It has no build step and no runtime of its own. Treat it as: a bash script + markdown + a small stdlib-only Python tool.

## Layout

- `install.sh` — the shipped artifact. Idempotent. Applies thinking-mode default, a curated `tools.allow` / `tools.deny`, registers the DeepWiki MCP server, and copies the cookbook-helper SKILL into the user's OpenClaw workspace. Supports atomic sub-commands (`install.sh apply <target>`) used by the e2e harness — preserve this dispatch shape when editing.
- `recipes/` — markdown patterns (tool-call discipline, hallucination mitigation, thinking-mode tuning, within-turn trust). Linked from `README.md` and surfaced to agents via the cookbook-helper SKILL + DeepWiki MCP.
- `skills/cookbook-helper/` — SKILL fetched by `install.sh` and placed in `~/.openclaw/workspace/skills/`.
- `test/` — docker-compose + shell harness that runs `install.sh` end-to-end against `ghcr.io/openclaw/openclaw:latest`. The container's `~/.openclaw` bind-mounts to `test/.state/` on the host.
- `tools/session-analyzer/` — **independent** Python 3.11+ (stdlib only) analyzer for OpenClaw session JSONL files. Has its own pytest suite and its own README. Not wired into the installer.

## Commands

From the Makefile (repo root):

- `make test` — bash lint, `--help` smoke, and preflight-error tests. No docker required.
- `make test-e2e` — full install run inside a container. Asserts config/SKILL/MCP state and re-runs `install.sh` for idempotency.
- `make run` — apply cookbook config, then keep the gateway running with port `28789` published to the host.
- `make shell` — interactive shell in the test container sharing the same bind-mounted state.
- `make clean-state` — wipe `test/.state/`.

Useful env vars for the installer and harness:

- `COOKBOOK_REF=<branch>` — test against a non-`main` branch (the installer fetches the SKILL by ref).
- `COOKBOOK_BASE_URL=file:///abs/path` — point the installer at a local checkout instead of `raw.githubusercontent.com`.
- `COOKBOOK_ACCEPT_RISK=1` — bypass the onboarding-consent prompt (used in CI and the test harness).
- `COOKBOOK_TEST_IMAGE=<tag>` / `COOKBOOK_HOST_GATEWAY_PORT=<port>` — override the container image or host port.

Session-analyzer (not invoked from the Makefile):

- `python3 tools/session-analyzer/analyze.py <path-to-session.jsonl>` — run the analyzer; add `--format json` for machine output.
- `python3 -m pytest tools/session-analyzer/test/ -v` — its own tests.

## Things to know before editing

- **Idempotency is load-bearing.** `install.sh` must produce the same final state on re-run. The e2e harness runs it twice and asserts. If you add a step, make it re-runnable.
- **E2E assertions live in `test/e2e-run.sh`.** Any change to what the installer writes (config keys, tool allowlist contents, SKILL path, MCP URL) needs matching updates there.
- **Session-analyzer is schema-pinned.** It targets the pi-mono session schema version 3 (`AssistantMessage`, `ToolResultMessage`, `ToolCall`, `Usage`). If tests start reporting empty `tool_call_count` against fresh sessions, suspect a field rename upstream; the tool's README has re-validation pointers.
- **DeepWiki coverage of OpenClaw implementation files is unreliable** — for schema-shape questions prefer raw `badlogic/pi-mono` source over DeepWiki-synthesized answers (noted in `tools/session-analyzer/README.md`).
