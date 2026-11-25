#!/bin/bash
set -eo pipefail
source "$(dirname "$0")/env.sh"
mkdir -p /home/jetson/slam_ws/logs
port="${1:-/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0}"
if ! test -c "$port"; then
  echo "LIDAR_NOT_CONNECTED: $port is absent. Connect lidar power and USB data cable."
  exit 1
fi
if ! timeout 5 rosnode list > /dev/null 2>&1; then
  nohup roscore > /home/jetson/slam_ws/logs/nano_roscore.log 2>&1 < /dev/null &
  sleep 4
  timeout 5 rosnode list > /dev/null
fi
if ! python "$NANO_SLAM_DIR/scripts/check_scan.py"; then
  # Recover only the lidar node; keep the ROS master, GUI and other robot nodes.
  if rosnode list 2>/dev/null | grep -qx /rplidarNode; then
    rosnode kill /rplidarNode
    sleep 2
  fi
  # These settings match the pre-existing A1 configuration on this Nano.
  nohup rosrun rplidar_ros rplidarNode _serial_port:="$port" _serial_baudrate:=115200 \
    _frame_id:=laser _inverted:=false _angle_compensate:=true __name:=rplidarNode \
    > /home/jetson/slam_ws/logs/nano_lidar.log 2>&1 < /dev/null &
  echo "$!" > /home/jetson/slam_ws/logs/nano_lidar.pid
  sleep 4
  python "$NANO_SLAM_DIR/scripts/check_scan.py"
fi
if ! rosnode list | grep -qx /nano_hector_mapping; then
  nohup roslaunch nano_slam mapping.launch \
    > /home/jetson/slam_ws/logs/nano_slam.log 2>&1 < /dev/null &
  echo "$!" > /home/jetson/slam_ws/logs/nano_slam.pid
  sleep 4
fi
rosnode ping -c 1 /nano_hector_mapping
echo 'READY: laser-only mapping; no wheel commands are sent.'
