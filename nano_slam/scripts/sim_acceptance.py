#!/usr/bin/env python
"""End-to-end tests on the dedicated simulation master; never a real base."""
from __future__ import print_function
import argparse
import json
import math
import os
import subprocess
import sys
import time
import actionlib
import rospy
import tf
from actionlib_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped, Twist
from move_base_msgs.msg import MoveBaseAction, MoveBaseGoal
from nav_msgs.msg import OccupancyGrid, Odometry
from std_msgs.msg import Int32, String
from std_srvs.srv import SetBool

def angle(a):
    return math.atan2(math.sin(a),math.cos(a))

class Acceptance(object):
    def __init__(self):
        self.pose=None; self.local_pose=None; self.odom=None; self.collision_count=0
        self.output=Twist(); self.status=''; self.trace=[]
        self.pub=rospy.Publisher('/nav_cmd_vel',Twist,queue_size=1)
        rospy.Subscriber('/sim/ground_truth',PoseStamped,self.truth)
        rospy.Subscriber('/amcl_pose',__import__('geometry_msgs.msg',fromlist=['PoseWithCovarianceStamped']).PoseWithCovarianceStamped,self.localization)
        rospy.Subscriber('/odom',Odometry,self.odometry)
        rospy.Subscriber('/sim/collisions',Int32,self.collision)
        rospy.Subscriber('/cmd_vel',Twist,self.command)
        rospy.Subscriber('/safety/status',String,self.safety)
        rospy.wait_for_message('/sim/ground_truth',PoseStamped,timeout=12)
    def truth(self,msg):
        self.pose=msg.pose
        self.trace.append([time.time(),msg.pose.position.x,msg.pose.position.y])
    def localization(self,msg):self.local_pose=msg.pose.pose
    def odometry(self,msg):self.odom=msg
    def collision(self,msg):self.collision_count=msg.data
    def command(self,msg):self.output=msg
    def safety(self,msg):self.status=msg.data
    def stop(self):
        for _ in range(8):
            self.pub.publish(Twist()); time.sleep(.05)
    def drive(self,x,y,timeout=70):
        start=time.time()
        while not rospy.is_shutdown() and time.time()-start<timeout:
            if self.pose is None:time.sleep(.1);continue
            dx=x-self.pose.position.x; dy=y-self.pose.position.y
            distance=math.hypot(dx,dy)
            if distance<.12:
                self.stop(); print('MAPPING_WAYPOINT {:.2f},{:.2f}'.format(x,y)); sys.stdout.flush();return
            q=self.pose.orientation
            yaw=tf.transformations.euler_from_quaternion([q.x,q.y,q.z,q.w])[2]
            error=angle(math.atan2(dy,dx)-yaw)
            msg=Twist(); msg.angular.z=max(-.7,min(.7,1.8*error))
            msg.linear.x=min(.32,.7*distance) if abs(error)<.5 else 0.
            self.pub.publish(msg);time.sleep(.05)
        self.stop();raise RuntimeError('Mapping waypoint timeout')
    def mapping(self):
        # Coordinates below are odom/map coordinates (world minus initial position).
        for p in [(5.8,0),(5.8,2.2),(6.,4.2),(3.8,4.2),(1.1,4.),(1.1,2.6),(0,2.6),(0,0)]:
            self.drive(*p)
        time.sleep(3)
        m=rospy.wait_for_message('/map',OccupancyGrid,timeout=10)
        known=sum(1 for v in m.data if v>=0); occupied=sum(1 for v in m.data if v>=65)
        assert known>5000 and occupied>200,'SLAM map incomplete'
        assert self.collision_count==0,'Mapping route collided'
        base='/home/jetson/maps/sim_room'
        if os.path.exists(base+'.pgm') or os.path.exists(base+'.yaml'):
            backup=base+'.backup.'+str(int(time.time()))
            for ext in ('.pgm','.yaml'):
                if os.path.exists(base+ext):os.rename(base+ext,backup+ext)
        subprocess.check_call([sys.executable,os.path.join(os.path.dirname(__file__),'save_map.py'),base])
        return {'mode':'mapping','known_cells':known,'occupied_cells':occupied,
                'collisions':self.collision_count,'map':base+'.yaml','simulation_only':True}
    def goal(self,client,x,y,yaw=0,timeout=90):
        goal=MoveBaseGoal();goal.target_pose.header.frame_id='map';goal.target_pose.header.stamp=rospy.Time.now()
        goal.target_pose.pose.position.x=x;goal.target_pose.pose.position.y=y
        q=tf.transformations.quaternion_from_euler(0,0,yaw)
        goal.target_pose.pose.orientation.z=q[2];goal.target_pose.pose.orientation.w=q[3]
        client.send_goal(goal)
        if not client.wait_for_result(rospy.Duration(timeout)):
            client.cancel_goal();raise RuntimeError('Navigation goal timeout: {},{}'.format(x,y))
        state=client.get_state()
        if state!=GoalStatus.SUCCEEDED:raise RuntimeError('Navigation goal failed with state '+str(state))
        time.sleep(.5)
        # Independent ground truth, not just the action result, judges arrival.
        truth_error=math.hypot(self.pose.position.x-x,self.pose.position.y-y)
        localization_error=math.hypot(self.local_pose.position.x-self.pose.position.x,
                                      self.local_pose.position.y-self.pose.position.y)
        assert truth_error<.30,'True goal error too large: '+str(truth_error)
        assert localization_error<.25,'AMCL position error too large: '+str(localization_error)
        assert self.collision_count==0,'Simulator contact guard was triggered'
        print('NAV_GOAL_OK x={} y={} true_error={:.3f} amcl_error={:.3f}'.format(x,y,truth_error,localization_error));sys.stdout.flush()
        return {'goal':[x,y,yaw],'true_position_error_m':truth_error,'amcl_position_error_m':localization_error,'action_state':state}
    def gate_tests(self):
        scan=rospy.ServiceProxy('/sim/scan_enabled',SetBool)
        odom=rospy.ServiceProxy('/sim/odom_enabled',SetBool)
        estop=rospy.ServiceProxy('/safety/estop',SetBool)
        start_pose=(self.pose.position.x,self.pose.position.y)
        # Rotate in place, then interrupt sensor data, exercising the full output chain.
        scan(False)
        for _ in range(20):
            command=Twist();command.angular.z=.2;self.pub.publish(command);time.sleep(.05)
        assert self.status=='scan_timeout','Missing laser did not inhibit commands'
        assert abs(self.output.angular.z)<1e-6 and abs(self.output.linear.x)<1e-6
        assert abs(self.odom.twist.twist.angular.z)<.01,'Simulated base did not stop'
        scan(True);time.sleep(.5)
        odom(False)
        for _ in range(20):
            command=Twist();command.angular.z=.2;self.pub.publish(command);time.sleep(.05)
        assert self.status=='odom_timeout' and abs(self.output.angular.z)<1e-6,'Missing odometry did not inhibit commands'
        odom(True);time.sleep(.5)
        estop(True)
        for _ in range(12):
            command=Twist();command.angular.z=.2;self.pub.publish(command);time.sleep(.05)
        assert self.status=='estop' and abs(self.output.angular.z)<1e-6,'E-stop failed'
        estop(False)
        for _ in range(5):
            command=Twist();command.angular.z=.2;self.pub.publish(command);time.sleep(.05)
        time.sleep(1)
        assert self.status=='command_timeout' and abs(self.output.angular.z)<1e-6,'Command timeout failed'
        assert abs(self.odom.twist.twist.angular.z)<.01
        for _ in range(12):
            command=Twist();command.linear.x=float('nan');self.pub.publish(command);time.sleep(.05)
        assert self.status=='invalid_command' and abs(self.output.linear.x)<1e-6,'Invalid command accepted'
        self.stop()
        print('GATE_TESTS_OK scan_timeout odom_timeout estop command_timeout invalid_command');sys.stdout.flush()
        return dict((key,'passed') for key in ('scan_timeout','odom_timeout','estop','command_timeout','invalid_command'))
    def navigation(self):
        client=actionlib.SimpleActionClient('/move_base',MoveBaseAction)
        if not client.wait_for_server(rospy.Duration(20)):raise RuntimeError('move_base action unavailable')
        rospy.wait_for_message('/amcl_pose',__import__('geometry_msgs.msg',fromlist=['PoseWithCovarianceStamped']).PoseWithCovarianceStamped,timeout=15)
        # The first goal crosses the central static box and requires a detour.
        outcomes=[]
        outcomes.append(self.goal(client,5.8,2.8,0))
        outcomes.append(self.goal(client,0.,0.,0))
        # A new box is not present in the saved map; only the laser can discover it.
        rospy.ServiceProxy('/sim/dynamic_obstacle',SetBool)(True)
        start_index=len(self.trace)
        outcomes.append(self.goal(client,5.8,0.,0))
        detour_trace=self.trace[start_index:]
        # In odom coords the new box occupies x=[2.5,3.1], y=[-.4,.4].
        deviation=max(abs(row[2]) for row in detour_trace if 2.0<row[1]<3.6)
        assert deviation>.55,'New obstacle was not bypassed geometrically'
        rospy.ServiceProxy('/sim/dynamic_obstacle',SetBool)(False)
        outcomes.append(self.goal(client,0.,0.,0))
        outcomes.append(self.goal(client,0.,1.5,math.pi/2))
        gate_results=self.gate_tests()
        return {'mode':'navigation','simulation_only':True,'odometry_model':'ideal',
                'goals':outcomes,'collisions':self.collision_count,
                'dynamic_obstacle_detour_m':deviation,'safety':gate_results,
                'trace':self.trace}

if __name__=='__main__':
    if os.environ.get('ROS_MASTER_URI') not in ('http://127.0.0.1:11312','http://localhost:11312'):
        raise SystemExit('Acceptance tests only run against the dedicated simulation master')
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['mapping','navigation']);args=parser.parse_args()
    rospy.init_node('simulation_acceptance',anonymous=True)
    runner=Acceptance()
    report_path='/home/jetson/slam_ws/logs/simulation/'+args.mode+'_report.json'
    try:
        result=runner.mapping() if args.mode=='mapping' else runner.navigation()
        result['passed']=True
        with open(report_path,'w') as f:json.dump(result,f,indent=2)
        print('ACCEPTANCE_PASSED '+report_path)
    except Exception as exc:
        runner.stop()
        with open(report_path,'w') as f:json.dump({'passed':False,'error':str(exc),'trace':runner.trace},f)
        raise
