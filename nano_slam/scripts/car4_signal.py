#!/usr/bin/env python
"""Four independent OM1..OM4 motor signals for the dual TB6612 4WD board."""
from __future__ import print_function
import argparse
import json
import sys
from motor_link import MotorClient,encode,validate_motion

PORT='/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0'

def four_duties(action,duty,left=(1,2),signs=(1,1,1,1)):
    if not 1<=duty<=200 or len(left)!=2 or len(set(left))!=2 or any(m not in (1,2,3,4) for m in left):
        raise ValueError('duty 1..200; left side must have two distinct motor numbers 1..4')
    if len(signs)!=4 or any(s not in (-1,1) for s in signs):
        raise ValueError('four motor signs must each be -1 or 1')
    values=[0,0,0,0]
    for index in range(4):
        motor=index+1
        if action in ('forward','backward'):
            values[index]=duty*(1 if action=='forward' else -1)
        elif action=='left':values[index]=duty if motor not in left else 0
        elif action=='right':values[index]=duty if motor in left else 0
        elif action=='motor'+str(motor):values[index]=duty
        values[index]*=signs[index]
    return tuple(values)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('motor1','motor2','motor3','motor4','forward','backward','left','right','stop'))
    parser.add_argument('--send',action='store_true')
    parser.add_argument('--port',default=PORT)
    parser.add_argument('--duty',type=int,default=200,help='permille; maximum 200 = 20 percent')
    parser.add_argument('--ms',type=int,default=250,help='finite output, 1..400 ms')
    parser.add_argument('--left-motors',default='1,2',help='left-side motor numbers, e.g. 1,3; other two form right side')
    parser.add_argument('--motor-signs',default='1,1,1,1',help='OM1..4 direction polarity, e.g. 1,-1,1,-1')
    args=parser.parse_args()
    left=tuple(int(v) for v in args.left_motors.split(','))
    signs=tuple(int(v) for v in args.motor_signs.split(','))
    values=four_duties(args.action,args.duty,left,signs)+(args.ms,)
    if args.action!='stop':validate_motion('PWM_FOUR',values)
    if not args.send:
        sequence=[('STOP',())] if args.action=='stop' else [
            ('HELLO',()),('STATUS',()),('ARM',()),('PWM_FOUR',values),('STOP',())]
        for seq,(name,parameters) in enumerate(sequence,1):
            print(encode(1,seq,name,*parameters).decode('ascii').strip())
        print('DRY_RUN: no serial port opened')
        return
    c=MotorClient(args.port)
    try:
        result=c.halt() if args.action=='stop' else c.motion('PWM_FOUR',values,args.ms/1000.+.2)
        print(json.dumps({'action':args.action,'pwm_four':values,'result':result},sort_keys=True))
    finally:c.close()

if __name__=='__main__':
    try:main()
    except (ValueError,RuntimeError,IOError) as exc:
        print('CAR4_SIGNAL_ERROR: '+str(exc),file=sys.stderr);sys.exit(1)
