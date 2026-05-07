#!/usr/bin/env python3
"""OpenClaw session trajectory analyzer.

Reads a session JSONL file (as written by pi-coding-agent) and emits
deterministic signals about tool-call trajectory health: repeats, ping-pong
loops, no-progress polls, token hotspots, and error storms.

Schema reference: badlogic/pi-mono
  packages/coding-agent/src/core/session-manager.ts
  packages/ai/src/types.ts
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

WINDOW = 30
GENERIC_REPEAT_WARN, GENERIC_REPEAT_CRIT = 10, 20
PING_PONG_WARN, PING_PONG_CRIT = 4, 8  # full A-B cycles
NO_PROGRESS_WARN, NO_PROGRESS_CRIT = 5, 10
TOKEN_HOTSPOT_WARN, TOKEN_HOTSPOT_CRIT = 0.40, 0.60
ERROR_STORM_WARN, ERROR_STORM_CRIT = 0.30, 0.50
ERROR_STORM_MIN_N = 3
SHORT_SEGMENT_MAX = 10
SHORT_SEGMENT_REPEAT_MIN = 5
AGGREGATE_MODEL = "*"


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


@dataclass
class ToolEvent:
    """One tool call paired with its result and the proximate token cost.

    Detectors only ever see ToolEvent — they never re-parse the JSONL. This
    keeps detector logic decoupled from pi-mono's session schema: if a future
    schema change requires a new field, it lands here and parse_session adapts.

    `args_hash` and `result_hash` are sha256 prefixes (16 hex chars) of canonical
    JSON for the args and the concatenated TextContent of the result. `result_hash`
    is None when the toolResult message is missing (still in flight, dropped) or
    when all result content is ImageContent (no meaningful hash; per §6a, v1).
    """
    entry_id: str
    tool: str
    args_hash: str
    result_hash: str | None
    is_error: bool
    assistant_input_tokens: int
    assistant_output_tokens: int
    model: str = ""


@dataclass
class Session:
    """Parsed view of one session JSONL file.

    Holds both the raw `entries` (for header/turn counting) and the derived
    `tool_events` list (which is what every detector actually consumes).
    `total_tokens` is summed across all assistant messages, not just those
    containing tool calls — it represents the full LLM bill for the session.
    """
    session_id: str
    agent_id: str
    cwd: str
    model: str
    entries: list[dict] = field(default_factory=list)
    tool_events: list[ToolEvent] = field(default_factory=list)
    total_tokens: dict = field(default_factory=lambda: {
        "input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "total": 0,
    })


def parse_session(path: Path) -> Session:
    """Parse a session JSONL into a Session.

    Tolerates malformed lines (skips them, mirroring pi-mono's parser). Walks
    entries in file order; does not reconstruct the parent/child tree, since v1
    sessions lack `parentId` and v3 branches are out of scope per §6a. Token
    cost is split equally across tool calls in the same assistant message
    (see analyze() for why proximate attribution is good enough for v1).
    """
    entries: list[dict] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    header = next((e for e in entries if e.get("type") == "session"), {})
    agent_id = _agent_id_from_path(path)
    model = _resolve_model(entries)
    sess = Session(
        session_id=header.get("id", ""),
        agent_id=agent_id,
        cwd=header.get("cwd", ""),
        model=model,
        entries=entries,
    )

    # Index tool results by toolCallId for pairing.
    results_by_call: dict[str, dict] = {}
    for e in entries:
        if e.get("type") != "message":
            continue
        msg = e.get("message", {})
        if msg.get("role") == "toolResult":
            results_by_call[msg.get("toolCallId", "")] = msg

    # Walk in file order; emit one ToolEvent per toolCall block.
    # Track the live model: assistant messages carry `msg["model"]` directly,
    # but a `model_change` entry between assistant messages signals an
    # imminent switch. We prefer the assistant message's own `model` (it's
    # the model that actually ran the call) and fall back to the most
    # recent `model_change` formatted as `provider/modelId` to match
    # `_resolve_model`.
    live_model = ""
    for e in entries:
        et = e.get("type")
        if et == "model_change":
            live_model = f"{e.get('provider','')}/{e.get('modelId','')}"
            continue
        if et != "message":
            continue
        msg = e.get("message", {})
        if msg.get("role") != "assistant":
            continue
        usage = msg.get("usage") or {}
        _accumulate_tokens(sess.total_tokens, usage)
        msg_model = msg.get("model") or live_model
        tool_calls = [b for b in (msg.get("content") or [])
                      if isinstance(b, dict) and b.get("type") == "toolCall"]
        if not tool_calls:
            continue
        in_tok = int(usage.get("input", 0) or 0) // len(tool_calls)
        out_tok = int(usage.get("output", 0) or 0) // len(tool_calls)
        for block in tool_calls:
            args = block.get("arguments") or {}
            result = results_by_call.get(block.get("id", ""))
            sess.tool_events.append(ToolEvent(
                entry_id=e.get("id", ""),
                tool=block.get("name", ""),
                args_hash=sha(canonical_json(args)),
                result_hash=_hash_result(result),
                is_error=bool(result.get("isError")) if result else False,
                assistant_input_tokens=in_tok,
                assistant_output_tokens=out_tok,
                model=msg_model,
            ))
    return sess


def _agent_id_from_path(path: Path) -> str:
    parts = path.resolve().parts
    if "agents" in parts:
        i = parts.index("agents")
        if i + 1 < len(parts):
            return parts[i + 1]
    return ""


def _resolve_model(entries: list[dict]) -> str:
    last_change = None
    for e in entries:
        if e.get("type") == "model_change":
            last_change = e
    if last_change:
        return f"{last_change.get('provider','')}/{last_change.get('modelId','')}"
    for e in entries:
        if e.get("type") == "message" and (e.get("message") or {}).get("role") == "assistant":
            return (e["message"].get("model") or "")
    return ""


def _accumulate_tokens(totals: dict, usage: dict) -> None:
    for k in ("input", "output", "cacheRead", "cacheWrite"):
        totals[k] += int(usage.get(k, 0) or 0)
    totals["total"] = totals["input"] + totals["output"]


def _hash_result(result: dict | None) -> str | None:
    if not result:
        return None
    chunks = []
    for c in result.get("content", []) or []:
        if isinstance(c, dict) and c.get("type") == "text":
            chunks.append(c.get("text", ""))
    if not chunks:
        return None  # all-image or empty result; skip per §6a
    return sha("".join(chunks))


# ---------- detectors ----------

def detect_generic_repeat(events: list[ToolEvent]) -> list[dict]:
    """Flag tools called repeatedly with identical arguments inside a sliding window.

    Catches the most common failure mode: an agent stuck re-running the same
    `read` / `grep` / `bash` invocation because it doesn't trust the previous
    result, or because instruction-following degraded mid-turn. Mirrors
    OpenClaw's `tools.loopDetection` runtime backstop (warn=10, crit=20 over
    the last 30 calls) so post-hoc signals line up with what the runtime would
    have seen.

    Caveat: ignores result content. If the agent is correctly polling a URL
    that legitimately returns different data each time, this still fires.
    Cross-check with `no_progress_poll` to distinguish "looping" from "polling
    a moving target."
    """
    events = events[-WINDOW:] if len(events) > WINDOW else events
    counts: dict[tuple[str, str], list[ToolEvent]] = {}
    for ev in events:
        counts.setdefault((ev.tool, ev.args_hash), []).append(ev)
    out = []
    for (tool, _h), bucket in counts.items():
        n = len(bucket)
        if n >= GENERIC_REPEAT_CRIT:
            sev = "critical"
        elif n >= GENERIC_REPEAT_WARN:
            sev = "warning"
        else:
            continue
        out.append({
            "type": "generic_repeat",
            "severity": sev,
            "tool": tool,
            "count": n,
            "window_start_id": bucket[0].entry_id,
            "window_end_id": bucket[-1].entry_id,
            "detail": {"window": len(events)},
        })
    return out


def detect_ping_pong(events: list[ToolEvent]) -> list[dict]:
    """Flag the longest A-B-A-B alternation in the recent window.

    Catches the second-most-common failure mode: an agent oscillating between
    two tools (typically `read` ↔ `edit`, or a search tool ↔ a viewer) without
    converging. Looks at tool *names* only, so a true cycle on the same pair of
    files reads as ping-pong even when args differ slightly.

    Returns at most one signal — the longest alternating run found. Warn at 4
    full cycles (8 calls), crit at 8 cycles (16 calls). Below 4 cycles the
    pattern is too noisy to call.
    """
    events = events[-WINDOW:] if len(events) > WINDOW else events
    if len(events) < 4:
        return []
    seq = [ev.tool for ev in events]
    # Find longest A-B alternating run.
    best = (0, 0, 0)  # cycles, start, end
    i = 0
    while i < len(seq) - 1:
        a, b = seq[i], seq[i + 1]
        if a == b:
            i += 1
            continue
        j = i
        while j + 1 < len(seq) and seq[j] == (a if (j - i) % 2 == 0 else b) \
                and seq[j + 1] == (b if (j - i) % 2 == 0 else a):
            j += 1
        run_len = j - i + 1  # number of positions
        cycles = run_len // 2
        if cycles > best[0]:
            best = (cycles, i, j)
        i = max(j, i + 1)
    cycles, start, end = best
    if cycles >= PING_PONG_CRIT:
        sev = "critical"
    elif cycles >= PING_PONG_WARN:
        sev = "warning"
    else:
        return []
    return [{
        "type": "ping_pong",
        "severity": sev,
        "tool": [seq[start], seq[start + 1]],
        "count": cycles,
        "window_start_id": events[start].entry_id,
        "window_end_id": events[end].entry_id,
        "detail": {"window": len(events)},
    }]


def detect_no_progress_poll(events: list[ToolEvent]) -> list[dict]:
    """Flag identical (call, result) pairs — the agent learned nothing new.

    Stricter cousin of `generic_repeat`: only counts repeats where the result
    content is byte-identical too. This is the strongest "the agent is wasting
    tokens" signal because legitimate polling against a moving target would
    produce different result hashes. Tighter thresholds (warn=5, crit=10) than
    generic_repeat reflect the higher confidence.

    Caveat: skips events whose result hash is None — that includes results not
    yet written when the file was inspected, and image-only results (no
    meaningful text hash; per §6a, v1 limitation).
    """
    events = [ev for ev in events if ev.result_hash is not None]
    events = events[-WINDOW:] if len(events) > WINDOW else events
    counts: dict[tuple[str, str, str], list[ToolEvent]] = {}
    for ev in events:
        counts.setdefault((ev.tool, ev.args_hash, ev.result_hash or ""), []).append(ev)
    out = []
    for (tool, _a, _r), bucket in counts.items():
        n = len(bucket)
        if n >= NO_PROGRESS_CRIT:
            sev = "critical"
        elif n >= NO_PROGRESS_WARN:
            sev = "warning"
        else:
            continue
        out.append({
            "type": "no_progress_poll",
            "severity": sev,
            "tool": tool,
            "count": n,
            "window_start_id": bucket[0].entry_id,
            "window_end_id": bucket[-1].entry_id,
            "detail": {"window": len(events)},
        })
    return out


def detect_token_hotspot(events: list[ToolEvent], per_tool: dict) -> list[dict]:
    """Flag any single tool that consumes a disproportionate share of tokens.

    Whole-session view (no window) — answers "where did the budget go?" Useful
    for triaging cost-blown sessions where no individual loop fired but one
    tool quietly dominated. Warn at 40% share, crit at 60%.

    Caveat: token attribution is proximate (input+output of the AssistantMessage
    holding the toolCall, split equally across calls in that message). Cache
    reads/writes are excluded from the share calculation. Sessions with very
    few tool variants (2-3) will naturally trip this even when behaviour is
    healthy — interpret alongside the per-tool call counts.
    """
    total = sum(p["tokens_attributed"] for p in per_tool.values())
    if total == 0:
        return []
    out = []
    for tool, p in per_tool.items():
        share = p["tokens_attributed"] / total
        if share >= TOKEN_HOTSPOT_CRIT:
            sev = "critical"
        elif share >= TOKEN_HOTSPOT_WARN:
            sev = "warning"
        else:
            continue
        out.append({
            "type": "token_hotspot",
            "severity": sev,
            "tool": tool,
            "count": p["calls"],
            "window_start_id": "",
            "window_end_id": "",
            "detail": {"share": round(share, 3), "tokens": p["tokens_attributed"]},
        })
    return out


def detect_error_storm(events: list[ToolEvent], per_tool: dict) -> list[dict]:
    """Flag tools whose results are mostly errors (≥30% with n≥3).

    Catches "agent keeps trying the wrong shape" — wrong arguments, missing
    permissions, malformed paths — without needing to read the error text. The
    n≥3 floor avoids noise from one-off transient errors. Warn at 30%, crit
    at 50%.

    Caveat: an `isError:true` result can mean anything the tool implementation
    decided to flag — schema validation failure, business-logic rejection,
    upstream 5xx. Treat this as "look at these results manually" rather than
    "the tool is broken."
    """
    out = []
    for tool, p in per_tool.items():
        n = p["calls"]
        if n < ERROR_STORM_MIN_N:
            continue
        rate = p["errors"] / n
        if rate >= ERROR_STORM_CRIT:
            sev = "critical"
        elif rate >= ERROR_STORM_WARN:
            sev = "warning"
        else:
            continue
        out.append({
            "type": "error_storm",
            "severity": sev,
            "tool": tool,
            "count": p["errors"],
            "window_start_id": "",
            "window_end_id": "",
            "detail": {"rate": round(rate, 3), "calls": n},
        })
    return out


def per_tool_stats(events: list[ToolEvent]) -> dict:
    """Aggregate calls / errors / attributed tokens / share, keyed by tool name.

    Detector inputs and the `per_tool_stats` block in the JSON output share
    this same shape so what you read in the summary is what the detectors saw.
    Accepts an event list directly so it can be reused on per-model slices.
    """
    stats: dict[str, dict] = {}
    for ev in events:
        s = stats.setdefault(ev.tool, {"calls": 0, "errors": 0, "tokens_attributed": 0, "token_share": 0.0})
        s["calls"] += 1
        if ev.is_error:
            s["errors"] += 1
        s["tokens_attributed"] += ev.assistant_input_tokens + ev.assistant_output_tokens
    total = sum(s["tokens_attributed"] for s in stats.values()) or 1
    for s in stats.values():
        s["token_share"] = round(s["tokens_attributed"] / total, 3)
    return stats


def detect_short_segment_repeat(events: list[ToolEvent]) -> list[dict]:
    """Flag tiny segments that are entirely identical calls.

    Captures the "few rounds of retrying then gave up and switched model"
    pattern: a 6-event segment with 6 identical calls won't trip
    `generic_repeat`'s WARN=10 threshold, but it's the exact behaviour we
    want surfaced when looking at per-model segments.

    Fires only when:
      - segment is short (len <= SHORT_SEGMENT_MAX)
      - every event in the segment shares the same (tool, args_hash)
      - count >= SHORT_SEGMENT_REPEAT_MIN
    Severity is always `warning` — short-segment evidence is suggestive,
    not conclusive.
    """
    n = len(events)
    if n < SHORT_SEGMENT_REPEAT_MIN or n > SHORT_SEGMENT_MAX:
        return []
    first = (events[0].tool, events[0].args_hash)
    if not all((ev.tool, ev.args_hash) == first for ev in events):
        return []
    return [{
        "type": "short_segment_repeat",
        "severity": "warning",
        "tool": first[0],
        "count": n,
        "window_start_id": events[0].entry_id,
        "window_end_id": events[-1].entry_id,
        "detail": {"segment_length": n},
    }]


def model_segments(events: list[ToolEvent]) -> list[list[ToolEvent]]:
    """Split events into contiguous same-model runs.

    A→B→A produces three segments, not two. This matters because window
    detectors are time-local: a loop in the first A-segment must not be
    diluted by a clean later A-segment.
    """
    if not events:
        return []
    segs: list[list[ToolEvent]] = []
    cur = [events[0]]
    for ev in events[1:]:
        if ev.model == cur[-1].model:
            cur.append(ev)
        else:
            segs.append(cur)
            cur = [ev]
    segs.append(cur)
    return segs


def group_by_model(events: list[ToolEvent]) -> dict[str, list[ToolEvent]]:
    """Bucket events by model, preserving file order within each bucket.

    Used for whole-session detectors (`token_hotspot`, `error_storm`) where
    "tool X errored 60% on model A" is a model-level fact independent of
    when the calls happened.
    """
    out: dict[str, list[ToolEvent]] = {}
    for ev in events:
        out.setdefault(ev.model, []).append(ev)
    return out


def models_used_sequence(events: list[ToolEvent]) -> list[str]:
    """Contiguously-deduped model sequence in entry order.

    A→A→B→B→A becomes ["A","B","A"] — the switch sequence consumers care
    about, not just the unique set.
    """
    out: list[str] = []
    for ev in events:
        if not out or out[-1] != ev.model:
            out.append(ev.model)
    return out


def per_model_stats(events: list[ToolEvent]) -> dict:
    """Per-model rollup: tool calls, attributed tokens, errors, segments."""
    stats: dict[str, dict] = {}
    for ev in events:
        s = stats.setdefault(ev.model, {
            "tool_calls": 0, "tokens_attributed": 0, "errors": 0, "segments": 0,
        })
        s["tool_calls"] += 1
        s["tokens_attributed"] += ev.assistant_input_tokens + ev.assistant_output_tokens
        if ev.is_error:
            s["errors"] += 1
    # Count contiguous segments per model.
    for seg in model_segments(events):
        m = seg[0].model
        if m in stats:
            stats[m]["segments"] += 1
    return stats


def analyze(path: Path) -> dict:
    """End-to-end: parse the JSONL, run all detectors, return the report dict.

    Window-based detectors (generic_repeat, ping_pong, no_progress_poll,
    short_segment_repeat) run per contiguous model-segment so a loop on
    model A is never diluted by a clean run on model B that follows.

    Whole-session detectors (token_hotspot, error_storm) run per model
    group (all events for a given model) and additionally once across the
    whole session tagged `model="*"`, so consumers that don't yet read the
    `model` field still see aggregate signals.

    `signals` is empty when nothing fired — a healthy session.
    """
    sess = parse_session(path)
    events = sess.tool_events
    per_tool = per_tool_stats(events)

    signals: list[dict] = []

    # Window-based detectors: per segment.
    for idx, seg in enumerate(model_segments(events)):
        seg_model = seg[0].model if seg else ""
        for sig in (
            detect_generic_repeat(seg)
            + detect_ping_pong(seg)
            + detect_no_progress_poll(seg)
            + detect_short_segment_repeat(seg)
        ):
            sig["model"] = seg_model
            sig["segment_index"] = idx
            signals.append(sig)

    # Whole-session detectors: per model group. When the session is
    # single-model, the per-model bucket equals the whole session, so we
    # tag the signal with `model="*"` to match the back-compat aggregate
    # shape consumers expect — and skip a redundant second pass.
    by_model = group_by_model(events)
    single_model = len(by_model) <= 1
    for model, bucket in by_model.items():
        bucket_per_tool = per_tool_stats(bucket)
        sig_model = AGGREGATE_MODEL if single_model else model
        for sig in (
            detect_token_hotspot(bucket, bucket_per_tool)
            + detect_error_storm(bucket, bucket_per_tool)
        ):
            sig["model"] = sig_model
            signals.append(sig)
    if not single_model:
        for sig in (
            detect_token_hotspot(events, per_tool)
            + detect_error_storm(events, per_tool)
        ):
            sig["model"] = AGGREGATE_MODEL
            signals.append(sig)

    turn_count = sum(
        1 for e in sess.entries
        if e.get("type") == "message" and (e.get("message") or {}).get("role") == "assistant"
    )
    return {
        "session_id": sess.session_id,
        "agent_id": sess.agent_id,
        "model": sess.model,
        "models_used": models_used_sequence(events),
        "turn_count": turn_count,
        "tool_call_count": len(events),
        "total_tokens": sess.total_tokens,
        "per_tool_stats": per_tool,
        "per_model_stats": per_model_stats(events),
        "signals": signals,
    }


def render_text(report: dict) -> str:
    """Render an analyze() report as a 20–40 line human-readable summary.

    Designed to fit one terminal screen: header (session/agent/model/tokens),
    per-tool table sorted by call count, then the firing signals. Use --format
    json instead when piping into other tooling.
    """
    lines = []
    lines.append(f"session  {report['session_id']}")
    lines.append(f"agent    {report['agent_id'] or '<unknown>'}")
    models_used = report.get("models_used") or []
    multi_model = len(set(models_used)) > 1
    if multi_model:
        lines.append(f"models   {' → '.join(models_used)}")
    else:
        lines.append(f"model    {report['model'] or '<unknown>'}")
    lines.append(f"turns    {report['turn_count']}    tool calls {report['tool_call_count']}")
    t = report["total_tokens"]
    lines.append(
        f"tokens   in={t['input']} out={t['output']} cacheR={t['cacheRead']} cacheW={t['cacheWrite']}"
    )
    lines.append("")
    lines.append("per-tool")
    if not report["per_tool_stats"]:
        lines.append("  (no tool calls)")
    for tool, s in sorted(report["per_tool_stats"].items(), key=lambda kv: -kv[1]["calls"]):
        lines.append(
            f"  {tool:<32} calls={s['calls']:<4} errors={s['errors']:<3} "
            f"tokens={s['tokens_attributed']:<8} share={s['token_share']:.0%}"
        )
    if multi_model:
        lines.append("")
        lines.append("per-model")
        for model, s in sorted(
            report.get("per_model_stats", {}).items(),
            key=lambda kv: -kv[1]["tool_calls"],
        ):
            lines.append(
                f"  {model:<32} calls={s['tool_calls']:<4} errors={s['errors']:<3} "
                f"tokens={s['tokens_attributed']:<8} segments={s['segments']}"
            )
    lines.append("")
    sigs = report["signals"]
    lines.append(f"signals ({len(sigs)})")
    if not sigs:
        lines.append("  (none)")
    for sig in sigs:
        tool = sig["tool"]
        if isinstance(tool, list):
            tool = "↔".join(tool)
        model_tag = (
            f" model={sig['model']}"
            if multi_model and sig.get("model") and sig["model"] != AGGREGATE_MODEL
            else ""
        )
        lines.append(
            f"  [{sig['severity']:<8}] {sig['type']:<22} tool={tool}{model_tag} "
            f"count={sig['count']} detail={sig['detail']}"
        )
    return "\n".join(lines)


DESCRIPTION = """\
Read one OpenClaw session JSONL file and report tool-call trajectory health.

The analyzer answers questions you'd otherwise answer by scrolling thousands
of lines: did the agent loop on the same tool, did it ping-pong between two
tools, did one tool quietly burn most of the token budget, did one tool
consistently error out? It runs five deterministic detectors over the session
and prints either a short human-readable summary (default) or a JSON report
suitable for piping into other tooling.

Detectors (warn / crit thresholds in parentheses):
  generic_repeat        same tool + same args, sliding window of 30   (10 / 20)
  ping_pong             A-B-A-B alternation, sliding window of 30     (4 cycles / 8)
  no_progress_poll      same call + same result hash                  (5 / 10)
  short_segment_repeat  tiny model-segment that is entirely identical (warn at 5)
  token_hotspot         one tool dominates input+output token share   (40% / 60%)
  error_storm           isError:true rate for one tool, n>=3          (30% / 50%)

Window-based detectors run per contiguous model-segment; whole-session
detectors (token_hotspot, error_storm) run per model and aggregate. Every
signal carries a `model` field ("*" = whole-session aggregate).

Sessions live at:  ~/.openclaw/agents/<agentId>/sessions/<sessionId>.jsonl
Pass the full path so <agentId> can be derived from it.
"""

EPILOG = """\
examples:
  python3 analyze.py ~/.openclaw/agents/triage-bot/sessions/abc123.jsonl
  python3 analyze.py session.jsonl --format json | jq '.signals'
  for s in ~/.openclaw/agents/*/sessions/*.jsonl; do \\
      python3 analyze.py "$s" --format json | jq -c '{id:.session_id, sigs:(.signals|length)}'; \\
  done

exit codes:
  0  success
  2  path is not a file
"""


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="analyze.py",
        description=DESCRIPTION,
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("path", help="Path to a session .jsonl file (typically under ~/.openclaw/agents/<agentId>/sessions/)")
    p.add_argument("--format", choices=("json", "text"), default="text",
                   help="Output format. text (default) is human-readable; json matches the schema in README.md.")
    args = p.parse_args(argv)

    path = Path(args.path)
    if not path.is_file():
        print(f"error: not a file: {path}", file=sys.stderr)
        return 2

    report = analyze(path)
    if args.format == "json":
        print(json.dumps(report, indent=2))
    else:
        print(render_text(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
