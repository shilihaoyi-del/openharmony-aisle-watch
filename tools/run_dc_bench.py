"""One 20% / 250ms motor test, with independent encoder and output readback."""
import argparse
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
sys.stdout.reconfigure(encoding='utf-8',errors='replace')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--axis',type=int,choices=(0,1),default=0)
    axis=parser.parse_args().axis
    stamp=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    folder=ROOT/'artifacts/dc_bench'/stamp.strftime('%Y%m%d-%H%M%S')
    folder.mkdir(parents=True,exist_ok=False)
    report={'time':stamp.isoformat(),'axis':axis,'duty_permille':200,'duration_ms':250,
            'motion_sent':None,'motion_attempted':False,'completed':False,'encoder_change_confirmed':False}
    def save(): (folder/'bench_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    def registers():
        addresses=[0x40000824,0x40000024,0x40000400,0x40000420,0x4001080c,0x4001100c]
        args=[str(CLI),'-c','SN='+SN,'SWD','HOTPLUG','FREQ=100']
        for address in addresses: args+=['-r32',hex(address),'1']
        result=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=25)
        output=result.stdout.decode('utf-8',errors='replace')
        with (folder/'registers.log').open('a',encoding='utf-8') as handle:handle.write(output+'\n')
        if result.returncode or not re.search(r'Device ID:\s*0x414\b',output,re.I):
            raise RuntimeError('ST-Link target read failed before/after motion')
        values={}
        for address in addresses:
            match=re.search(r'0x%08x\s*:\s*([0-9a-f]{8})' % address,output,re.I)
            if not match:raise RuntimeError('Register absent: '+hex(address))
            values[hex(address)]=int(match.group(1),16)
        return values
    save()
    try:
        before=registers();report['registers_before']=before;save()
        client=paramiko.SSHClient();client.load_host_keys(str(ROOT/'tools/known_hosts'))
        try:
            client.connect(os.environ.get("JETSON_HOST", "jetson.local"),username='jetson',password=os.environ['JETSON_SSH_PASSWORD'],
                           look_for_keys=False,allow_agent=False,timeout=10)
            source='''from __future__ import print_function
import os,sys,json,time,subprocess
sys.path.insert(0,os.path.expanduser('~/slam_ws/src/nano_slam/scripts'))
from motor_link import MotorClient
AXIS=__TEST_AXIS__
processes=subprocess.check_output(['ps','-eo','comm']).decode()
if 'rplidarNode' in processes or 'sllidar_node' in processes:
    raise RuntimeError('Lidar must remain stopped')
port='/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0'
c=MotorClient(port)
result={}
try:
    result['before']=c.connect()
    assert result['before']['bound'] and result['before']['state']=='DISARMED'
    assert not result['before']['enabled'] and not result['before']['busy']
    started=time.time()
    c.motion('PWM',(AXIS,200,250),.45)
    result['elapsed_host_seconds']=time.time()-started
    result['finite_motion_completed']=True
finally:c.close()
after=MotorClient(port)
try:
    result['after']=after.connect()
    assert result['after']['state']=='DISARMED' and not result['after']['enabled'] and not result['after']['busy']
finally:after.close()
print('BENCH_REPORT_JSON='+json.dumps(result))
'''
            source=source.replace('__TEST_AXIS__',str(axis))
            report['motion_attempted']=True;save()
            stdin,stdout,stderr=client.exec_command('python -u -',timeout=15)
            stdin.write(source);stdin.channel.shutdown_write()
            out=stdout.read().decode('utf-8',errors='replace');err=stderr.read().decode('utf-8',errors='replace')
            code=stdout.channel.recv_exit_status()
            (folder/'serial.log').write_text(out+'\n'+err,encoding='utf-8')
            if code:raise RuntimeError('Bounded motor command failed; inspect serial.log. No automatic retry.')
            match=re.search(r'BENCH_REPORT_JSON=(.+)',out)
            if not match:raise RuntimeError('No serial test result')
            report['serial']=json.loads(match.group(1));report['motion_sent']=True
            report['completed']=report['serial']['finite_motion_completed']
            save()
        finally:client.close()
        after=registers();report['registers_after']=after
        delta=lambda a,b:((b-a+32768)%65536)-32768
        report['motor1_encoder_delta']=delta(before['0x40000824']&65535,after['0x40000824']&65535)
        report['motor2_encoder_delta']=delta(before['0x40000024']&65535,after['0x40000024']&65535)
        report['encoder_change_confirmed']=report['motor1_encoder_delta' if axis==0 else 'motor2_encoder_delta']!=0
        report['other_motor_stationary']=report['motor2_encoder_delta' if axis==0 else 'motor1_encoder_delta']==0
        report['outputs_stopped']=(after['0x40000400']&1)==0 and after['0x40000420']==0 and (after['0x4001080c']&0xf0)==0 and (after['0x4001100c']&0x30)==0
        save()
        if not report['outputs_stopped']:raise RuntimeError('Motor output stop readback failed')
        print(json.dumps(report,indent=2))
        print('BENCH_REPORT='+str(folder/'bench_report.json'))
    except Exception as exc:
        report['error']=str(exc);save();raise

if __name__=='__main__':main()
