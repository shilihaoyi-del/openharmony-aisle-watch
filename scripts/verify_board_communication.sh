set -e
root=/home/jetson/slam_ws/src/nano_slam
echo 'BOARD USB INTERFACE'
port=/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0
ls -l "$port"
python - <<'PY'
from __future__ import print_function
import json,os,sys
sys.path.insert(0,os.path.expanduser('~/slam_ws/src/nano_slam/scripts'))
from motor_link import MotorClient
client=MotorClient('/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0')
try:
    status=client.connect()
    assert status['state']=='DISARMED' and not status['bound'] and not status['enabled'] and not status['busy'],status
    rejected=False
    try:
        client.exchange('ARM')
    except RuntimeError as exc:
        rejected='ERR,ARM,UNBOUND' in str(exc) or 'ARM,UNBOUND' in str(exc)
        print('ARM_REJECTION='+str(exc))
    assert rejected,'Communication image must reject ARM with UNBOUND'
    after=client.exchange('STATUS')
    assert after['state']=='DISARMED' and not after['enabled'] and not after['busy']
    stopped=client.halt()
    report={'physical_board_communication':True,'baud':115200,'status':status,
            'arm_rejected_unbound':rejected,'after_rejection':after,'stop':stopped,
            'motion_commands_sent':False}
    output=os.path.expanduser('~/slam_ws/logs/board_communication_report.json')
    with open(output,'w') as handle:json.dump(report,handle,indent=2)
    print(json.dumps(report,indent=2))
    print('BOARD_COMMUNICATION_VERIFIED '+output)
finally:
    client.close()
PY
