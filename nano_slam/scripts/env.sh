#!/bin/bash
source /opt/ros/melodic/setup.bash
source /home/jetson/slam_ws/devel/setup.bash
export ROS_MASTER_URI=http://localhost:11311
# A source-only package needs no compile step; also works before catkin_make.
NANO_SLAM_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export ROS_PACKAGE_PATH="$(dirname "$NANO_SLAM_DIR"):$ROS_PACKAGE_PATH"
