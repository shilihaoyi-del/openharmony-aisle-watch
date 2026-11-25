set -e
source /home/jetson/slam_ws/src/nano_slam/scripts/simulation_env.sh
if ! rosnode list | grep -qx /simulation_rviz; then
  nohup env DISPLAY=:0 XAUTHORITY=/run/user/1000/gdm/Xauthority \
    rviz -d "$NANO_SLAM_DIR/rviz/navigation_simulation.rviz" __name:=simulation_rviz \
    > /home/jetson/slam_ws/logs/simulation/rviz.log 2>&1 < /dev/null &
fi
sleep 4
rosnode ping -c 1 /simulation_rviz
tail -n 15 /home/jetson/slam_ws/logs/simulation/rviz.log
