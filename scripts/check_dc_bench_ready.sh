set -e
python - <<'PY'
from __future__ import print_function
import os,sys
sys.path.insert(0,os.path.expanduser('~/slam_ws/src/nano_slam/scripts'))
from motor_link import MotorClient
c=MotorClient('/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0')
try:
 s=c.connect()
 assert s['bound'] and s['state']=='DISARMED' and not s['enabled'] and not s['busy'],s
 print('DC_BENCH_READY '+str(s))
finally:c.close()
PY
if ps -eo args | grep -Eq '[r]plidarNode|[s]llidar_node'; then
  echo 'LIDAR_DRIVER_RUNNING: stop it before the bench test'; exit 1
fi
echo 'LIDAR_DRIVER_STOPPED'
