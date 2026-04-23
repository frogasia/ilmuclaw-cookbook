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


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


@dataclass
class ToolEvent:
    """A single tool call with its paired result (when available)."""
    entry_id: str
    tool: str
    args_hash: str
    result_hash: str | None  # None when result missing or all ImageContent
    is_error: bool
    assistant_input_tokens: int
    assistant_output_tokens: int


@dataclass
class Session:
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
    """Parse JSONL; tolerate malformed lines (mirrors pi-mono's parser)."""
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
    for e in entries:
        if e.get("type") != "message":
            continue
        msg = e.get("message", {})
        if msg.get("role") != "assistant":
            continue
        usage = msg.get("usage") or {}
        _accumulate_tokens(sess.total_tokens, usage)
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

def detect_generic_repeat(sess: Session) -> list[dict]:
    events = sess.tool_events[-WINDOW:] if len(sess.tool_events) > WINDOW else sess.tool_events
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


def detect_ping_pong(sess: Session) -> list[dict]:
    events = sess.tool_events[-WINDOW:] if len(sess.tool_events) > WINDOW else sess.tool_events
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


def detect_no_progress_poll(sess: Session) -> list[dict]:
    events = [ev for ev in sess.tool_events if ev.result_hash is not None]
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


def detect_token_hotspot(sess: Session, per_tool: dict) -> list[dict]:
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


def detect_error_storm(sess: Session, per_tool: dict) -> list[dict]:
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


def per_tool_stats(sess: Session) -> dict:
    stats: dict[str, dict] = {}
    for ev in sess.tool_events:
        s = stats.setdefault(ev.tool, {"calls": 0, "errors": 0, "tokens_attributed": 0, "token_share": 0.0})
        s["calls"] += 1
        if ev.is_error:
            s["errors"] += 1
        s["tokens_attributed"] += ev.assistant_input_tokens + ev.assistant_output_tokens
    total = sum(s["tokens_attributed"] for s in stats.values()) or 1
    for s in stats.values():
        s["token_share"] = round(s["tokens_attributed"] / total, 3)
    return stats


def analyze(path: Path) -> dict:
    sess = parse_session(path)
    per_tool = per_tool_stats(sess)
    signals = (
        detect_generic_repeat(sess)
        + detect_ping_pong(sess)
        + detect_no_progress_poll(sess)
        + detect_token_hotspot(sess, per_tool)
        + detect_error_storm(sess, per_tool)
    )
    turn_count = sum(
        1 for e in sess.entries
        if e.get("type") == "message" and (e.get("message") or {}).get("role") == "assistant"
    )
    return {
        "session_id": sess.session_id,
        "agent_id": sess.agent_id,
        "model": sess.model,
        "turn_count": turn_count,
        "tool_call_count": len(sess.tool_events),
        "total_tokens": sess.total_tokens,
        "per_tool_stats": per_tool,
        "signals": signals,
    }


def render_text(report: dict) -> str:
    lines = []
    lines.append(f"session  {report['session_id']}")
    lines.append(f"agent    {report['agent_id'] or '<unknown>'}")
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
    lines.append("")
    sigs = report["signals"]
    lines.append(f"signals ({len(sigs)})")
    if not sigs:
        lines.append("  (none)")
    for sig in sigs:
        tool = sig["tool"]
        if isinstance(tool, list):
            tool = "↔".join(tool)
        lines.append(
            f"  [{sig['severity']:<8}] {sig['type']:<18} tool={tool} "
            f"count={sig['count']} detail={sig['detail']}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Analyze an OpenClaw session JSONL for tool-call trajectory signals.",
    )
    p.add_argument("path", help="Path to a session .jsonl file")
    p.add_argument("--format", choices=("json", "text"), default="text",
                   help="Output format (default: text)")
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
