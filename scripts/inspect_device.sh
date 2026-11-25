source /opt/ros/melodic/setup.bash
export ROS_MASTER_URI=http://localhost:11311
echo 'SERIAL DRIVERS'
ls -l /dev/ttyUSB* /dev/ttyACM* /dev/rplidar* /dev/serial/by-id/* 2>/dev/null || true
lsmod | grep -E 'cp210|ch341|usbserial' || true
dmesg | grep -Ei 'ttyUSB|ttyACM|cp210|ch341|disconnect|over-current' | tail -n 25
echo 'PROCESS FILE DESCRIPTORS'
ls -l /proc/9961/fd 2>/dev/null
echo 'RECENT DRIVER LOGS'
find /home/jetson/.ros/log -maxdepth 2 -type f -name '*rplidar*' -printf '%T@ %p\n' | sort -nr | head -n 8
echo 'LATEST ROS LOG'
ls -l /home/jetson/.ros/log/latest
echo 'DRIVER MODEL LOG'
grep -Ei 'model|firmware|serial|error|health|disconnect' /home/jetson/.ros/log/73070028-d814-11f1-86e5-3c6d66450d92/* 2>/dev/null | tail -n 25
echo 'HECTOR CONFIG'
cat /opt/ros/melodic/share/hector_mapping/launch/mapping_default.launch
echo 'SOURCE BEHAVIOR'
grep -nE 'motor|startMotor|stopMotor|grabScan|while' /home/jetson/slam_ws/src/rplidar_ros/src/node.cpp
