#!/bin/bash
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
export ROS_MASTER_URI=http://127.0.0.1:11312
export ROS_IP=127.0.0.1
unset ROS_HOSTNAME
export ROS_LOG_DIR=/home/jetson/slam_ws/logs/simulation/ros
mkdir -p "$ROS_LOG_DIR"
