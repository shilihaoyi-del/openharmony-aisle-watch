#!/usr/bin/env python
"""Forward fixed-pose laser scans and display decisions made on the WS63 sender."""
from __future__ import print_function

import argparse
from collections import deque
import json
import math
import os
import struct
import sys
import tempfile
import threading
import time

from fusion_gateway import (CLOCK, Decoder, MAX_BINS, delta_ms, encode, front_ranges,
                            handshake, open_port, quantize, scan_frame, source_header, stamp_ms)

CONFIG, REPORT, READY = 5, 0x82, 0x85
HEADER = struct.Struct("<BBBB6I7B")
STATES = ("calibrating", "clear", "occupied", "unknown")
EVENTS = ("heartbeat", "baseline", "intrusion", "restored", "blind")
FULL_REPORT_BYTES = 176


def decode_change(payload):
    if len(payload) < HEADER.size:
        raise ValueError("short change report")
    (test, kind, state, fresh, session, seq, event_id, stamp, uptime, scans,
     valid_baseline, observed, roi_first, roi_count, first, count, samples) = HEADER.unpack_from(payload)
    if (test > 1 or kind >= len(EVENTS) or state >= len(STATES) or fresh > 1 or
            roi_count < 3 or roi_first + roi_count > MAX_BINS or observed > valid_baseline or
            valid_baseline > roi_count or samples != min(count, 16) or
            (count and (first < roi_first or first + count > roi_first + roi_count)) or
            (not kind and count) or len(payload) != HEADER.size + 4 * samples):
        raise ValueError("invalid change report")
    evidence = [struct.unpack_from("<HH", payload, HEADER.size + 4 * i) for i in range(samples)]
    return dict(test=bool(test), kind=EVENTS[kind], state=STATES[state], fresh=bool(fresh), session=session,
                seq=seq, event_id=event_id, capture_ms=stamp, uptime_ms=uptime, scans=scans,
                valid_baseline=valid_baseline, observed=observed, roi_first=roi_first, roi_count=roi_count,
                first=first, count=count, evidence_mm=evidence)


class WatchStream(object):
    def __init__(self, session, detect_range=None):
        self.session = session
        self.detect_range = detect_range
        self.events = deque(maxlen=16)
        self.latest = None
        self.last_event_id = 0
        self.received_bytes = 0
        self.received_reports = 0
        self.missing_reports = 0
        self.latest_at = None

    def accept(self, payload, now):
        report = decode_change(payload)
        if report["test"] or report["session"] != self.session:
            return None
        if self.latest is not None:
            step = delta_ms(report["seq"], self.latest["seq"])
            if step <= 0:
                return None
            self.missing_reports += step - 1
        self.received_reports += 1
        self.received_bytes += len(payload) + 6
        self.latest = report
        self.latest_at = now
        if report["kind"] != "heartbeat" and delta_ms(report["event_id"], self.last_event_id) > 0:
            self.last_event_id = report["event_id"]
            event = dict(report, arrived_at=now)
            age = delta_ms(int(now * 1000), report["capture_ms"])
            event["capture_age_ms"] = age if report["fresh"] and 0 <= age <= 5000 else None
            self.events.appendleft(event)
            return event
        return None

    def snapshot(self, width, running, stage, sent, error=None):
        return dict(running=running, stage=stage, error=error, latest=self.latest, latest_at=self.latest_at,
                    events=list(self.events), received_bytes=self.received_bytes, received_reports=self.received_reports,
                    missing_reports=self.missing_reports, sent_scans=sent, width_deg=width,
                    detect_range_m=self.detect_range,
                    same_rate_full_bytes=self.latest["scans"] * FULL_REPORT_BYTES if self.latest else 0)


def configure(port, decoder, session, first, count, detect_range=None):
    body = source_header(False, session) + struct.pack("<BB", first, count)
    if detect_range is not None:
        body += struct.pack("<H", quantize(detect_range))
    for _ in range(4):
        port.write(encode(CONFIG, body))
        deadline = CLOCK() + .75
        while CLOCK() < deadline:
            for kind, data in decoder.feed(port.read(port.in_waiting or 1)):
                if kind == READY and data == body:
                    return
    raise RuntimeError("WS63 sender did not acknowledge the monitor settings. Check the sender firmware version.")


def write_snapshot(path, state):
    with tempfile.NamedTemporaryFile(mode="w", dir=os.path.dirname(os.path.abspath(path)), delete=False) as output:
        temp = output.name
        try:
            json.dump(state, output, separators=(",", ":"))
            output.flush()
            os.rename(temp, path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)


def run(args):
    import rospy
    import serial
    from sensor_msgs.msg import LaserScan
    from std_msgs.msg import String

    rospy.init_node("ws63_change_probe", anonymous=True)
    if rospy.get_param("/use_sim_time", False):
        raise ValueError("watch needs a fixed sensor with real capture timestamps")
    session = int(time.time() * 1000) & 0xffffffff
    stream = WatchStream(session, args.detect_range)
    sent = [0]
    next_scan = [0.0]
    closing = threading.Event()
    send_lock = threading.Lock()
    event_topic = rospy.Publisher("/ws63/change_events", String, queue_size=8)
    state_topic = rospy.Publisher("/ws63/change", String, queue_size=1, latch=True)
    error = None
    try:
        write_snapshot(args.output, stream.snapshot(args.width, True, "sender", 0))
        with open_port(serial, args.port) as sender, open_port(serial, args.receive_port) as receiver:
            uart = Decoder()
            handshake(sender, uart, False)
            configure(sender, uart, session, args.roi_first, args.roi_count, args.detect_range)
            width, center = math.radians(args.width), math.radians(args.center)

            def scan(message):
                with send_lock:
                    if closing.is_set() or CLOCK() < next_scan[0] or not message.ranges or message.angle_increment == 0:
                        return
                    try:
                        duration = (len(message.ranges) - 1) * message.time_increment if message.time_increment > 0 else message.scan_time
                        duration_ms = quantize(duration)
                        stamp = stamp_ms(message.header) + duration_ms // 2
                        near, far = max(message.range_min, args.near), min(message.range_max, args.far)
                        if near >= far or not 0 <= duration_ms <= 65535:
                            return
                        ranges, angle, step = front_ranges(message.ranges, message.angle_min, message.angle_increment,
                                                           center, width, MAX_BINS, near, far)
                        sender.write(scan_frame(False, stamp, int(round(angle * 1e6)), int(round(step * 1e6)),
                                                duration_ms, quantize(near), quantize(far), ranges))
                        sent[0] += 1
                        next_scan[0] = CLOCK() + .25
                    except (ValueError, OverflowError, IOError, OSError, struct.error) as exc:
                        rospy.logwarn_throttle(4, "WS63 monitor scan: %s" % exc)

            subscription = rospy.Subscriber("/scan", LaserScan, scan, queue_size=1)
            decoder = Decoder()
            ready = False
            next_snapshot = 0.0
            try:
                while not rospy.is_shutdown():
                    if sender.in_waiting:
                        sender.read(sender.in_waiting)
                    for kind, payload in decoder.feed(receiver.read(receiver.in_waiting or 1)):
                        if kind != REPORT:
                            continue
                        try:
                            event = stream.accept(payload, time.time())
                        except ValueError:
                            continue
                        if event:
                            line = json.dumps(event, separators=(",", ":"))
                            print(line)
                            sys.stdout.flush()
                            event_topic.publish(String(data=line))
                    if not ready and stream.latest:
                        with open(args.ready_file, "w") as out:
                            out.write(str(session) + "\n")
                        ready = True
                    if CLOCK() >= next_snapshot:
                        stage = "monitoring" if ready else "receiver"
                        state = stream.snapshot(args.width, True, stage, sent[0])
                        write_snapshot(args.output, state)
                        state_topic.publish(String(data=json.dumps(state, separators=(",", ":"))))
                        next_snapshot = CLOCK() + .4
            finally:
                with send_lock:
                    closing.set()
                subscription.unregister()
    except (RuntimeError, ValueError, IOError, OSError) as exc:
        error = str(exc)
        raise
    finally:
        write_snapshot(args.output, stream.snapshot(args.width, False, "stopped", sent[0], error))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="/dev/ws63-contact")
    parser.add_argument("--receive-port", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--ready-file", required=True)
    parser.add_argument("--center", type=float, default=175)
    parser.add_argument("--width", type=float, default=110)
    parser.add_argument("--near", type=float, default=.4)
    parser.add_argument("--far", type=float, default=10)
    parser.add_argument("--detect-range", type=float, help="maximum obstacle distance in metres with stable sender firmware")
    parser.add_argument("--roi-first", type=int, default=12)
    parser.add_argument("--roi-count", type=int, default=48)
    args = parser.parse_args()
    if (not -180 <= args.center <= 180 or not 0 < args.width < 360 or not 0 < args.near < args.far <= 65.535 or
            (args.detect_range is not None and not args.near < args.detect_range <= args.far) or
            not 3 <= args.roi_count <= MAX_BINS or not 0 <= args.roi_first <= MAX_BINS - args.roi_count or
            os.path.realpath(args.port) == os.path.realpath(args.receive_port)):
        parser.error("invalid sector, range, monitoring zone or serial ports")
    try:
        run(args)
    except (RuntimeError, ValueError, IOError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
