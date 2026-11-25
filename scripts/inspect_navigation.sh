source /opt/ros/melodic/setup.bash
source /home/jetson/yahboomcar_ws/devel/setup.bash
export ROS_MASTER_URI=http://localhost:11311
echo 'INSTALLED NAVIGATION'
for p in move_base amcl map_server gmapping teb_local_planner dwa_local_planner robot_localization; do
  rospack find "$p" 2>/dev/null || true
done
echo 'CURRENT ROS GRAPH'
timeout 6 rosnode list
timeout 6 rostopic list -v
echo 'BOTTOM BOARD SOFTWARE'
find /home/jetson/yahboomcar_ws/src/yahboomcar_bringup /home/jetson/yahboomcar_ws/src/yahboomcar_ctrl -maxdepth 3 -type f \( -name '*.py' -o -name '*.cpp' -o -name '*.launch' -o -name '*.yaml' -o -name 'package.xml' \) | head -n 65
echo 'CONTROL AND ODOMETRY REFERENCES'
if command -v rg >/dev/null; then
  rg -n -m 8 'cmd_vel|Odometry|odom|Rosmaster|Transbot|set_motor|set_car_motion|serial.Serial|imu' /home/jetson/yahboomcar_ws/src/yahboomcar_bringup /home/jetson/yahboomcar_ws/src/yahboomcar_ctrl | head -n 100
else
  grep -RnE 'cmd_vel|Odometry|odom|Rosmaster|Transbot|set_motor|set_car_motion|serial.Serial|imu' /home/jetson/yahboomcar_ws/src/yahboomcar_bringup /home/jetson/yahboomcar_ws/src/yahboomcar_ctrl --include='*.py' --include='*.cpp' --include='*.launch' | head -n 100
fi
echo 'DEVICE PORTS'
ls -l /dev/ttyUSB* /dev/ttyACM* /dev/serial/by-id/* 2>/dev/null || true
