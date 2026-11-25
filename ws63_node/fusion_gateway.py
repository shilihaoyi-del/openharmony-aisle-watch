#!/usr/bin/env python
"""WS63 v1 USB bridge for Jetson and receiver for the SLE payload stream."""
from __future__ import print_function

import argparse
import binascii
from collections import OrderedDict, deque
from copy import copy
import json
import math
import os
import struct
import sys
import threading
import time


MAGIC = b"\xa5\x5a"
MAX_PAYLOAD = 224
MAX_BINS = 72
MAX_FRONT_BINS = 5 * MAX_BINS
SECTOR_GAP = 0.18
SECTORS_PER_SECOND = 5.0
STATIONARY_WINDOW = 7
STATIONARY_MIN_RETURNS = 3
STATIONARY_RANGE_SPAN_MM = 120
SCAN, IMU, ODOM, RESET, REPORT, READY = 1, 2, 3, 4, 0x81, 0x84
REPORT_HEADER = struct.Struct("<BBIIIiiHBB")
CLOCK = getattr(time, "monotonic", time.time)


def encode(kind, payload):
    if len(payload) > MAX_PAYLOAD:
        raise ValueError("oversized payload")
    body = struct.pack("<BB", kind, len(payload)) + payload
    return MAGIC + body + struct.pack("<H", binascii.crc_hqx(body, 0xffff))


class Decoder(object):
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data):
        self.buffer.extend(data)
        while self.buffer:
            start = self.buffer.find(MAGIC)
            if start < 0:
                self.buffer[:] = self.buffer[-1:] if self.buffer[-1] == 0xa5 else b""
                return
            del self.buffer[:start]
            if len(self.buffer) < 4:
                return
            kind, length = self.buffer[2:4]
            if length > MAX_PAYLOAD:
                del self.buffer[0]
                continue
            end = 4 + length
            if len(self.buffer) < end + 2:
                return
            crc = struct.unpack_from("<H", self.buffer, end)[0]
            if crc != binascii.crc_hqx(self.buffer[2:end], 0xffff):
                del self.buffer[0]
                continue
            payload = bytes(self.buffer[4:end])
            del self.buffer[:end + 2]
            yield kind, payload


def source_header(test, stamp):
    return struct.pack("<BI", int(test), stamp & 0xffffffff)


def scan_frame(test, stamp, angle, step, duration, minimum, maximum, ranges):
    count = len(ranges)
    if not 1 <= count <= MAX_BINS:
        raise ValueError("invalid scan bin count")
    payload = struct.pack("<iiHHHB%uH" % count, angle, step, duration, minimum, maximum, count, *ranges)
    return encode(SCAN, source_header(test, stamp) + payload)


def sample_frame(kind, test, stamp, values):
    return encode(kind, source_header(test, stamp) + struct.pack("<%ui" % len(values), *values))


def delta_ms(sample, anchor):
    return ((sample - anchor + 0x80000000) & 0xffffffff) - 0x80000000


def decode_report(payload):
    if len(payload) < REPORT_HEADER.size:
        raise ValueError("short report")
    test, present, seq, stamp, rx, angle, step, duration, count, valid = REPORT_HEADER.unpack_from(payload)
    expected = REPORT_HEADER.size + 2 * count + (28 if present & 1 else 0) + (24 if present & 2 else 0)
    if test > 1 or present > 3 or not 1 <= count <= MAX_BINS or valid > count or len(payload) != expected:
        raise ValueError("invalid report")
    ranges = struct.unpack_from("<%uH" % count, payload, REPORT_HEADER.size)
    report = {
        "test": bool(test), "seq": seq, "scan_stamp_ms32": stamp, "ws63_rx_uptime_ms32": rx,
        "scan_duration_ms": duration, "angle_start_urad": angle, "bucket_width_urad": step,
        "valid_bins": valid, "range_mm": [value or None for value in ranges], "imu": None, "odom": None,
    }
    offset = REPORT_HEADER.size + 2 * count
    if present & 1:
        imu_stamp, ax, ay, az, gx, gy, gz = struct.unpack_from("<I6i", payload, offset)
        report["imu"] = {"offset_ms": delta_ms(imu_stamp, stamp), "accel_mm_s2": [ax, ay, az],
                         "gyro_mrad_s": [gx, gy, gz]}
        offset += 28
    if present & 2:
        odom_stamp, x, y, yaw, v, w = struct.unpack_from("<I5i", payload, offset)
        report["odom"] = {"offset_ms": delta_ms(odom_stamp, stamp), "x_mm": x, "y_mm": y,
                          "yaw_mrad": yaw, "v_mm_s": v, "w_mrad_s": w}
    return report


def handshake(port, decoder, test):
    token = int(time.time() * 1000) & 0xffffffff
    request = source_header(test, token)
    for _ in range(3):
        port.write(encode(RESET, request))
        deadline = CLOCK() + 0.7
        while CLOCK() < deadline:
            for kind, payload in decoder.feed(port.read(port.in_waiting or 1)):
                if kind == READY and payload == request:
                    return
    raise RuntimeError("no Fusion v1 response on the WS63 port")


def fixture():
    """Three-source, near-u32-rollover fixture with damaged and stale records."""
    first = 0xfffffff8
    ranges = (410, 45, 7200) + (900,) * (MAX_BINS - 3)
    good = scan_frame(True, first, -3141593, 87266, 100, 100, 6000, ranges)
    bad = good[:-2] + b"\0\0"
    return b"".join((
        b"boot log\r\n", bad,
        sample_frame(IMU, True, first - 12, (100, 0, 9800, 0, 0, 30)),
        good,
        sample_frame(IMU, True, first + 3, (300, 0, 9800, 0, 0, 50)),
        sample_frame(ODOM, True, first + 12, (10, 20, 30, 40, 50)),
        sample_frame(IMU, False, first + 199, (999,) * 6),
        scan_frame(True, first + 200, -3141593, 87266, 100, 100, 6000, (500,)),
    ))


def verify_fixture(reports):
    if len(reports) != 2:
        raise ValueError("expected two reports, received %d" % len(reports))
    a, b = reports
    if (not a["test"] or not b["test"] or (a["seq"], b["seq"]) != (0, 1) or
            a["scan_stamp_ms32"] != 0xfffffff8 or b["scan_stamp_ms32"] != 192 or
            a["valid_bins"] != 70 or a["range_mm"][:3] != [410, None, None] or
            a["imu"] != {"offset_ms": 3, "accel_mm_s2": [200, 0, 9800], "gyro_mrad_s": [0, 0, 40]} or
            a["odom"] != {"offset_ms": 12, "x_mm": 10, "y_mm": 20, "yaw_mrad": 30, "v_mm_s": 40, "w_mrad_s": 50} or
            b["imu"] is not None or b["odom"] is not None or b["range_mm"] != [500]):
        raise ValueError("Fusion report differs from the fixture expectations")


def self_test(port, decoder):
    handshake(port, decoder, True)
    try:
        port.write(fixture())
        deadline = CLOCK() + 3
        reports = []
        while CLOCK() < deadline:
            for kind, payload in decoder.feed(port.read(port.in_waiting or 1)):
                if kind == REPORT:
                    reports.append(decode_report(payload))
        verify_fixture(reports)
        for report in reports:
            print(json.dumps(report, sort_keys=True))
        print("PASS WS63 Fusion v1 USB", file=sys.stderr)
    finally:
        handshake(port, decoder, False)


def quantize(value):
    return int(round(value * 1000))


def stamp_ms(header):
    if header.stamp.secs == 0 and header.stamp.nsecs == 0:
        raise ValueError("missing ROS capture timestamp")
    return header.stamp.secs * 1000 + header.stamp.nsecs // 1000000


def front_ranges(ranges, angle_min, step, center, width, bins, minimum, maximum):
    """Keep the nearest valid surface in each uniform bin of the front sector."""
    bin_width = width / bins
    start = center - width / 2
    selected = [0] * bins
    for i, distance in enumerate(ranges):
        if not minimum <= distance <= maximum:
            continue
        relative = (angle_min + i * step - start) % (2 * math.pi)
        if relative < width:
            bucket = min(bins - 1, int(relative / bin_width))
            mm = quantize(distance)
            if not selected[bucket] or mm < selected[bucket]:
                selected[bucket] = mm
    return selected, start + bin_width / 2, bin_width


def stationary_ranges(scans, minimum, maximum):
    """Keep the nearest repeatable measurement at each angle of a fixed sensor."""
    ranges = []
    for returns in zip(*scans):
        valid = sorted(quantize(r) for r in returns if minimum <= r <= maximum)
        distance = float("nan")
        for i in range(len(valid) - STATIONARY_MIN_RETURNS + 1):
            nearest = valid[i]
            if valid[i + STATIONARY_MIN_RETURNS - 1] <= nearest + STATIONARY_RANGE_SPAN_MM:
                group = [r for r in valid[i:] if r <= nearest + STATIONARY_RANGE_SPAN_MM]
                distance = group[(len(group) - 1) // 2] / 1000.0
                break
        ranges.append(distance)
    return ranges


class ScanAssembly(object):
    """Collect CRC-checked v1 sectors with the same capture timestamp."""

    def __init__(self, metadata, stamp_ms32, angle, step, duration, ranges):
        self.metadata = metadata
        self.stamp_ms32 = stamp_ms32
        self.step = int(round(step * 1000000))
        self.duration = duration
        self.sectors = OrderedDict()
        self.reports = {}
        for offset in range(0, len(ranges), MAX_BINS):
            sector = ranges[offset:offset + MAX_BINS]
            start = int(round((angle + offset * step) * 1000000))
            self.sectors[start] = len(sector)

    def receive(self, report):
        start = report["angle_start_urad"]
        if (report["scan_stamp_ms32"] != self.stamp_ms32 or report["bucket_width_urad"] != self.step or
                report["scan_duration_ms"] != self.duration or self.sectors.get(start) != len(report["range_mm"])):
            return None
        self.reports[start] = report
        if len(self.reports) != len(self.sectors):
            return None
        complete = dict(self.reports[next(iter(self.sectors))])
        complete["range_mm"] = [value for angle in self.sectors for value in self.reports[angle]["range_mm"]]
        complete["valid_bins"] = sum(value is not None for value in complete["range_mm"])
        return complete


class LinkTrace(object):
    """Bounded observations from the gateway's send and receive serial ports."""

    def __init__(self, max_age_ms):
        self.max_age_ms = max_age_ms or 6000
        self.pending = OrderedDict()
        self.recent = deque(maxlen=6)
        self.sequence = 0
        self.first_complete_capture_ms = None
        self.counts = dict(submitted=0, completed=0, expired=0, startup_expired=0,
                           tx_parts=0, rx_parts=0, tx_bytes=0, rx_bytes=0)

    def begin(self, capture_ms, raw_points, bins, parts):
        key = capture_ms & 0xffffffff
        self.pending[key] = dict(capture_ms=capture_ms, raw_points=raw_points, bins=bins,
                                 segments=parts, tx=[], rx=[], status="pending")
        self.counts["submitted"] += 1

    def sent(self, key, part, size, now_ms):
        frame = self.pending.get(key)
        if frame is not None:
            frame["tx"].append(dict(part=part, bytes=size, at_ms=now_ms))
            self.counts["tx_parts"] += 1
            self.counts["tx_bytes"] += size

    def received(self, key, part, size, now_ms, report, crc):
        frame = self.pending.get(key)
        if frame is not None:
            frame["rx"].append(dict(part=part, bytes=size, at_ms=now_ms, seq=report["seq"],
                                    sender_uptime_ms=report["ws63_rx_uptime_ms32"], crc16="%04X" % crc))
            self.counts["rx_parts"] += 1
            self.counts["rx_bytes"] += size

    def published(self, key, report, now_ms):
        frame = self.pending.pop(key, None)
        if frame is not None:
            if self.first_complete_capture_ms is None:
                self.first_complete_capture_ms = frame["capture_ms"]
            frame.update(status="published", published_ms=now_ms, valid_bins=report["valid_bins"],
                         sample_mm=report["range_mm"][:12])
            self.recent.appendleft(frame)
            self.counts["completed"] += 1

    def snapshot(self, now_ms):
        for key, frame in list(self.pending.items()):
            if now_ms - frame["capture_ms"] > self.max_age_ms:
                self.pending.pop(key)
                frame["status"] = "expired"
                self.recent.appendleft(frame)
                self.counts["expired"] += 1
                if self.first_complete_capture_ms is None or frame["capture_ms"] < self.first_complete_capture_ms:
                    self.counts["startup_expired"] += 1
        self.sequence += 1
        return dict(protocol="SLE SSAP Notification", sender_ready=True, updated_ms=now_ms,
                    update=self.sequence, counts=dict(self.counts), recent=list(self.recent),
                    pending=list(self.pending.values()))


def ros_bridge(port, decoder, args, report_port=None):
    import rospy
    from nav_msgs.msg import Odometry
    from sensor_msgs.msg import Imu, LaserScan
    from std_msgs.msg import String

    rospy.init_node("ws63_fusion_ingress", anonymous=True)
    if rospy.get_param("/use_sim_time", False):
        raise ValueError("live input requires stamped physical sensors on a shared ROS timebase")
    if args.scan_output_topic and rospy.resolve_name(args.scan_output_topic) == rospy.resolve_name(args.scan):
        raise ValueError("reconstructed scan topic must be distinct from the raw scan topic")
    if args.stationary_output_topic and rospy.resolve_name(args.stationary_output_topic) in (
            rospy.resolve_name(args.scan), rospy.resolve_name(args.scan_output_topic)):
        raise ValueError("stationary output requires a distinct topic")
    handshake(port, decoder, False)
    publisher = rospy.Publisher(args.output_topic, String, queue_size=5) if args.output_topic else None
    scan_output = rospy.Publisher(args.scan_output_topic, LaserScan, queue_size=3) if args.scan_output_topic else None
    static_output = (rospy.Publisher(args.stationary_output_topic, LaserScan, queue_size=2)
                     if args.stationary_output_topic else None)
    link_output = rospy.Publisher(args.link_topic, String, queue_size=1, latch=True) if args.link_topic else None
    trace = LinkTrace(args.max_age_ms) if link_output is not None else None
    static_scans = deque(maxlen=STATIONARY_WINDOW)
    static_geometry = None
    last_static_scan = None
    scan_headers = OrderedDict()
    next_scan = [0.0]
    scan_period = 1.0 / args.scan_hz if args.scan_hz else 0
    front_width, front_center = math.radians(args.front_width), math.radians(args.front_center)
    front_frame = args.front_frame if front_width else None
    if front_frame:
        from geometry_msgs.msg import TransformStamped
        from tf2_ros import StaticTransformBroadcaster
        broadcaster = StaticTransformBroadcaster()
        front_transform = TransformStamped()
        front_transform.header.frame_id = front_frame
        front_transform.transform.rotation.z = -math.sin(front_center / 2)
        front_transform.transform.rotation.w = math.cos(front_center / 2)
    lock = threading.Lock()
    closing = threading.Event()

    def submit(encoder, limit_scan=False):
        def callback(message):
            try:
                with lock:
                    now = CLOCK()
                    if closing.is_set() or (limit_scan and now < next_scan[0]):
                        return
                    if not limit_scan:
                        port.write(encoder(message))
                        return
                    capture_ms, bins, frames = encoder(message)
                    key = capture_ms & 0xffffffff
                    port.write(frames[0])
                    if trace is not None:
                        trace.begin(capture_ms, len(message.ranges), bins, len(frames))
                        trace.sent(key, 1, len(frames[0]), int(time.time() * 1000))
                    next_scan[0] = now + scan_period
                for part, frame in enumerate(frames[1:], 2):
                    closing.wait(SECTOR_GAP)
                    with lock:
                        if closing.is_set():
                            return
                        port.write(frame)
                        if trace is not None:
                            trace.sent(key, part, len(frame), int(time.time() * 1000))
            except (ValueError, OverflowError, struct.error) as exc:
                rospy.logwarn_throttle(5, "WS63 input dropped: %s" % exc)
        return callback

    def lidar(msg):
        points = len(msg.ranges)
        if not points or msg.angle_increment == 0:
            raise ValueError("empty scan or zero angle increment")
        duration = (points - 1) * msg.time_increment if msg.time_increment > 0 else msg.scan_time
        duration_ms = quantize(duration)
        near = max(msg.range_min, args.min_range) if args.min_range is not None else msg.range_min
        far = min(msg.range_max, args.max_range) if args.max_range is not None else msg.range_max
        minimum, maximum = quantize(near), min(65535, quantize(far))
        if not 0 <= minimum <= maximum or not 0 <= duration_ms <= 65535:
            raise ValueError("invalid scan metadata")
        midpoint_ms = stamp_ms(msg.header) + duration_ms // 2
        angle, step = msg.angle_min, msg.angle_increment
        if front_width:
            ranges, angle, step = front_ranges(msg.ranges, angle, step, front_center, front_width,
                                              args.bins, near, far)
            if not any(ranges):
                raise ValueError("no valid returns in the front sector")
        else:
            stride = (points + args.bins - 1) // args.bins
            ranges = []
            for start in range(0, points, stride):
                values = [r for r in msg.ranges[start:start + stride] if near <= r <= far]
                ranges.append(min(maximum, quantize(min(values))) if values else 0)
            step *= stride
        if scan_output is not None:
            # Store scan geometry only. The scan published for SLAM uses the ranges returned over SLE.
            stamp = msg.header.stamp
            if front_width:
                # These pooled bins have no individual acquisition times. Use a common midpoint.
                stamp += rospy.Duration.from_sec(duration / 2)
            stamp_ms32 = midpoint_ms & 0xffffffff
            metadata = (stamp, msg.header.frame_id, msg.scan_time, msg.angle_increment,
                        minimum / 1000.0, maximum / 1000.0)
            scan_headers[stamp_ms32] = ScanAssembly(metadata, stamp_ms32, angle, step, duration_ms, ranges)
            if len(scan_headers) > 128:
                scan_headers.popitem(last=False)
        frames = [scan_frame(False, midpoint_ms, int(round((angle + offset * step) * 1000000)),
                           int(round(step * 1000000)), duration_ms, minimum, maximum,
                           ranges[offset:offset + MAX_BINS])
                for offset in range(0, len(ranges), MAX_BINS)]
        return midpoint_ms, len(ranges), frames

    def imu(msg):
        if msg.linear_acceleration_covariance[0] < 0 or msg.angular_velocity_covariance[0] < 0:
            raise ValueError("IMU must supply both linear acceleration and angular velocity")
        vectors = (msg.linear_acceleration, msg.angular_velocity)
        values = [quantize(value) for vector in vectors for value in (vector.x, vector.y, vector.z)]
        return sample_frame(IMU, False, stamp_ms(msg.header), values)

    def odometry(msg):
        pose, twist = msg.pose.pose, msg.twist.twist
        q = pose.orientation
        norm = q.w * q.w + q.x * q.x + q.y * q.y + q.z * q.z
        if not 0.99 < norm < 1.01:
            raise ValueError("invalid odometry orientation")
        yaw = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
        values = [quantize(value) for value in (pose.position.x, pose.position.y, yaw, twist.linear.x, twist.angular.z)]
        return sample_frame(ODOM, False, stamp_ms(msg.header), values)

    subscriptions = [rospy.Subscriber(args.scan, LaserScan, submit(lidar, limit_scan=True), queue_size=2)]
    if args.imu:
        subscriptions.append(rospy.Subscriber(args.imu, Imu, submit(imu), queue_size=10))
    if args.odom:
        subscriptions.append(rospy.Subscriber(args.odom, Odometry, submit(odometry), queue_size=10))
    try:
        report_port = report_port if report_port is not None else port
        report_decoder = Decoder() if report_port is not port else decoder
        next_link_snapshot = 0
        while not rospy.is_shutdown():
            if report_port is not port and port.in_waiting:
                port.read(port.in_waiting)
            for kind, payload in report_decoder.feed(report_port.read(report_port.in_waiting or 1)):
                if kind == REPORT:
                    report = decode_report(payload)
                    if not report["test"]:
                        now_ms = int(time.time() * 1000)
                        capture_age = delta_ms(now_ms, report["scan_stamp_ms32"])
                        if args.max_age_ms and not 0 <= capture_age <= args.max_age_ms:
                            rospy.logwarn_throttle(5, "WS63 stale report dropped (%d ms)" % capture_age)
                            continue
                        metadata = None
                        if scan_output is not None:
                            with lock:
                                capture = report["scan_stamp_ms32"]
                                pending = scan_headers.get(capture)
                                if pending is not None:
                                    before = len(pending.reports)
                                    complete = pending.receive(report)
                                    if trace is not None and len(pending.reports) > before:
                                        part = list(pending.sectors).index(report["angle_start_urad"]) + 1
                                        crc = binascii.crc_hqx(struct.pack("<BB", kind, len(payload)) + payload, 0xffff)
                                        trace.received(capture, part, len(payload) + 6, now_ms, report, crc)
                                    if complete is None:
                                        continue
                                    del scan_headers[capture]
                                    metadata = pending.metadata
                                    report = complete
                                elif args.bins > MAX_BINS:
                                    continue
                        report["capture_age_ms"] = capture_age
                        report["transport"] = "sle" if report_port is not port else "usb"
                        line = json.dumps(report)
                        print(line)
                        sys.stdout.flush()
                        if publisher is not None:
                            publisher.publish(String(data=line))
                        if metadata is not None:
                            stamp, frame_id, scan_time, raw_step, minimum, maximum = metadata
                            reconstructed = LaserScan()
                            reconstructed.header.stamp = stamp
                            if front_frame and (not frame_id or frame_id == front_frame):
                                rospy.logwarn_throttle(5, "WS63 front-frame output requires a distinct raw laser frame")
                                continue
                            if front_frame and frame_id != front_transform.child_frame_id:
                                front_transform.header.stamp = stamp
                                front_transform.child_frame_id = frame_id
                                broadcaster.sendTransform(front_transform)
                            reconstructed.header.frame_id = front_frame or frame_id
                            reconstructed.header.seq = report["seq"]
                            reconstructed.angle_increment = report["bucket_width_urad"] / 1000000.0
                            center_shift = 0 if front_width else (reconstructed.angle_increment - raw_step) / 2
                            if front_frame:
                                center_shift = -front_center
                            reconstructed.angle_min = report["angle_start_urad"] / 1000000.0 + center_shift
                            reconstructed.scan_time = scan_time
                            reconstructed.range_min = minimum
                            reconstructed.range_max = min(maximum, 65.535)
                            missing = float("nan") if front_width else float("inf")
                            reconstructed.ranges = [missing if mm is None else mm / 1000.0
                                                    for mm in report["range_mm"]]
                            reconstructed.angle_max = (reconstructed.angle_min + reconstructed.angle_increment *
                                                       (len(reconstructed.ranges) - 1))
                            scan_output.publish(reconstructed)
                            if trace is not None:
                                with lock:
                                    trace.published(capture, report, int(time.time() * 1000))
                            if static_output is not None:
                                geometry = (reconstructed.header.frame_id, reconstructed.angle_min,
                                            reconstructed.angle_increment, reconstructed.range_min,
                                            reconstructed.range_max, len(reconstructed.ranges))
                                if (static_geometry != geometry or last_static_scan is None or
                                        not 0 < (stamp - last_static_scan).to_sec() <= 3):
                                    static_scans.clear()
                                    static_geometry = geometry
                                last_static_scan = stamp
                                static_scans.append(reconstructed.ranges)
                                if len(static_scans) == STATIONARY_WINDOW:
                                    stationary = copy(reconstructed)
                                    stationary.header = copy(reconstructed.header)
                                    stationary.ranges = stationary_ranges(list(static_scans),
                                                                          stationary.range_min, stationary.range_max)
                                    if any(stationary.range_min <= r <= stationary.range_max for r in stationary.ranges):
                                        static_output.publish(stationary)
            if link_output is not None and CLOCK() >= next_link_snapshot:
                with lock:
                    data = json.dumps(trace.snapshot(int(time.time() * 1000)), separators=(",", ":"))
                link_output.publish(String(data=data))
                next_link_snapshot = CLOCK() + .4
    finally:
        with lock:
            closing.set()
        for subscription in subscriptions:
            subscription.unregister()


def open_port(serial, path):
    port = serial.Serial(None, 115200, timeout=0.05, write_timeout=1, exclusive=True)
    port.port, port.dtr, port.rts = path, False, False
    return port


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="/dev/ws63-contact")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true", help="verify simulated sensor input over real WS63 USB")
    mode.add_argument("--ros", action="store_true", help="send physically sourced ROS messages to the WS63")
    mode.add_argument("--monitor", action="store_true", help="read reports from a USB-connected SLE receiver")
    parser.add_argument("--scan", default="/scan")
    parser.add_argument("--imu", help="optional sensor_msgs/Imu topic")
    parser.add_argument("--odom", help="optional nav_msgs/Odometry topic sourced from wheel encoders")
    parser.add_argument("--receive-port", help="SLE receiver USB serial device (with --ros)")
    parser.add_argument("--output-topic", help="publish decoded telemetry as std_msgs/String (with --ros)")
    parser.add_argument("--scan-output-topic", help="publish a LaserScan from SLE reports (requires --receive-port)")
    parser.add_argument("--stationary-output-topic", help="publish repeatable SLE returns from a fixed lidar only")
    parser.add_argument("--link-topic", help="publish measured SLE transport events as JSON")
    parser.add_argument("--scan-hz", type=float, help="maximum scan submission rate (default: SLE 4 Hz, lower for split sectors; USB uncapped)")
    parser.add_argument("--bins", type=int, default=MAX_BINS, help="maximum number of angular bins")
    parser.add_argument("--front-center", type=float, default=0, help="forward direction in the raw laser frame, degrees")
    parser.add_argument("--front-width", type=float, default=0, help="front sector width in degrees (0 keeps the entire scan)")
    parser.add_argument("--front-frame", help="publish the cropped scan in a distinct frame with +X pointing forward")
    parser.add_argument("--min-range", type=float, help="reject closer returns in metres")
    parser.add_argument("--max-range", type=float, help="reject farther returns in metres")
    parser.add_argument("--max-age-ms", type=int, help="drop late reports (default: SLE 1000 ms plus allowance for dense scans; USB disabled)")
    args = parser.parse_args()
    if args.receive_port and (not args.ros or os.path.realpath(args.receive_port) == os.path.realpath(args.port)):
        parser.error("--receive-port requires --ros and a distinct receiver port")
    if args.output_topic and not args.ros:
        parser.error("--output-topic requires --ros")
    if args.scan_output_topic and not args.receive_port:
        parser.error("--scan-output-topic requires --receive-port")
    if args.stationary_output_topic and not args.scan_output_topic:
        parser.error("--stationary-output-topic requires --scan-output-topic")
    if args.link_topic and not args.scan_output_topic:
        parser.error("--link-topic requires --scan-output-topic")
    if args.front_frame and not args.scan_output_topic:
        parser.error("--front-frame requires --scan-output-topic")
    parts = (args.bins + MAX_BINS - 1) // MAX_BINS
    if args.scan_hz is None:
        args.scan_hz = SECTORS_PER_SECOND / parts if parts > 1 else (4 if args.receive_port else 0)
    if args.max_age_ms is None:
        args.max_age_ms = 1000 + 200 * max(0, parts - 2) if args.receive_port else 0
    bin_limit = MAX_FRONT_BINS if args.front_width and args.scan_output_topic else MAX_BINS
    if not 0 <= args.scan_hz < float("inf") or args.max_age_ms < 0 or not 1 <= args.bins <= bin_limit:
        parser.error("invalid scan rate, report age, or bin count")
    if (not -180 <= args.front_center <= 180 or not 0 <= args.front_width < 360 or
            any(v is not None and not 0 < v <= 65.535 for v in (args.min_range, args.max_range)) or
            args.min_range is not None and args.max_range is not None and args.min_range >= args.max_range):
        parser.error("invalid front sector or range bounds")
    import serial

    decoder = Decoder()
    try:
        with open_port(serial, args.port) as port:
            if args.self_test:
                self_test(port, decoder)
            elif args.ros:
                if args.receive_port:
                    with open_port(serial, args.receive_port) as report_port:
                        ros_bridge(port, decoder, args, report_port=report_port)
                else:
                    ros_bridge(port, decoder, args)
            else:
                while True:
                    for kind, payload in decoder.feed(port.read(port.in_waiting or 1)):
                        if kind == REPORT:
                            print(json.dumps(decode_report(payload)))
                            sys.stdout.flush()
    except KeyboardInterrupt:
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
