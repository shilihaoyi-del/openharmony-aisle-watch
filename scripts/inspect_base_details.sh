echo 'BRINGUP LAUNCH'
cat /home/jetson/yahboomcar_ws/src/yahboomcar_bringup/launch/bringup.launch
echo 'PYTHON HARDWARE DRIVER'
sed -n '1,180p' /home/jetson/yahboomcar_ws/src/yahboomcar_bringup/scripts/Mcnamu_driver.py
echo 'ODOMETRY IMPLEMENTATION'
sed -n '1,230p' /home/jetson/yahboomcar_ws/src/yahboomcar_bringup/src/base.cpp
echo 'DRIVER SERIAL DEFAULT (READ SOURCE ONLY)'
find /home/jetson -maxdepth 6 -name Rosmaster_Lib.py 2>/dev/null | head -n 6
echo 'BOARD UART DEVICES'
ls -l /dev/ttyTHS* /dev/ttyS* 2>/dev/null | head -n 10
