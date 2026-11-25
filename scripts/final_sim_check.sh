set -e
source /home/jetson/slam_ws/src/nano_slam/scripts/simulation_env.sh
for script in "$NANO_SLAM_DIR"/scripts/*.sh; do bash -n "$script"; done
python -m py_compile "$NANO_SLAM_DIR/scripts/sim_base.py" "$NANO_SLAM_DIR/scripts/safety_gate.py" "$NANO_SLAM_DIR/scripts/sim_acceptance.py"
roslaunch --nodes nano_slam navigation.launch map:=/home/jetson/maps/sim_room.yaml
python - <<'PY'
from __future__ import print_function
import json,os,rospy
from std_msgs.msg import String
from nav_msgs.msg import Odometry
for mode in ('mapping','navigation'):
    p='/home/jetson/slam_ws/logs/simulation/'+mode+'_report.json'
    data=json.load(open(p));assert data['passed'] and data['collisions']==0
    print(mode.upper()+'_REPORT_VERIFIED')
rospy.init_node('final_simulation_check',anonymous=True)
status=rospy.wait_for_message('/safety/status',String,timeout=5).data
odom=rospy.wait_for_message('/odom',Odometry,timeout=5)
assert abs(odom.twist.twist.linear.x)<.01 and abs(odom.twist.twist.angular.z)<.01
print('IDLE_BASE_STOPPED safety='+status)
PY
echo 'GUI'
rosnode ping -c 1 /simulation_rviz
echo 'REAL MASTER REMAINS SEPARATE'
ROS_MASTER_URI=http://127.0.0.1:11311 timeout 5 rostopic info /cmd_vel 2>&1 || true
