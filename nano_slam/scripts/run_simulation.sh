#!/bin/bash
set -eo pipefail
source "$(dirname "$0")/simulation_env.sh"
mode="${1:-status}"
logs=/home/jetson/slam_ws/logs/simulation
if [[ "$mode" == status ]]; then
  rosnode list
  exit
fi
if [[ "$mode" != mapping && "$mode" != navigation && "$mode" != stop ]]; then
  echo 'Usage: run_simulation.sh mapping|navigation|stop|status'; exit 2
fi
if [[ -f "$logs/launch.pid" ]]; then
  previous="$(cat "$logs/launch.pid")"
  if [[ "$previous" =~ ^[0-9]+$ ]] && kill -0 "$previous" 2>/dev/null; then
    if tr '\0' ' ' < "/proc/$previous/cmdline" | grep -q 'roslaunch nano_slam simulation_'; then
      kill -INT "$previous"
      for i in {1..20}; do
        kill -0 "$previous" 2>/dev/null || break
        [[ "$(awk '{print $3}' "/proc/$previous/stat" 2>/dev/null)" == Z ]] && break
        sleep .5
      done
    else
      echo 'Refusing to signal an unrelated process from an old PID file'; exit 1
    fi
  fi
fi
[[ "$mode" == stop ]] && exit 0
if ! timeout 4 rosnode list >/dev/null 2>&1; then
  nohup roscore -p 11312 > "$logs/master.log" 2>&1 < /dev/null &
  echo "$!" > "$logs/master.pid"
  sleep 4
fi
if [[ "$mode" == navigation && ! -f /home/jetson/maps/sim_room.yaml ]]; then
  echo 'First run simulation mapping and save sim_room.yaml'; exit 1
fi
nohup roslaunch nano_slam "simulation_${mode}.launch" > "$logs/$mode.log" 2>&1 < /dev/null &
echo "$!" > "$logs/launch.pid"
echo "$mode" > "$logs/mode"
sleep 5
rosnode list
echo "SIMULATION_MODE=$mode (master port 11312; real robot master 11311 is separate)"
