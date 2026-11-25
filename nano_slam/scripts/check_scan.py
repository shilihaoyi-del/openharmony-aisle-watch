#!/usr/bin/env python
from __future__ import print_function
import math
import sys
import time
import rospy
from sensor_msgs.msg import LaserScan

rospy.init_node('nano_check_scan', anonymous=True)
try:
    start = time.time()
    frames = [rospy.wait_for_message('/scan', LaserScan, timeout=8) for _ in range(5)]
    scan = frames[-1]
    valid = sum(1 for r in scan.ranges if not math.isnan(r) and not math.isinf(r)
                and scan.range_min < r < scan.range_max)
    if valid < 10 or not scan.header.frame_id:
        raise ValueError('Too few valid ranges or missing frame_id')
    print('SCAN_OK frame={} points={} valid={} elapsed={:.2f}s stamp={:.3f}'.format(
        scan.header.frame_id, len(scan.ranges), valid, time.time()-start, scan.header.stamp.to_sec()))
except Exception as exc:
    print('SCAN_FAILED: {}'.format(exc), file=sys.stderr)
    sys.exit(1)
