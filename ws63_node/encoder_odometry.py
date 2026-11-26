#!/usr/bin/env python
"""Read four STM32 quadrature counters and optionally publish calibrated ROS odometry."""
from __future__ import print_function

import argparse
import binascii
import json
import math
import sys


BAUD = 115200
MAX_U32 = 0xffffffff
WHEELS = ("left_rear", "right_rear", "right_front", "left_front")
ENCODER_PINS = ("PB6/PB7", "PA0/PA1", "PC8/PC9", "PA11/PA12")
PAIRED_BOARD_FORWARD_SIGNS = (1, -1, -1, 1)
AS_REPORTED = (1, 1, 1, 1)


def parse_sample(frame):
    if not frame.endswith(b"\n") or not frame.startswith((b"$J1ENC1,", b"$J1ENC2,")):
        raise ValueError("missing encoder frame prefix or terminator")
    body, checksum = frame.rstrip(b"\r\n")[1:].rsplit(b"*", 1)
    if len(checksum) != 4 or int(checksum, 16) != binascii.crc_hqx(body, 0xffff):
        raise ValueError("encoder CRC mismatch")
    fields = body.split(b",")[1:]
    if len(fields) != 10 or not all(field.isdigit() for field in fields):
        raise ValueError("invalid encoder fields")
    values = [int(field) for field in fields]
    if max(values) > MAX_U32:
        raise ValueError("encoder field exceeds 32 bits")
    return values[0], values[1], values[2:6], values[6:10]


def difference(new, old):
    return ((new - old + 0x80000000) & MAX_U32) - 0x80000000


def encoder_delta(new, old, signs):
    return [difference(value, previous) * sign for value, previous, sign in zip(new, old, signs)]


def print_sample(sample, signs, channels):
    seq, tick, count, invalid = sample
    counts = encoder_delta(count, (0, 0, 0, 0), signs)
    print(json.dumps({"seq": seq, "stm32_ms32": tick, "counts": dict(zip(channels, counts)),
                      "invalid_transitions": dict(zip(channels, invalid))}))
    sys.stdout.flush()


class WheelOdometry(object):
    def __init__(self, scales, track):
        self.scales = scales
        self.track = track
        self.previous = None
        self.x = self.y = self.yaw = 0.0

    def update(self, sample):
        previous, self.previous = self.previous, sample
        if previous is None:
            return None
        seq, tick, count, invalid = sample
        old_seq, old_tick, old_count, old_invalid = previous
        elapsed = difference(tick, old_tick)
        if not 0 < elapsed <= 1000 or difference(seq, old_seq) <= 0 or invalid != old_invalid:
            raise ValueError("encoder interval could not be integrated (reset, gap, or invalid transition)")
        distances = [difference(new, old) * scale for new, old, scale in zip(count, old_count, self.scales)]
        left = (distances[0] + distances[3]) / 2
        right = (distances[1] + distances[2]) / 2
        travel = (left + right) / 2
        rotation = (right - left) / self.track
        new_yaw = self.yaw + rotation
        if abs(rotation) < 1e-8:
            self.x += travel * math.cos(self.yaw)
            self.y += travel * math.sin(self.yaw)
        else:
            radius = travel / rotation
            self.x += radius * (math.sin(new_yaw) - math.sin(self.yaw))
            self.y += radius * (math.cos(self.yaw) - math.cos(new_yaw))
        self.yaw = math.atan2(math.sin(new_yaw), math.cos(new_yaw))
        dt = elapsed / 1000.0
        return self.x, self.y, self.yaw, travel / dt, rotation / dt


def run_ros(port, args):
    import rospy
    from nav_msgs.msg import Odometry

    rospy.init_node("ws63_wheel_odometry")
    if rospy.get_param("/use_sim_time", False):
        raise ValueError("wheel encoder input requires the Jetson's live ROS clock")
    scales = [math.pi * diameter / ticks * sign for diameter, ticks, sign in
              zip(args.diameters, args.ticks_per_rev, args.signs)]
    odometry = WheelOdometry(scales, args.track)
    publisher = rospy.Publisher(args.topic, Odometry, queue_size=5)
    port.reset_input_buffer()
    while not rospy.is_shutdown():
        frame = port.read_until(size=125)
        if not frame:
            continue
        received = rospy.Time.now()
        try:
            pose = odometry.update(parse_sample(frame))
        except ValueError as error:
            rospy.logwarn_throttle(5, str(error))
            continue
        if pose is None:
            continue
        x, y, yaw, speed, turn_rate = pose
        msg = Odometry()
        # Intervals use the STM32 clock. Estimate the ROS capture time from the wire transfer.
        msg.header.stamp = received - rospy.Duration.from_sec(len(frame) * 10.0 / BAUD)
        msg.header.frame_id = "odom"
        msg.child_frame_id = "base_link"
        msg.pose.pose.position.x, msg.pose.pose.position.y = x, y
        msg.pose.pose.orientation.z, msg.pose.pose.orientation.w = math.sin(yaw / 2), math.cos(yaw / 2)
        msg.twist.twist.linear.x, msg.twist.twist.angular.z = speed, turn_rate
        # Conservative placeholders until measured error statistics are available.
        for index in (0, 7, 35):
            msg.pose.covariance[index] = msg.twist.covariance[index] = 0.25
        for index in (14, 21, 28):
            msg.pose.covariance[index] = msg.twist.covariance[index] = 1e6
        publisher.publish(msg)


def main():
    order = "order: " + ", ".join(WHEELS)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="STM32 serial device; use /dev/serial/by-path")
    parser.add_argument("--ros", action="store_true", help="publish wheel odometry instead of raw encoder JSON")
    parser.add_argument("--query", action="store_true", help="read one calibrated sample from the paired motor firmware")
    parser.add_argument("--topic", default="/wheel/odom")
    parser.add_argument("--diameters", type=float, nargs=4, help="wheel diameters in metres; " + order)
    parser.add_argument("--ticks-per-rev", type=int, nargs=4, help="counts per wheel revolution; " + order)
    parser.add_argument("--signs", type=int, choices=(-1, 1), nargs=4,
                        help="forward polarity; query input order: " + ", ".join(ENCODER_PINS) + "; " + order)
    parser.add_argument("--track", type=float, help="effective track width in metres")
    args = parser.parse_args()
    if args.query and args.ros:
        parser.error("--query and --ros select different firmware interfaces")
    if args.ros and (not args.diameters or not args.ticks_per_rev or not args.signs or args.track is None or
                     not all(0 < value < float("inf") for value in args.diameters + args.ticks_per_rev + [args.track])):
        parser.error("--ros requires measured --diameters, --ticks-per-rev, --signs and --track")
    if args.query:
        from motor_link import MotorClient

        try:
            client = MotorClient(args.port)
            try:
                client.connect()
                reply = client.exchange("ENC")
                frame = reply["encoder_frame"]
                default_signs = AS_REPORTED if frame.startswith(b"$J1ENC2,") else PAIRED_BOARD_FORWARD_SIGNS
                print_sample(parse_sample(frame), args.signs or default_signs, ENCODER_PINS)
            finally:
                client.close()
        except (IOError, RuntimeError, ValueError) as error:
            print(str(error), file=sys.stderr)
            return 1
        return 0
    import serial

    port = serial.Serial(None, BAUD, timeout=0.3, exclusive=True)
    port.port, port.dtr, port.rts = args.port, False, False
    try:
        with port:
            if args.ros:
                run_ros(port, args)
            else:
                while True:
                    try:
                        sample = parse_sample(port.read_until(size=125))
                    except ValueError:
                        continue
                    print_sample(sample, args.signs or AS_REPORTED, WHEELS)
    except KeyboardInterrupt:
        return 0
    except (IOError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
