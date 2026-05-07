"""Detector tests: each detector fires on its fixture and stays silent on healthy.jsonl."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from analyze import analyze  # noqa: E402

FIXTURES = ROOT / "fixtures"


def signal_types(report) -> set[str]:
    return {s["type"] for s in report["signals"]}


def signals_of(report, type_: str):
    return [s for s in report["signals"] if s["type"] == type_]


def test_healthy_fires_nothing():
    report = analyze(FIXTURES / "healthy.jsonl")
    assert report["signals"] == [], f"unexpected signals: {report['signals']}"


def test_generic_repeat_fires_on_read_storm():
    report = analyze(FIXTURES / "generic-repeat.jsonl")
    sigs = signals_of(report, "generic_repeat")
    assert sigs, "generic_repeat did not fire on read-storm fixture"
    assert any(s["tool"] == "read" and s["count"] >= 10 for s in sigs)


def test_no_progress_poll_fires_when_results_repeat():
    report = analyze(FIXTURES / "generic-repeat.jsonl")
    sigs = signals_of(report, "no_progress_poll")
    assert sigs, "no_progress_poll did not fire on read-storm fixture"
    assert any(s["tool"] == "read" and s["severity"] == "critical" for s in sigs)


def test_ping_pong_fires_on_alternating_pattern():
    report = analyze(FIXTURES / "ping-pong.jsonl")
    sigs = signals_of(report, "ping_pong")
    assert sigs, "ping_pong did not fire"
    pair = sigs[0]["tool"]
    assert isinstance(pair, list) and set(pair) == {"read", "grep"}
    assert sigs[0]["count"] >= 4


def test_token_hotspot_fires_when_one_tool_dominates():
    report = analyze(FIXTURES / "generic-repeat.jsonl")
    sigs = signals_of(report, "token_hotspot")
    assert sigs, "token_hotspot did not fire on read-storm fixture"
    top = max(sigs, key=lambda s: s["detail"]["share"])
    assert top["tool"] == "read"
    assert top["detail"]["share"] >= 0.40


def test_error_storm_fires_on_high_error_rate():
    report = analyze(FIXTURES / "error-storm.jsonl")
    sigs = signals_of(report, "error_storm")
    assert sigs, "error_storm did not fire"
    s = sigs[0]
    assert s["tool"] == "exec"
    assert s["detail"]["rate"] >= 0.30


def _ev(tool="t", args="a", model="m", entry_id="e", result_hash="r", is_error=False):
    """Build a synthetic ToolEvent — keeps per-model tests free of fixture churn."""
    from analyze import ToolEvent
    return ToolEvent(
        entry_id=entry_id, tool=tool, args_hash=args, result_hash=result_hash,
        is_error=is_error, assistant_input_tokens=0, assistant_output_tokens=0,
        model=model,
    )


def test_model_segments_splits_on_change():
    from analyze import model_segments
    events = [_ev(model="A"), _ev(model="A"), _ev(model="B"), _ev(model="A")]
    segs = model_segments(events)
    assert [s[0].model for s in segs] == ["A", "B", "A"]
    assert [len(s) for s in segs] == [2, 1, 1]


def test_models_used_sequence_dedupes_contiguously():
    from analyze import models_used_sequence
    events = [_ev(model="A"), _ev(model="A"), _ev(model="B"), _ev(model="A")]
    assert models_used_sequence(events) == ["A", "B", "A"]


def test_generic_repeat_fires_on_first_segment_even_when_later_segments_clean():
    """A loop on model A must not be diluted by a clean run on model B.

    Constructed so the last-30 sliding window over the whole event list lands
    entirely inside the clean B tail — the loop is invisible session-wide,
    but the A-segment still has 12 identical reads.
    """
    from analyze import detect_generic_repeat, model_segments
    loop = [_ev(tool="read", args="x", model="A") for _ in range(12)]
    # 31 distinct clean calls so events[-30:] contains no `read` calls.
    clean = [_ev(tool=f"t{i}", args=f"a{i}", model="B") for i in range(31)]
    events = loop + clean
    assert detect_generic_repeat(events) == []
    # Per-segment, the A-segment of 12 identical reads trips warn.
    segs = model_segments(events)
    a_signals = detect_generic_repeat(segs[0])
    assert any(s["tool"] == "read" and s["count"] >= 10 for s in a_signals)


def test_short_segment_repeat_fires_on_six_identical_calls():
    from analyze import detect_short_segment_repeat
    seg = [_ev(tool="read", args="x", model="A") for _ in range(6)]
    sigs = detect_short_segment_repeat(seg)
    assert sigs and sigs[0]["type"] == "short_segment_repeat"
    assert sigs[0]["count"] == 6 and sigs[0]["severity"] == "warning"


def test_short_segment_repeat_silent_on_long_segment():
    """The point of this detector is short segments; defer to generic_repeat past 10."""
    from analyze import detect_short_segment_repeat
    seg = [_ev(tool="read", args="x", model="A") for _ in range(12)]
    assert detect_short_segment_repeat(seg) == []


def test_short_segment_repeat_silent_on_mixed_segment():
    from analyze import detect_short_segment_repeat
    seg = [_ev(tool="read" if i % 2 else "grep", model="A") for i in range(6)]
    assert detect_short_segment_repeat(seg) == []


def test_per_model_stats_counts_segments_and_errors():
    from analyze import per_model_stats
    events = (
        [_ev(model="A", is_error=True)] * 3
        + [_ev(model="B")] * 2
        + [_ev(model="A")] * 4
    )
    stats = per_model_stats(events)
    assert stats["A"]["tool_calls"] == 7
    assert stats["A"]["errors"] == 3
    assert stats["A"]["segments"] == 2  # A appears in two contiguous runs
    assert stats["B"]["segments"] == 1


def test_existing_fixtures_carry_model_field_on_signals():
    """Single-model fixtures must still produce signals — and tag them with `*`."""
    report = analyze(FIXTURES / "generic-repeat.jsonl")
    assert all("model" in s for s in report["signals"]), report["signals"]
    # Single-model session: all whole-session signals collapse onto the aggregate tag.
    hotspots = signals_of(report, "token_hotspot")
    assert hotspots and all(s["model"] == "*" for s in hotspots)
    # Window-based detectors carry the actual model (one segment in single-model fixtures).
    repeats = signals_of(report, "generic_repeat")
    assert repeats and all(s["model"] != "" for s in repeats)
    assert all("segment_index" in s for s in repeats)


def test_models_used_present_in_report():
    report = analyze(FIXTURES / "healthy.jsonl")
    assert "models_used" in report
    assert "per_model_stats" in report


def test_healthy_isolates_per_detector():
    """Sanity: each detector individually returns [] on healthy.jsonl."""
    from analyze import (
        detect_generic_repeat,
        detect_ping_pong,
        detect_no_progress_poll,
        detect_token_hotspot,
        detect_error_storm,
        parse_session,
        per_tool_stats,
    )
    sess = parse_session(FIXTURES / "healthy.jsonl")
    events = sess.tool_events
    pt = per_tool_stats(events)
    assert detect_generic_repeat(events) == []
    assert detect_ping_pong(events) == []
    assert detect_no_progress_poll(events) == []
    assert detect_token_hotspot(events, pt) == []
    assert detect_error_storm(events, pt) == []
