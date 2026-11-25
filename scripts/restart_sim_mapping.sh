set -e
source /home/jetson/slam_ws/src/nano_slam/scripts/simulation_env.sh
test_pid="$(cat /home/jetson/slam_ws/logs/simulation/test.pid)"
if [[ "$test_pid" =~ ^[0-9]+$ ]] && [[ -f "/proc/$test_pid/cmdline" ]]; then
  if tr '\0' ' ' < "/proc/$test_pid/cmdline" | grep -q 'sim_acceptance.py mapping'; then
    kill -TERM "$test_pid"
    sleep 1
  fi
fi
bash "$NANO_SLAM_DIR/scripts/run_simulation.sh" mapping
nohup python -u "$NANO_SLAM_DIR/scripts/sim_acceptance.py" mapping > /home/jetson/slam_ws/logs/simulation/mapping_test.log 2>&1 < /dev/null &
echo "$!" > /home/jetson/slam_ws/logs/simulation/test.pid
echo "RESTARTED_MAPPING_PID=$!"
