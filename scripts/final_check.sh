set -e
source /home/jetson/slam_ws/src/nano_slam/scripts/env.sh
bash -n "$NANO_SLAM_DIR/scripts/start.sh"
roslaunch --nodes nano_slam mapping.launch rviz:=true
echo 'LIVE MAPPING NODE'
rosnode ping -c 1 /nano_hector_mapping
echo 'RECOVERY CHECK'
set +e
bash "$NANO_SLAM_DIR/scripts/start.sh" /dev/ttyUSB0
result=$?
set -e
echo "RECOVERY_EXIT=$result"
echo 'DEVICE STATE'
lsusb
ls -l /dev/ttyUSB* /dev/ttyACM* 2>/dev/null || true
