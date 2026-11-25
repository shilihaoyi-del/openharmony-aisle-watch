set -e
source /home/jetson/slam_ws/src/nano_slam/scripts/env.sh
echo 'LIVE SENSOR'
python "$NANO_SLAM_DIR/scripts/check_scan.py"
echo 'MAP ASSESSMENT'
python - <<'PY'
from __future__ import print_function
import rospy
from nav_msgs.msg import OccupancyGrid
from geometry_msgs.msg import PoseStamped
rospy.init_node('nano_final_map_check',anonymous=True)
m=rospy.wait_for_message('/map',OccupancyGrid,timeout=12)
indices=[i for i,v in enumerate(m.data) if v>=0]
occupied=sum(1 for v in m.data if v>=65)
if not indices or not occupied:
    raise SystemExit('Map has no observed obstacle cells')
w=m.info.width
xs=[i%w for i in indices]; ys=[i//w for i in indices]
print('MAP frame={} width={} height={} resolution={:.3f} known={} occupied={}'.format(
    m.header.frame_id,w,m.info.height,m.info.resolution,len(indices),occupied))
print('OBSERVED_BOUNDS width_m={:.2f} height_m={:.2f} observed_area_m2={:.2f}'.format(
    (max(xs)-min(xs)+1)*m.info.resolution,(max(ys)-min(ys)+1)*m.info.resolution,len(indices)*m.info.resolution**2))
p=rospy.wait_for_message('/slam_out_pose',PoseStamped,timeout=8)
print('END_POSE x={:.3f} y={:.3f} (closure accuracy requires a measured reference)'.format(p.pose.position.x,p.pose.position.y))
PY
name="/home/jetson/maps/room_$(date +%Y%m%d_%H%M%S)"
python "$NANO_SLAM_DIR/scripts/save_map.py" "$name"
echo "$name" > /home/jetson/slam_ws/logs/latest_saved_map.txt
echo 'SAVED FILES'
ls -lh "$name.pgm" "$name.yaml"
cat "$name.yaml"
echo 'MAPPING WARNINGS'
grep -Ei 'error|warn|failed' /home/jetson/slam_ws/logs/nano_slam.log | tail -n 10 || true
