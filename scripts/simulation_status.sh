source /home/jetson/slam_ws/src/nano_slam/scripts/simulation_env.sh
mode="$(cat /home/jetson/slam_ws/logs/simulation/mode)"
echo "MODE=$mode"
tail -n 12 "/home/jetson/slam_ws/logs/simulation/${mode}_test.log"
echo 'LAUNCH ERRORS'
grep -Ei 'error|died|exception|failed' "/home/jetson/slam_ws/logs/simulation/$mode.log" | tail -n 5 || true
echo 'NODES'
timeout 4 rosnode list
echo 'TEST PROCESS'
ps -p "$(cat /home/jetson/slam_ws/logs/simulation/test.pid)" -o pid,stat,etime,%cpu,args
