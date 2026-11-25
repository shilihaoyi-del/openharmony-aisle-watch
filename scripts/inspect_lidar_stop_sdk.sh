echo 'SDK CREATION'
sed -n '250,335p' /home/jetson/slam_ws/src/rplidar_ros/src/node.cpp
echo 'SDK MOTOR SUPPORT'
grep -nE 'setMotorSpeed|MOTOR_CTRL|MotorCtrl|_motor|_isSupportingMotorCtrl|_isSupportingMotor' /home/jetson/slam_ws/src/rplidar_ros/sdk/src/sl_lidar_driver.cpp | tail -n 45
echo 'MOTOR IMPLEMENTATION'
grep -n -A 90 -B 8 'sl_result setMotorSpeed' /home/jetson/slam_ws/src/rplidar_ros/sdk/src/sl_lidar_driver.cpp
echo 'OBJECT FILES'
find /home/jetson/slam_ws/build -type f -path '*/rplidarNode.dir/sdk/*' -name '*.o' | head -n 8
echo 'LINK COMMAND'
cat /home/jetson/slam_ws/build/rplidar_ros/CMakeFiles/rplidarNode.dir/link.txt
