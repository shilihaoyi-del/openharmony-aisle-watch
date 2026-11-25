#!/usr/bin/env python
"""Collect SLAM state from the Jetson ROS graph for the local display."""
from __future__ import print_function

import argparse
import base64
from collections import OrderedDict, deque
import hashlib
import json
import math
import os
import tempfile
import threading
import time

try:
    from io import BytesIO
except ImportError:
    from StringIO import StringIO as BytesIO

from PIL import Image
import rospy
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import OccupancyGrid
from sensor_msgs.msg import LaserScan
from std_msgs.msg import String


PALETTE = [(17, 27, 34), (34, 57, 62), (101, 129, 116), (214, 232, 214)]


def stamp_key(header):
    return header.stamp.to_nsec()


def yaw(rotation):
    return math.atan2(2 * (rotation.w * rotation.z + rotation.x * rotation.y),
                      1 - 2 * (rotation.y * rotation.y + rotation.z * rotation.z))


OCCUPANCY_COLORS = [0 if value == 255 else 1 if value <= 25 else 3 if value >= 65 else 2 for value in range(256)]


def map_snapshot(message):
    info = message.info
    if not info.width or not info.height:
        return None
    raster = bytes(bytearray(value & 255 for value in message.data))
    image = Image.frombytes("L", (info.width, info.height), raster)
    blank_mask = image.point([255] * 101 + [0] * 155)
    bounds = blank_mask.getbbox()
    if bounds is None:
        return None
    padding = 3
    left = max(0, bounds[0] - padding)
    bottom = max(0, bounds[1] - padding)
    right = min(info.width, bounds[2] + padding)
    top = min(info.height, bounds[3] + padding)
    colors = image.crop((left, bottom, right, top)).point(OCCUPANCY_COLORS)
    histogram = colors.histogram()
    colors = colors.transpose(Image.FLIP_TOP_BOTTOM)
    colors.putpalette(tuple(component for entry in PALETTE for component in entry) + (0,) * 756)
    png = BytesIO()
    colors.save(png, format="PNG", bits=2)
    content = png.getvalue()
    orientation = yaw(info.origin.orientation)
    dx, dy = left * info.resolution, bottom * info.resolution
    return {
        "id": hashlib.sha256(content).hexdigest()[:16], "png": base64.b64encode(content).decode("ascii"),
        "width": right - left, "height": top - bottom, "resolution": info.resolution,
        "x": info.origin.position.x + dx * math.cos(orientation) - dy * math.sin(orientation),
        "y": info.origin.position.y + dx * math.sin(orientation) + dy * math.cos(orientation),
        "yaw": orientation, "frame": message.header.frame_id,
        "known": sum(histogram[1:4]), "occupied": histogram[3],
    }


def fit_wall_segments(points):
    if len(points) < 6:
        return []
    x0, y0 = points[0]
    x1, y1 = points[-1]
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy)
    if length < 0.45:
        return []
    deviation, split = max((abs(dx * (y - y0) - dy * (x - x0)) / length, i)
                           for i, (x, y) in enumerate(points[1:-1], 1))
    if deviation > 0.08:
        return fit_wall_segments(points[:split + 1]) + fit_wall_segments(points[split:])
    return [[points[0], points[-1]]]


def scan_geometry(scan, pose):
    x, y, heading = pose
    groups = []
    group = None
    for i, distance in enumerate(scan.ranges):
        if not scan.range_min <= distance <= scan.range_max:
            group = None
            continue
        angle = heading + scan.angle_min + scan.angle_increment * i
        point = [round(x + distance * math.cos(angle), 3), round(y + distance * math.sin(angle), 3)]
        if group is None or math.hypot(point[0] - group[-1][0], point[1] - group[-1][1]) > 0.24:
            group = []
            groups.append(group)
        group.append(point)
    points = [point for group in groups for point in group]
    walls = [wall for group in groups for wall in fit_wall_segments(group)]
    return points, walls


class Observer(object):
    def __init__(self):
        self.lock = threading.Lock()
        self.grid = None
        self.map_message = None
        self.map = None
        self.link = None
        self.scans = OrderedDict()
        self.poses = OrderedDict()
        self.trail = deque(maxlen=1000)
        self.current_pose = None
        self.raw = 0
        self.returned = 0
        self.last_scan_at = None
        self.scan_times = deque(maxlen=24)

    def raw_scan(self, _message):
        with self.lock:
            self.raw += 1

    def scan(self, message):
        with self.lock:
            self.returned += 1
            self.last_scan_at = time.time()
            self.scan_times.append(message.header.stamp.to_sec())
            self.scans[stamp_key(message.header)] = message
            if len(self.scans) > 24:
                self.scans.popitem(last=False)

    def pose(self, message):
        pose = message.pose
        item = [pose.position.x, pose.position.y, yaw(pose.orientation)]
        with self.lock:
            self.current_pose = item
            self.poses[stamp_key(message.header)] = item
            if len(self.poses) > 64:
                self.poses.popitem(last=False)
            if not self.trail or math.hypot(item[0] - self.trail[-1][0], item[1] - self.trail[-1][1]) >= 0.04:
                self.trail.append(item[:2])

    def occupancy(self, message):
        with self.lock:
            self.grid = message

    def link_update(self, message):
        try:
            data = json.loads(message.data)
        except ValueError:
            return
        if not isinstance(data, dict) or "update" not in data or "updated_ms" not in data:
            return
        with self.lock:
            self.link = data

    def state(self, source):
        with self.lock:
            grid, self.grid = self.grid, None
            pose = self.current_pose
            trail = list(self.trail)
            count = (self.raw, self.returned)
            scans = list(self.scans.items())
            poses = dict(self.poses)
            stamps = list(self.scan_times)
            last_scan_at = self.last_scan_at
            link = self.link
        if grid is not None:
            previous = self.map_message
            if (previous is None or previous.header.frame_id != grid.header.frame_id or
                    previous.info != grid.info or previous.data != grid.data):
                self.map = map_snapshot(grid)
            self.map_message = grid
        points, walls = [], []
        for stamp, scan in reversed(scans):
            if stamp not in poses:
                continue
            points, walls = scan_geometry(scan, poses[stamp])
            break
        rate = (len(stamps) - 1) / (stamps[-1] - stamps[0]) if len(stamps) >= 2 and stamps[-1] > stamps[0] else None
        return {"source": source, "written_at": time.time(), "last_scan_at": last_scan_at,
                "map_stamp": self.map_message.header.stamp.to_sec() if self.map_message is not None else None,
                "scan_stamp": stamps[-1] if stamps else None,
                "map": self.map, "pose": pose, "trail": trail, "points": points, "walls": walls,
                "link": link,
                "raw_count": count[0], "sle_count": count[1], "scan_hz": round(rate, 2) if rate else None}


def write_state(path, state):
    directory = os.path.dirname(os.path.abspath(path))
    with tempfile.NamedTemporaryFile(dir=directory, mode="w", delete=False) as output:
        temp = output.name
        try:
            json.dump(state, output, separators=(",", ":"))
            output.flush()
            os.rename(temp, path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--scan-topic", default="/scan_sle")
    parser.add_argument("--source", choices=("live", "recorded"), default="live")
    args = parser.parse_args()
    rospy.init_node("ws63_dashboard_observer")
    observer = Observer()
    subscribers = [rospy.Subscriber(topic, message, consumer, queue_size=4) for topic, message, consumer in (
        ("/map", OccupancyGrid, observer.occupancy), ("/scan", LaserScan, observer.raw_scan),
        (args.scan_topic, LaserScan, observer.scan), ("/slam_out_pose", PoseStamped, observer.pose),
        ("/ws63/link", String, observer.link_update),
    )]
    last_written = None
    while not rospy.is_shutdown():
        state = observer.state(args.source)
        state["scan_topic"] = args.scan_topic
        link = state["link"]
        revision = (state["map_stamp"], state["scan_stamp"], state["pose"], link["update"] if link else None)
        if (state["map"] or link) and revision != last_written:
            write_state(args.output, state)
            last_written = revision
        time.sleep(0.2)
    for subscription in subscribers:
        subscription.unregister()


if __name__ == "__main__":
    main()
