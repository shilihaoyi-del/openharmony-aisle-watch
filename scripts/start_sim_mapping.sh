set -e
source /home/jetson/slam_ws/src/nano_slam/scripts/simulation_env.sh
python -m py_compile "$NANO_SLAM_DIR/scripts/sim_base.py" "$NANO_SLAM_DIR/scripts/safety_gate.py" "$NANO_SLAM_DIR/scripts/sim_acceptance.py"
roslaunch --nodes nano_slam simulation_mapping.launch
bash "$NANO_SLAM_DIR/scripts/run_simulation.sh" mapping
nohup python -u "$NANO_SLAM_DIR/scripts/sim_acceptance.py" mapping > /home/jetson/slam_ws/logs/simulation/mapping_test.log 2>&1 < /dev/null &
echo "$!" > /home/jetson/slam_ws/logs/simulation/test.pid
echo "MAPPING_TEST_PID=$!"
