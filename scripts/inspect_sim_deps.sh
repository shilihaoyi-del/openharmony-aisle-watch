source /opt/ros/melodic/setup.bash
echo 'RESOURCES'
df -h /
free -h
echo 'NAVIGATION CANDIDATE VERSIONS'
apt-cache policy ros-melodic-move-base ros-melodic-amcl ros-melodic-map-server ros-melodic-gmapping ros-melodic-dwa-local-planner
echo 'TARGETED INSTALL SIMULATION'
LC_ALL=C apt-get -s install --no-install-recommends ros-melodic-move-base ros-melodic-amcl ros-melodic-map-server ros-melodic-gmapping ros-melodic-dwa-local-planner | tail -n 35
echo 'PYTHON PACKAGES'
python -c 'import rospy, numpy, yaml; from PIL import Image; import actionlib; print("ROS_PYTHON_READY")'
echo 'SUDO CAPABILITY'
sudo -n true 2>/dev/null && echo SUDO_NOPASSWD || true
