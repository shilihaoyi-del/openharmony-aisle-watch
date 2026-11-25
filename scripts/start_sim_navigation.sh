set -e
source /home/jetson/slam_ws/src/nano_slam/scripts/simulation_env.sh
echo 'MAPPING RESULT'
cat /home/jetson/slam_ws/logs/simulation/mapping_report.json
python -c 'import json; assert json.load(open("/home/jetson/slam_ws/logs/simulation/mapping_report.json"))["passed"]'
roslaunch --nodes nano_slam simulation_navigation.launch
bash "$NANO_SLAM_DIR/scripts/run_simulation.sh" navigation
nohup python -u "$NANO_SLAM_DIR/scripts/sim_acceptance.py" navigation > /home/jetson/slam_ws/logs/simulation/navigation_test.log 2>&1 < /dev/null &
echo "$!" > /home/jetson/slam_ws/logs/simulation/test.pid
echo "NAVIGATION_TEST_PID=$!"
