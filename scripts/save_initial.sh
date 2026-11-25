set -e
source /home/jetson/slam_ws/src/nano_slam/scripts/env.sh
echo 'SCAN STATISTICS'
python - <<'PY'
from __future__ import print_function
import math, rospy
from sensor_msgs.msg import LaserScan
rospy.init_node('nano_scan_statistics', anonymous=True)
s=rospy.wait_for_message('/scan',LaserScan,timeout=8)
r=sorted(v for v in s.ranges if not math.isnan(v) and not math.isinf(v) and s.range_min<v<s.range_max)
print('valid={} min={:.3f} median={:.3f} max={:.3f} meters'.format(len(r),r[0],r[len(r)//2],r[-1]))
PY
name="/home/jetson/maps/initial_$(date +%Y%m%d_%H%M%S)"
python "$NANO_SLAM_DIR/scripts/save_map.py" "$name"
echo "$name" > /home/jetson/slam_ws/logs/latest_saved_map.txt
echo 'OPEN MAPPING VIEW'
if ! rosnode list | grep -qx /nano_mapping_rviz; then
  nohup env DISPLAY=:0 XAUTHORITY=/run/user/1000/gdm/Xauthority \
    rviz -d "$NANO_SLAM_DIR/rviz/mapping.rviz" __name:=nano_mapping_rviz \
    > /home/jetson/slam_ws/logs/nano_rviz.log 2>&1 < /dev/null &
fi
sleep 4
rosnode ping -c 1 /nano_mapping_rviz
echo 'RVIZ LOG'
tail -n 15 /home/jetson/slam_ws/logs/nano_rviz.log
echo 'LIVE MAP TF'
timeout 4 rosrun tf tf_echo map laser || test "$?" = 124
