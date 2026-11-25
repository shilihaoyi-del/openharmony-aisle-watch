"""Send three finite open-loop car signals once, then verify stopped outputs."""
import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import paramiko

ROOT=Path(__file__).resolve().parents[1]
CLI=Path('D:/ST-LINK/ST-LINK Utility/ST-LINK_CLI.exe')
SN='34FF74064D56383341362443'

def main():
    sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    stamp=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    folder=ROOT/'artifacts/car_signals'/stamp.strftime('%Y%m%d-%H%M%S')
    folder.mkdir(parents=True,exist_ok=False)
    report={'time':stamp.isoformat(),'motion_attempted':False,'completed':False,
            'left_channel':'Motor1','right_channel':'Motor2',
            'physical_forward_direction_confirmed':False,'encoder_feedback_used':False}
    def save():
        (folder/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    save()
    client=paramiko.SSHClient();client.load_host_keys(str(ROOT/'tools/known_hosts'))
    try:
        client.connect(os.environ.get("JETSON_HOST", "jetson.local"),username='jetson',password=os.environ['JETSON_SSH_PASSWORD'],
                       look_for_keys=False,allow_agent=False,timeout=10)
        source='''from __future__ import print_function
import json,os,subprocess,sys,time
sys.path.insert(0,os.path.expanduser('~/slam_ws/src/nano_slam/scripts'))
from motor_link import MotorClient
from car_signal import duties,PORT
processes=subprocess.check_output(['ps','-eo','comm']).decode()
assert 'rplidarNode' not in processes and 'sllidar_node' not in processes,'Lidar is running'
for action in ('forward','left','right'):
    c=MotorClient(PORT)
    try:
        before=c.connect()
        assert before['bound'] and before['state']=='DISARMED' and not before['enabled'] and not before['busy'],before
        values=duties(action,200)+(250,)
        result=c.motion('PWM_PAIR',values,.45)
        assert result['started']['state']=='PWM_TEST' and result['started']['busy'] and result['started']['enabled'],result
        assert result['completed']['state']=='ARMED' and not result['completed']['busy'],result
        assert result['stopped']['state']=='DISARMED' and not result['stopped']['enabled'] and not result['stopped']['busy'],result
        print('ACTION_JSON='+json.dumps({'action':action,'pwm_pair':values,'before':before,'result':result}))
        sys.stdout.flush()
    finally:c.close()
    time.sleep(1.5)
c=MotorClient(PORT)
try:
    status=c.connect()
    assert status['state']=='DISARMED' and not status['enabled'] and not status['busy'],status
    print('FINAL_JSON='+json.dumps(status))
finally:c.close()
'''
        report['motion_attempted']=True;save()
        stdin,stdout,stderr=client.exec_command('python -u -',timeout=20)
        stdin.write(source);stdin.channel.shutdown_write()
        out=stdout.read().decode('utf-8',errors='replace')
        err=stderr.read().decode('utf-8',errors='replace')
        code=stdout.channel.recv_exit_status()
        (folder/'serial.log').write_text(out+'\n'+err,encoding='utf-8')
        report['actions']=[json.loads(line[len('ACTION_JSON='):]) for line in out.splitlines() if line.startswith('ACTION_JSON=')]
        save()
        if code:raise RuntimeError('Finite car test failed; commands will not be automatically retried. See serial.log')
        assert len(report['actions'])==3,'Missing action results'
        report['final_status']=json.loads(next(line[len('FINAL_JSON='):] for line in out.splitlines() if line.startswith('FINAL_JSON=')))
        # Read GPIO/timer output state independently of the serial protocol.
        addresses=[0x40000400,0x40000420,0x4001080c,0x4001100c]
        command=[str(CLI),'-c','SN='+SN,'SWD','HOTPLUG','FREQ=100']
        for address in addresses:command+=['-r32',hex(address),'1']
        result=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=25)
        output=result.stdout.decode('utf-8',errors='replace')
        (folder/'stopped_registers.log').write_text(output,encoding='utf-8')
        if result.returncode or not re.search(r'Device ID:\s*0x414\b',output,re.I):
            raise RuntimeError('ST-Link stopped-output readback failed')
        registers={}
        for address in addresses:
            match=re.search(r'0x%08x\s*:\s*([0-9a-f]{8})'%address,output,re.I)
            if not match:raise RuntimeError('Missing register '+hex(address))
            registers[hex(address)]=int(match.group(1),16)
        report['stopped_registers']=registers
        report['outputs_stopped']=(registers['0x40000400']&1)==0 and registers['0x40000420']==0 and (registers['0x4001080c']&0xf0)==0 and (registers['0x4001100c']&0x30)==0
        if not report['outputs_stopped']:raise RuntimeError('Motor output stop readback mismatch')
        report['completed']=True;save()
        print(json.dumps(report,indent=2))
        print('REPORT='+str(folder/'report.json'))
    except Exception as exc:
        report['error']=str(exc);save();raise
    finally:client.close()

if __name__=='__main__':main()
