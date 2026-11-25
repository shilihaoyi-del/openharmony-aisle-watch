#!/usr/bin/env python
"""Lightweight differential-drive simulator; uses ideal odometry, not real hardware."""
from __future__ import print_function
import math
import threading
import time
import os
import numpy as np
import rospy
import tf
from geometry_msgs.msg import Twist, PoseStamped
from nav_msgs.msg import Odometry
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Int32
from std_srvs.srv import SetBool, SetBoolResponse

# World coordinates in metres. The mapping origin is the first pose (1,1).
STATIC_BOXES = [(0,0,8,.10),(0,5.90,8,6),(0,0,.10,6),(7.90,0,8,6),
                (3.3,2.0,4.3,3.5),(5.5,4.1,6.5,4.8),(.8,4.4,1.5,5.2)]

class Simulator(object):
    def __init__(self):
        self.lock = threading.RLock()
        self.x, self.y, self.yaw = 1.,1.,0.
        self.v = self.w = self.target_v = self.target_w = 0.
        self.last_command = 0
        self.scan_enabled = True
        self.odom_enabled = True
        self.dynamic = False
        self.collisions = 0
        self.angles = np.linspace(-math.pi, math.pi, 360, endpoint=False)
        self.rng = np.random.RandomState(7)
        self.odom_pub = rospy.Publisher('/odom',Odometry,queue_size=1)
        self.scan_pub = rospy.Publisher('/scan',LaserScan,queue_size=1)
        self.truth_pub = rospy.Publisher('/sim/ground_truth',PoseStamped,queue_size=1)
        self.collision_pub = rospy.Publisher('/sim/collisions',Int32,queue_size=1,latch=True)
        self.broadcaster = tf.TransformBroadcaster()
        rospy.Subscriber('/cmd_vel',Twist,self.command,queue_size=1)
        rospy.Service('/sim/scan_enabled',SetBool,self.enable_scan)
        rospy.Service('/sim/odom_enabled',SetBool,self.enable_odom)
        rospy.Service('/sim/dynamic_obstacle',SetBool,self.obstacle)
        self.last_tick = time.time()
        rospy.Timer(rospy.Duration(.05),self.tick)
        rospy.Timer(rospy.Duration(.1),self.scan)
    def boxes(self):
        return STATIC_BOXES + ([(3.5,.6,4.1,1.4)] if self.dynamic else [])
    def command(self,msg):
        with self.lock:
            self.target_v = max(-.15,min(.35,msg.linear.x))
            self.target_w = max(-.8,min(.8,msg.angular.z))
            self.last_command = time.time()
    def enable_scan(self,req):
        self.scan_enabled=req.data
        return SetBoolResponse(True,'scan enabled='+str(req.data))
    def enable_odom(self,req):
        self.odom_enabled=req.data
        return SetBoolResponse(True,'odom enabled='+str(req.data))
    def obstacle(self,req):
        self.dynamic=req.data
        return SetBoolResponse(True,'dynamic obstacle='+str(req.data))
    def collision(self,x,y,yaw):
        # Exact oriented rectangular footprint, matching the planner's unpadded body.
        c,s=math.cos(yaw),math.sin(yaw)
        robot=[(x+c*px-s*py,y+s*px+c*py) for px,py in
               [(-.20,-.15),(-.20,.15),(.20,.15),(.20,-.15)]]
        for x0,y0,x1,y1 in self.boxes():
            box=[(x0,y0),(x0,y1),(x1,y1),(x1,y0)]
            overlap=True
            for ax,ay in [(1,0),(0,1),(c,s),(-s,c)]:
                a=[px*ax+py*ay for px,py in robot];b=[px*ax+py*ay for px,py in box]
                if max(a)<=min(b) or max(b)<=min(a):
                    overlap=False;break
            if overlap:return True
        return False
    @staticmethod
    def approach(value,target,step):
        return value+max(-step,min(step,target-value))
    def tick(self,event):
        with self.lock:
            now=time.time(); dt=min(.1,max(0.,now-self.last_tick)); self.last_tick=now
            if now-self.last_command>.4:
                self.target_v=self.target_w=0.
            self.v=self.approach(self.v,self.target_v,.5*dt)
            self.w=self.approach(self.w,self.target_w,1.5*dt)
            mid=self.yaw+.5*self.w*dt
            nx=self.x+self.v*math.cos(mid)*dt; ny=self.y+self.v*math.sin(mid)*dt
            next_yaw=self.yaw+self.w*dt
            if self.collision(nx,ny,next_yaw) and (abs(self.v)>1e-5 or abs(self.w)>1e-5):
                self.collisions+=1; self.v=self.w=0
            else:
                self.x,self.y=nx,ny
                self.yaw=math.atan2(math.sin(next_yaw),math.cos(next_yaw))
            stamp=rospy.Time.now(); q=tf.transformations.quaternion_from_euler(0,0,self.yaw)
            self.broadcaster.sendTransform((self.x-1,self.y-1,0),q,stamp,'base_link','odom')
            self.broadcaster.sendTransform((0,0,.2),(0,0,0,1),stamp,'laser','base_link')
            odom=Odometry(); odom.header.stamp=stamp; odom.header.frame_id='odom'; odom.child_frame_id='base_link'
            odom.pose.pose.position.x=self.x-1; odom.pose.pose.position.y=self.y-1
            odom.pose.pose.orientation.x,odom.pose.pose.orientation.y,odom.pose.pose.orientation.z,odom.pose.pose.orientation.w=q
            odom.twist.twist.linear.x=self.v; odom.twist.twist.angular.z=self.w
            odom.pose.covariance[0]=odom.pose.covariance[7]=.0001; odom.pose.covariance[35]=.0001
            if self.odom_enabled:self.odom_pub.publish(odom)
            truth=PoseStamped(); truth.header=odom.header; truth.pose=odom.pose.pose
            self.truth_pub.publish(truth); self.collision_pub.publish(self.collisions)
    def scan(self,event):
        with self.lock:
            if not self.scan_enabled:return
            x,y,yaw=self.x,self.y,self.yaw; boxes=self.boxes()
        angles=self.angles+yaw; dx=np.cos(angles); dy=np.sin(angles)
        distances=np.full(360,8.)
        # Intersections with all rectangle edges, vectorised over rays.
        for x0,y0,x1,y1 in boxes:
            for edge in (x0,x1):
                t=(edge-x)/np.where(np.abs(dx)<1e-9,1e-9,dx)
                valid=(t>0)&(y+t*dy>=y0)&(y+t*dy<=y1)
                distances=np.minimum(distances,np.where(valid,t,8.))
            for edge in (y0,y1):
                t=(edge-y)/np.where(np.abs(dy)<1e-9,1e-9,dy)
                valid=(t>0)&(x+t*dx>=x0)&(x+t*dx<=x1)
                distances=np.minimum(distances,np.where(valid,t,8.))
        distances=np.clip(distances+self.rng.normal(0,.003,360),.08,8.)
        msg=LaserScan(); msg.header.stamp=rospy.Time.now(); msg.header.frame_id='laser'
        msg.angle_min=-math.pi; msg.angle_increment=2*math.pi/360; msg.angle_max=msg.angle_min+359*msg.angle_increment
        msg.range_min=.08; msg.range_max=8.; msg.scan_time=.1; msg.time_increment=0.
        msg.ranges=distances.tolist(); self.scan_pub.publish(msg)

if __name__=='__main__':
    if os.environ.get('ROS_MASTER_URI') not in ('http://127.0.0.1:11312','http://localhost:11312'):
        raise SystemExit('Simulator requires the dedicated loopback ROS master on port 11312')
    rospy.init_node('sim_base')
    simulator=Simulator()
    rospy.spin()
