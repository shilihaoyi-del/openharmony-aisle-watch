set -e
echo 'MASTER LISTEN ADDRESSES'
ss -ltn | grep -E ':11311|:11312'
echo 'REAL MASTER SPEED TOPIC'
source /opt/ros/melodic/setup.bash
export ROS_MASTER_URI=http://127.0.0.1:11311
timeout 5 rostopic info /cmd_vel 2>&1 || true
echo 'SIMULATION SPEED TOPIC'
source /home/jetson/slam_ws/src/nano_slam/scripts/simulation_env.sh
timeout 5 rostopic info /cmd_vel
echo 'SIMULATION SENSOR HEALTH'
timeout 4 rostopic hz /scan 2>&1 || true
echo 'RESOURCES'
free -h
df -h /
