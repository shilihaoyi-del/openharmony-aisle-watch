set -e
sdk=/home/jetson/slam_ws/src/rplidar_ros/sdk
root=/home/jetson/slam_ws/src/nano_slam
build=/home/jetson/slam_ws/logs/lidar_control
mkdir -p "$build"
mapfile -d '' objects < <(find /home/jetson/slam_ws/build/rplidar_ros/CMakeFiles/rplidarNode.dir/sdk -name '*.o' -print0)
g++ -std=c++11 -O2 -I "$sdk/include" -I "$sdk/src" \
  "$root/scripts/lidar_stop.cpp" "${objects[@]}" -pthread -o "$build/lidar_stop"
"$build/lidar_stop" | tee "$build/last_stop.log"
echo 'NO SCAN PROCESS SHOULD REMAIN'
ps -eo pid,args | grep -E '[r]plidarNode|[s]llidar_node' || true
