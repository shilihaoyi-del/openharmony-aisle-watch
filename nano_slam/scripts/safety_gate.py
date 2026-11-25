#!/usr/bin/env python
"""Velocity gate; real hardware also needs its own independent watchdog."""
from __future__ import print_function
import time
import math
import rospy
from geometry_msgs.msg import Twist
from sensor_msgs.msg import LaserScan
from nav_msgs.msg import Odometry
from std_msgs.msg import String
from std_srvs.srv import SetBool, SetBoolResponse

class Gate(object):
    def __init__(self):
        self.scan = self.odom = self.command_time = 0
        self.command = Twist()
        self.estop = False
        self.pub = rospy.Publisher('/cmd_vel', Twist, queue_size=1)
        self.state = rospy.Publisher('/safety/status', String, queue_size=1, latch=True)
        rospy.Subscriber('/nav_cmd_vel', Twist, self.cmd, queue_size=1)
        rospy.Subscriber('/scan', LaserScan, self.scan_cb, queue_size=1)
        rospy.Subscriber('/odom', Odometry, self.odom_cb, queue_size=1)
        rospy.Service('/safety/estop', SetBool, self.stop)
        rospy.Timer(rospy.Duration(0.05), self.tick)
    def cmd(self, msg):
        self.command, self.command_time = msg, time.time()
    def scan_cb(self, msg):
        valid = sum(1 for r in msg.ranges if not math.isnan(r) and not math.isinf(r)
                    and msg.range_min <= r <= msg.range_max)
        if valid >= 10 and abs((rospy.Time.now()-msg.header.stamp).to_sec()) < 0.4:
            self.scan = time.time()
    def odom_cb(self, msg):
        if abs((rospy.Time.now()-msg.header.stamp).to_sec()) < 0.3:
            self.odom = time.time()
    def stop(self, req):
        self.estop = req.data
        return SetBoolResponse(True, 'stopped' if self.estop else 'released')
    def tick(self, event):
        now = time.time()
        reason = 'ready'
        if self.estop: reason = 'estop'
        elif now-self.scan > 0.4: reason = 'scan_timeout'
        elif now-self.odom > 0.3: reason = 'odom_timeout'
        elif now-self.command_time > 0.3: reason = 'command_timeout'
        elif any(math.isnan(v) or math.isinf(v) for v in
                 (self.command.linear.x,self.command.angular.z)): reason = 'invalid_command'
        out = Twist()
        if reason == 'ready':
            out.linear.x = max(-0.15, min(0.35, self.command.linear.x))
            out.angular.z = max(-0.8, min(0.8, self.command.angular.z))
        self.pub.publish(out)
        self.state.publish(reason)

if __name__ == '__main__':
    rospy.init_node('safety_gate')
    gate = Gate()
    rospy.spin()
