set -e
source /home/jetson/slam_ws/src/nano_slam/scripts/env.sh
echo 'FIXED DEVICE AND REPEAT START CHECK'
bash "$NANO_SLAM_DIR/scripts/start.sh"
echo 'LIVE MAP OBSERVATION'
python - <<'PY'
from __future__ import print_function
import math, time, rospy
from nav_msgs.msg import OccupancyGrid
from geometry_msgs.msg import PoseStamped
rospy.init_node('nano_observe_map',anonymous=True)
for n in range(6):
    m=rospy.wait_for_message('/map',OccupancyGrid,timeout=8)
    p=rospy.wait_for_message('/slam_out_pose',PoseStamped,timeout=8)
    print('sample={} observed={} occupied={} pose=({:.2f},{:.2f})'.format(
        n+1,sum(1 for v in m.data if v>=0),sum(1 for v in m.data if v>=65),p.pose.position.x,p.pose.position.y))
    time.sleep(4)
PY
