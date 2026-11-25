source /opt/ros/melodic/setup.bash
source /home/jetson/slam_ws/devel/setup.bash
export ROS_MASTER_URI=http://localhost:11311
echo 'ROS NODES AND TOPICS'
timeout 10 rosnode list
timeout 10 rostopic list -v
echo 'DRIVER PARAMETERS'
timeout 10 rosparam get /rplidarNode
echo 'DRIVER LAUNCH'
cat /home/jetson/slam_ws/src/rplidar_ros/launch/rplidar_a1.launch
echo 'DRIVER LOG'
tail -n 35 /home/jetson/.ros/log/latest/rplidarNode-2.log
echo 'SCAN SAMPLE'
timeout 8 rostopic echo -n 1 /scan/header
echo 'EXISTING PROJECT CONFIG'
find /home/jetson/slam_ws/src -maxdepth 4 -name '*.launch' -o -name AGENTS.md
echo 'MAP SAVER'
rospack find map_server
