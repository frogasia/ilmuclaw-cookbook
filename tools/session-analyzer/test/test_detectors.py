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
    pt = per_tool_stats(sess)
    assert detect_generic_repeat(sess) == []
    assert detect_ping_pong(sess) == []
    assert detect_no_progress_poll(sess) == []
    assert detect_token_hotspot(sess, pt) == []
    assert detect_error_storm(sess, pt) == []
