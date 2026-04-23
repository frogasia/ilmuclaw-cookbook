# session-analyzer

A read-only analyzer for OpenClaw session JSONL files. Parses one session and emits
deterministic signals about tool-call trajectory health: repeats, ping-pong loops,
no-progress polls, token hotspots, and error storms.

Internal instrument. No daemon, no installer, no MCP wiring. Run it against a
session file, get JSON or a text summary, decide whether the trajectory needs
attention.

## Why

`AgentSessionEvent` (the live event stream pi-mono exposes via `--mode rpc`) is
live-only: once a session ends, only the JSONL on disk remains. `openclaw sessions
--json` returns metadata but no per-tool stats. To answer "did this run loop on the
same tool, and how badly," you read the JSONL yourself. This script does that
deterministically — five rules, fixed thresholds, no model in the loop.

## Install

None. Python 3.11+ standard library only. The one dev dependency is `pytest` for
the detector tests.

```sh
python3 --version           # 3.11+
python3 -m pytest --version # for tests
```

## Usage

```sh
python3 analyze.py <path-to-session.jsonl>
python3 analyze.py <path-to-session.jsonl> --format json
python3 analyze.py --help
```

Sessions live at `~/.openclaw/agents/<agentId>/sessions/<sessionId>.jsonl`.
The `<agentId>` is derived from the file path; pass the full path so it can be
extracted.

## Output

Text summary (default) — 20–40 lines, eyeball-friendly:

```
session  bdffc39d-d9bc-...
agent    triage-bot
model    <provider>/<model>
turns    28    tool calls 24
tokens   in=1251996 out=22408 cacheR=798720 cacheW=0

per-tool
  read                     calls=14 errors=0 tokens=632394 share=57%
  ...

signals (3)
  [warning ] generic_repeat     tool=read count=12 detail={'window': 24}
  [critical] no_progress_poll   tool=read count=12 detail={'window': 24}
  [warning ] token_hotspot      tool=read count=14 detail={'share': 0.573, ...}
```

JSON (for piping into other tooling):

```json
{
  "session_id": "...",
  "agent_id": "...",
  "model": "...",
  "turn_count": 28,
  "tool_call_count": 24,
  "total_tokens": { "input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "total": 0 },
  "per_tool_stats": {
    "<toolName>": { "calls": 0, "errors": 0, "tokens_attributed": 0, "token_share": 0.0 }
  },
  "signals": [
    {
      "type": "generic_repeat|ping_pong|no_progress_poll|token_hotspot|error_storm",
      "severity": "warning|critical",
      "tool": "<toolName>",
      "count": 0,
      "window_start_id": "...",
      "window_end_id": "...",
      "detail": {}
    }
  ]
}
```

## Detectors

| Detector | Rule | Window | Warn / Crit |
|---|---|---|---|
| `generic_repeat`   | Same tool, same args | last 30 calls | 10 / 20 |
| `ping_pong`        | Alternating A-B-A-B  | last 30 calls | 4 cycles / 8 cycles |
| `no_progress_poll` | Same call, same result | last 30 (call,result) pairs | 5 / 10 |
| `token_hotspot`    | One tool dominates input+output token share | whole session | 40% / 60% |
| `error_storm`      | High `isError:true` rate (n≥3) | whole session | 30% / 50% |

Thresholds mirror the `tools.loopDetection` defaults documented for OpenClaw
(`historySize=30`, `warningThreshold=10`, `criticalThreshold=20`) plus the cycle /
share / rate variants the live runtime backstop does not expose.

## Tests

```sh
python3 -m pytest tools/session-analyzer/test/ -v
```

Each detector has a fixture in `fixtures/`:

- `healthy.jsonl`         — synthesized clean session; analyzer must report 0 signals.
- `generic-repeat.jsonl`  — sanitized capture of a real read-storm session;
                            fires `generic_repeat`, `no_progress_poll`,
                            `token_hotspot`.
- `ping-pong.jsonl`       — synthesized A-B alternating run; fires `ping_pong`.
- `error-storm.jsonl`     — synthesized run with 60% errors on one tool;
                            fires `error_storm`.

## Pin: validated against OpenClaw

This analyzer was built and validated against:

- **OpenClaw image:** `ghcr.io/openclaw/openclaw:latest` digest as of 2026-04-17.
  CLI reports `v24.14.0`.
- **Session schema:** `badlogic/pi-mono` →
  `packages/coding-agent/src/core/session-manager.ts` (CURRENT_SESSION_VERSION = 3),
  `packages/ai/src/types.ts` (`AssistantMessage`, `ToolResultMessage`, `ToolCall`,
  `Usage`).

`pi-coding-agent` is an external dependency of OpenClaw and the schema can drift.
Re-validate when bumping OpenClaw if the analyzer starts emitting empty
`tool_call_count` against new sessions — that usually means a field rename.

If a quick schema check is needed, `cat` the two files above from a local clone of
`badlogic/pi-mono` (or `gh api repos/badlogic/pi-mono/contents/<path> --jq
'.download_url' | xargs curl -sL`) before debugging the analyzer. DeepWiki coverage
of `openclaw/openclaw` implementation files is unreliable — prefer raw source over
synthesized answers for schema-shape questions.

## Limitations

- Walks entries in file order; ignores branch trees (single-chain v1 simplification).
- `ImageContent` results are skipped for `no_progress_poll` (no meaningful hash).
- Token attribution is proximate: tokens charged to the AssistantMessage holding the
  `toolCall` block, summed per tool. Multi-tool messages are split equally by call
  count within that message.
- Sessions without the v3 `id`/`parentId` fields still parse; the analyzer simply
  does not use the tree structure.
