"""One finite pulse per channel, observing live MCU PWM/direction registers."""
import datetime
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time
import paramiko

ROOT=Path(__file__).resolve().parents[1]
CLI='D:/ST-LINK/ST-LINK Utility/ST-LINK_CLI.exe'
SN='34FF74064D56383341362443'
ADDRESSES=(0x40000400,0x40000420,0x40000434,0x40000438,
           0x4001080c,0x4001100c,0x40010800,0x40011000,0x40010004)

def reader():
    args=[CLI,'-c','SN='+SN,'SWD','HOTPLUG','FREQ=100']
    for addr in ADDRESSES:args+=['-r32',hex(addr),'1']
    return subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)

def parse_output(process,folder,name):
    out=process.communicate(timeout=15)[0]
    (folder/(name+'.log')).write_bytes(out)
    text=out.decode('utf-8',errors='replace')
    if process.returncode or not re.search(r'Device ID:\s*0x414\b',text,re.I):
        raise RuntimeError('ST-Link read failed: '+name)
    registers={}
    for addr in ADDRESSES:
        match=re.search(r'0x%08x\s*:\s*([0-9a-f]{8})'%addr,text,re.I)
        if not match:raise RuntimeError('Missing register: '+hex(addr))
        registers[hex(addr)]=int(match.group(1),16)
    return registers

def main():
    sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    stamp=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    folder=ROOT/'artifacts/car_diagnosis'/stamp.strftime('%Y%m%d-%H%M%S')
    folder.mkdir(parents=True,exist_ok=False)
    report={'time':stamp.isoformat(),'actions':[],'completed':False,
            'electrical_voltage_measured':False,'physical_motor_rotation_confirmed':False}
    def save():
        (folder/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    save()
    client=paramiko.SSHClient();client.load_host_keys(str(ROOT/'tools/known_hosts'))
    try:
        client.connect(os.environ.get("JETSON_HOST", "jetson.local"),username='jetson',password=os.environ['JETSON_SSH_PASSWORD'],
                       look_for_keys=False,allow_agent=False,timeout=10)
        # Verify probe access before any motor command.
        report['before']=parse_output(reader(),folder,'before');save()
        for axis in (0,1):
            source='''from __future__ import print_function
import json,os,subprocess,sys
sys.path.insert(0,os.path.expanduser('~/slam_ws/src/nano_slam/scripts'))
from motor_link import MotorClient
p=subprocess.check_output(['ps','-eo','comm']).decode()
assert 'rplidarNode' not in p and 'sllidar_node' not in p,'Lidar is running'
c=MotorClient('/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0')
try:
    s=c.connect()
    assert s['bound'] and s['state']=='DISARMED' and not s['enabled'] and not s['busy'],s
    print('READY');sys.stdout.flush()
    if sys.stdin.readline().strip()!='GO':raise RuntimeError('No host trigger')
    result=c.motion('PWM',(__AXIS__,200,400),.6)
    print('RESULT='+json.dumps(result));sys.stdout.flush()
finally:c.close()
'''.replace('__AXIS__',str(axis))
            stdin,stdout,stderr=client.exec_command('python -u -c '+shlex.quote(source),timeout=15)
            ready=stdout.readline().strip()
            if ready!='READY':
                raise RuntimeError('Board not ready: '+ready+' '+stderr.read().decode(errors='replace'))
            item={'axis':axis,'channel':'Motor'+str(axis+1),'duty_permille':200,'duration_ms':400,'motion_attempted':False}
            report['actions'].append(item);save()
            monitor=reader()
            try:
                item['motion_attempted']=True;save()
                print('Sending Motor%d: 20 percent, 400 ms'%(axis+1),flush=True)
                stdin.write('GO\n');stdin.flush();stdin.channel.shutdown_write()
                item['live_registers']=parse_output(monitor,folder,'motor%d_live'%(axis+1))
            finally:
                if monitor.poll() is None:monitor.communicate(timeout=15)
            out=stdout.read().decode(errors='replace');err=stderr.read().decode(errors='replace')
            code=stdout.channel.recv_exit_status()
            (folder/('motor%d_serial.log'%(axis+1))).write_text(out+'\n'+err,encoding='utf-8')
            if code:raise RuntimeError('Finite motor command failed; no automatic retry')
            item['serial']=json.loads(next(line[7:] for line in out.splitlines() if line.startswith('RESULT=')))
            r=item['live_registers']
            item['live_pwm_observed']=(r['0x40000400']&1)==1 and r['0x40000420']==(1 if axis==0 else 16) and r['0x40000434']==(160 if axis==0 else 0) and r['0x40000438']==(160 if axis==1 else 0)
            item['live_direction_observed']=(r['0x4001080c']&0x30)==(0x20 if axis==0 else 0) and (r['0x4001100c']&0x30)==(0x10 if axis==1 else 0)
            stopped=item['serial']['stopped']
            assert stopped['state']=='DISARMED' and not stopped['busy'] and not stopped['enabled'],stopped
            item['after']=parse_output(reader(),folder,'motor%d_after'%(axis+1))
            r=item['after']
            item['outputs_stopped']=(r['0x40000400']&1)==0 and r['0x40000420']==0 and (r['0x4001080c']&0xf0)==0 and (r['0x4001100c']&0x30)==0
            if not item['outputs_stopped']:raise RuntimeError('Stopped-output readback mismatch')
            save();time.sleep(2)
        report['completed']=True;save()
        print(json.dumps(report,indent=2))
        print('REPORT='+str(folder/'report.json'))
    except Exception as exc:
        report['error']=str(exc);save();raise
    finally:client.close()

if __name__=='__main__':main()
