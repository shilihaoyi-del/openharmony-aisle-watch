set -e
source /home/jetson/slam_ws/src/nano_slam/scripts/env.sh
echo 'PACKAGE'
rospack find nano_slam
echo 'LAUNCH VALIDATION'
roslaunch --nodes nano_slam mapping.launch
echo 'PYTHON SYNTAX'
python -m py_compile "$NANO_SLAM_DIR/scripts/save_map.py" "$NANO_SLAM_DIR/scripts/check_scan.py"
bash -n "$NANO_SLAM_DIR/scripts/env.sh"
echo 'DRIVER HEALTH HISTORY'
grep -E 'RPLIDAR|RPLidar|Firmware|Hardware|S/N|Model' /home/jetson/.ros/log/latest/rosout.log | head -n 12
echo 'START MAPPING'
if ! rosnode list | grep -qx /nano_hector_mapping; then
  mkdir -p /home/jetson/slam_ws/logs
  nohup bash -c 'source /home/jetson/slam_ws/src/nano_slam/scripts/env.sh; exec roslaunch nano_slam mapping.launch' > /home/jetson/slam_ws/logs/nano_slam.log 2>&1 < /dev/null &
  echo "LAUNCH_PID=$!"
fi
sleep 4
rosnode info /nano_hector_mapping
tail -n 15 /home/jetson/slam_ws/logs/nano_slam.log
echo 'USB STATUS'
ls -l /dev/ttyUSB* 2>/dev/null || true
