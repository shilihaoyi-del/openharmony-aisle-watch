#!/usr/bin/env bash
set -eo pipefail

directory=$(cd -- "$(dirname -- "$0")" && pwd)
session=${1:?supply a new session directory for the map and bag}
port=${ROS_PORT:-11321}
receiver=${WS63_RECEIVER_PORT:-/dev/serial/by-path/platform-70090000.xusb-usb-0:2.3:1.0-port0}
if [[ -z ${WS63_RECEIVER_PORT:-} && ! -e $receiver ]]; then
  receiver=/dev/serial/by-path/platform-70090000.xusb-usb-0:2.2.3:1.0-port0
fi
front_center=${WS63_FRONT_CENTER:-175}
front_width=${WS63_FRONT_WIDTH:-110}
near_range=${WS63_MIN_RANGE:-0.40}
far_range=${WS63_MAX_RANGE:-10.0}
source /opt/ros/melodic/setup.bash
source /home/jetson/slam_ws/devel/setup.bash
export ROS_MASTER_URI="http://127.0.0.1:$port"
export ROS_IP=127.0.0.1

mkdir -p -- "$session"
if timeout 2 rosparam list >/dev/null 2>&1; then
  echo "ROS master port $port is already in use" >&2
  exit 1
fi

pids=()
pipeline_started=false
cleanup() {
  for ((i=${#pids[@]}-1; i>=0; --i)); do
    local pid=${pids[i]}
    kill -INT "$pid" 2>/dev/null || true
    for ((j=0; j<20; ++j)); do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.1
    done
    kill -TERM "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
  done
  if "$pipeline_started" && [[ -x /home/jetson/slam_ws/logs/lidar_control/lidar_stop ]]; then
    timeout 8 /home/jetson/slam_ws/logs/lidar_control/lidar_stop >"$session/lidar_stop.log" 2>&1 || true
  fi
}
trap cleanup EXIT
trap 'exit 0' INT TERM

roscore -p "$port" >"$session/roscore.log" 2>&1 &
pids+=("$!")
for ((i=0; i<25; ++i)); do
  if timeout 1 rosparam list >/dev/null 2>&1; then break; fi
  sleep 0.2
done
timeout 2 rosparam list >/dev/null 2>&1

if [[ ${WS63_CHANGE_WATCH:-0} == 1 ]]; then
  if [[ ! -c /dev/ws63-contact || ! -c $receiver ]]; then
    echo "Connect both WS63 serial ports before starting the monitor" >&2
    exit 1
  fi
  rm -f -- "$session/watch-ready"
  range_args=()
  if [[ -n ${WS63_WATCH_DETECT_RANGE:-} ]]; then
    range_args=(--detect-range "$WS63_WATCH_DETECT_RANGE")
  fi
  python -u "$directory/change_gateway.py" --receive-port "$receiver" \
    --output "$directory/dashboard/watch.json" --ready-file "$session/watch-ready" \
    --center "$front_center" --width "$front_width" --near "$near_range" --far "$far_range" \
    --roi-first "${WS63_WATCH_ROI_FIRST:-12}" --roi-count "${WS63_WATCH_ROI_COUNT:-48}" \
    "${range_args[@]}" \
    >"$session/gateway.log" 2>&1 &
  gateway=$!
  pids+=("$gateway")
  for ((i=0; i<40; ++i)); do
    if [[ -e "$session/stop" ]]; then exit 0; fi
    if [[ -s "$session/watch-ready" ]] || ! kill -0 "$gateway" 2>/dev/null; then break; fi
    sleep 0.5
  done
  if [[ ! -s "$session/watch-ready" ]]; then
    echo "No WS63 change report via SLE; see $session/gateway.log" >&2
    exit 1
  fi

  rosbag record -O "$session/scans.bag" /scan /ws63/change /ws63/change_events >"$session/bag.log" 2>&1 &
  pids+=("$!")
  roslaunch nano_slam mapping.launch start_driver:=true start_mapper:=false >"$session/mapping.log" 2>&1 &
  pids+=("$!")
  pipeline_started=true
else
  mapping_frame=laser
  map_input=/scan_sle
  static_args=()
  default_bins=72
  if [[ ! $front_width =~ ^0+([.]0*)?$ ]]; then
    mapping_frame=laser_front
    default_bins=144
  fi
  if [[ ${WS63_STATIC_SWEEP:-0} == 1 ]]; then
    map_input=/scan_sle_static
    static_args=(--stationary-output-topic "$map_input")
    if [[ $mapping_frame == laser_front ]]; then default_bins=350; fi
  fi
  bins=${WS63_SCAN_BINS:-$default_bins}

  python -u "$directory/fusion_gateway.py" --ros --receive-port "$receiver" \
    --front-center "$front_center" --front-width "$front_width" --min-range "$near_range" --max-range "$far_range" \
    --front-frame laser_front --bins "$bins" \
    "${static_args[@]}" \
    --scan-output-topic /scan_sle --output-topic /ws63/fusion --link-topic /ws63/link >"$session/gateway.log" 2>&1 &
  pids+=("$!")

  rosbag record -O "$session/scans.bag" /scan /scan_sle /scan_sle_static /slam_out_pose /tf_static /ws63/link >"$session/bag.log" 2>&1 &
  pids+=("$!")

  roslaunch nano_slam mapping.launch start_driver:=true scan_topic:="$map_input" mapping_frame:="$mapping_frame" \
    map_pub_period:=0.5 map_update_distance:=0.07 map_update_angle:=0.035 \
    >"$session/mapping.log" 2>&1 &
  pids+=("$!")
  pipeline_started=true

  if [[ -f "$directory/dashboard/ros_state.py" ]]; then
    python -u "$directory/dashboard/ros_state.py" --output "$directory/dashboard/live.json" \
      --scan-topic "$map_input" \
      >"$session/dashboard.log" 2>&1 &
    pids+=("$!")
  fi
fi

while [[ ! -e "$session/stop" ]]; do
  for pid in "${pids[@]}"; do
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "A pipeline process exited; inspect logs in $session" >&2
      exit 1
    fi
  done
  sleep 0.5
done
