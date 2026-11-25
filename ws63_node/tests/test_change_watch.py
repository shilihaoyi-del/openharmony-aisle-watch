"""Replay synthetic fixtures through the production sender C and gateway parser."""

import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from change_gateway import CONFIG, REPORT, READY, WatchStream, decode_change
from fusion_gateway import Decoder, RESET, encode, scan_frame, source_header


def main():
    trace = []
    now = 0
    capture = 0xffffff00
    accepted = 0
    session = 1234
    baseline = [2000] * 72
    # An angle which is unobservable during baseline must stay outside the reference.
    baseline[16] = 0
    baseline[20:28] = [9000] * 8
    near = baseline.copy()
    near[30:38] = [900] * 8
    moved = baseline.copy()
    moved[48:56] = [1200] * 8
    missing = baseline.copy()
    missing[48:56] = [0] * 8

    def step(frame=b"", elapsed=250):
        nonlocal now
        now += elapsed
        trace.append(struct.pack("<IH", now, len(frame)) + frame)
        return now

    def scan(ranges, elapsed=250, capture_change=250):
        nonlocal capture, accepted
        capture += capture_change
        accepted += capture_change > 0
        return step(scan_frame(False, capture, 1, 26665, 100, 400, 10000, ranges), elapsed)

    step(encode(RESET, source_header(False, session)))
    scan(baseline)
    step(elapsed=100)
    legacy_config = source_header(False, session) + struct.pack("<BB", 12, 48)
    config = legacy_config + struct.pack("<H", 2500)
    step(encode(CONFIG, legacy_config))
    step(encode(CONFIG, config))
    outlier = baseline.copy()
    outlier[22] = 700
    scan(outlier)
    for _ in range(6):
        scan(baseline)
    for distance in (7700, 2800):
        far_change = baseline.copy()
        far_change[20:28] = [distance] * 8
        for _ in range(5):
            scan(far_change)
    for first in (28, 30, 32, 34):
        moving_noise = baseline.copy()
        moving_noise[first:first + 3] = [1300] * 3
        scan(moving_noise)
    scan(baseline)
    scan(near)
    scan(near)
    scan(baseline)
    scan(near)
    scan(near, capture_change=0)
    scan(near)
    confirmed = scan(near)
    for _ in range(8):
        scan(near)
    for _ in range(5):
        scan(moved)
    for _ in range(4):
        scan(missing)
    for _ in range(3):
        scan(baseline)
    stale = step(elapsed=1600)
    isolated_miss = baseline.copy()
    isolated_miss[22] = 0
    for _ in range(3):
        scan(isolated_miss)
    for first in (28, 34, 40):
        crossing = baseline.copy()
        crossing[first:first + 8] = [1300] * 8
        crossed = scan(crossing)
    partial_recovery = baseline.copy()
    partial_recovery[41] = 0
    partial_recovery[43] = 2400
    for _ in range(3):
        scan(partial_recovery)

    with tempfile.TemporaryDirectory() as temp:
        executable = Path(temp) / "watch-replay"
        subprocess.run([os.environ.get("CC", "cc"), "-std=c99", "-Wall", "-Wextra", "-Werror",
                        "-I", str(ROOT), "-o", str(executable), str(ROOT / "tests/watch_harness.c"),
                        str(ROOT / "fusion.c"), str(ROOT / "change_watch.c")], check=True)
        result = subprocess.run([str(executable)], input=b"".join(trace), stdout=subprocess.PIPE, check=True)

    frames = list(Decoder().feed(result.stdout))
    assert [kind for kind, _ in frames[:4]] == [0x84, 0x81, READY, READY], frames[:4]
    assert frames[2][1] == legacy_config and frames[3][1] == config
    assert all(kind == REPORT for kind, _ in frames[4:])
    stream = WatchStream(session)
    events = []
    payloads = [payload for _, payload in frames[4:]]
    reports = [decode_change(payload) for payload in payloads]
    for payload in payloads:
        report = decode_change(payload)
        event = stream.accept(payload, report["uptime_ms"] / 1000.0)
        if event:
            events.append(event)
    assert [event["kind"] for event in events] == [
        "baseline", "intrusion", "blind", "restored", "blind", "restored", "intrusion", "restored",
    ], events
    assert events[0]["valid_baseline"] == 47
    assert events[1]["uptime_ms"] == confirmed
    repeats = [r for r in reports if r["event_id"] == events[1]["event_id"] and r["kind"] == "intrusion"]
    assert len(repeats) == 3 and all(r["capture_ms"] == events[1]["capture_ms"] for r in repeats)
    assert events[1]["first"] == 30 and events[1]["evidence_mm"] == [(2000, 900)] * 8
    assert events[2]["first"] == 48
    assert all(after == 0 for _, after in events[2]["evidence_mm"])
    assert events[4]["uptime_ms"] == stale and not events[4]["fresh"]
    assert events[6]["uptime_ms"] == crossed and events[6]["first"] == 40
    assert stream.latest["scans"] == accepted - 1, stream.latest
    assert stream.missing_reports == 0
    assert stream.accept(payloads[-1], now / 1000.0) is None
    state = stream.snapshot(110, True, "monitoring", 31)
    print("PASS legacy/configurable range, far returns, moving noise, moving obstacle, evidence, visibility and recovery")
    print("Replay application bytes: %d received vs %d full-scan equivalent over %d scans" %
          (state["received_bytes"], state["same_rate_full_bytes"], state["latest"]["scans"]))


if __name__ == "__main__":
    main()
