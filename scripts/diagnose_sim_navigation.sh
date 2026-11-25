source /home/jetson/slam_ws/src/nano_slam/scripts/simulation_env.sh
python - <<'PY'
from __future__ import print_function
import math,rospy,tf
from geometry_msgs.msg import PoseStamped,Twist
from std_msgs.msg import Int32,String
from nav_msgs.msg import Path
rospy.init_node('diagnose_navigation',anonymous=True)
p=rospy.wait_for_message('/sim/ground_truth',PoseStamped,timeout=5).pose
q=p.orientation
print('TRUTH',p.position.x,p.position.y,tf.transformations.euler_from_quaternion([q.x,q.y,q.z,q.w])[2])
print('COLLISIONS',rospy.wait_for_message('/sim/collisions',Int32,timeout=5).data)
print('GATE',rospy.wait_for_message('/safety/status',String,timeout=5).data)
try:
 path=rospy.wait_for_message('/move_base/NavfnROS/plan',Path,timeout=3)
 print('PLAN',[(round(x.pose.position.x,2),round(x.pose.position.y,2)) for x in path.poses[::max(1,len(path.poses)//12)]])
except Exception as e:print(str(e))
PY
tail -n 30 /home/jetson/slam_ws/logs/simulation/navigation.log
