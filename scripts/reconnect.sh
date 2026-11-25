set -e
source /home/jetson/slam_ws/src/nano_slam/scripts/env.sh
echo 'RECONNECTED DEVICE'
ls -l /dev/serial/by-id/* /dev/ttyUSB* 2>/dev/null || true
bash "$NANO_SLAM_DIR/scripts/start.sh" /dev/ttyUSB1
echo 'SCAN FREQUENCY'
timeout 8 rostopic hz /scan || test "$?" = 124
echo 'MAP CONTENT'
python - <<'PY'
from __future__ import print_function
import rospy
from nav_msgs.msg import OccupancyGrid
rospy.init_node('nano_verify_real_map', anonymous=True)
m = rospy.wait_for_message('/map', OccupancyGrid, timeout=12)
known = sum(1 for x in m.data if x >= 0)
occupied = sum(1 for x in m.data if x >= 65)
print('REAL_MAP frame={} size={}x{} resolution={} known={} occupied={}'.format(m.header.frame_id,m.info.width,m.info.height,m.info.resolution,known,occupied))
if known == 0 or occupied == 0:
    raise SystemExit('No observed obstacles yet')
PY
echo 'DRIVER LOG'
tail -n 20 /home/jetson/slam_ws/logs/nano_lidar.log
