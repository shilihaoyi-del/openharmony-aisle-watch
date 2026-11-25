source /opt/ros/melodic/setup.bash
export ROS_MASTER_URI=http://localhost:11311
echo 'REAL LIDAR PROCESSES'
ps -eo pid,args | grep -E '[r]plidarNode|[s]llidar_node|[r]oslaunch.*rplidar|[r]osmaster' || true
echo 'ROS STOP MOTOR SERVICE'
if timeout 4 rosservice list > /tmp/jetson_lidar_services.txt 2>/dev/null; then
  if grep -qx /stop_motor /tmp/jetson_lidar_services.txt; then
    timeout 8 rosservice call /stop_motor '{}'
    echo "STOP_MOTOR_SERVICE_EXIT=$?"
  else
    echo 'NO_STOP_MOTOR_SERVICE'
  fi
else
  echo 'NO_REAL_ROS_MASTER'
fi
echo 'DRIVER SDK STOP IMPLEMENTATION'
sed -n '170,220p' /home/jetson/slam_ws/src/rplidar_ros/src/node.cpp
echo 'SDK BUILD FILES'
find /home/jetson/slam_ws/src/rplidar_ros -maxdepth 4 -name '*.h' -o -name '*Makefile*' -o -name '*.a' | head -n 25
echo 'REAL LIDAR USB'
ls -l /dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0
