#!/usr/bin/env python
"""Finite open-loop left/right DC motor signals; Python 2.7 and 3."""
from __future__ import print_function
import argparse
import json
import sys
from motor_link import MotorClient, encode, validate_motion

PORT='/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0'

def duties(action,duty,left_sign=1,right_sign=1,swap=False):
    if not 1<=duty<=200 or left_sign not in (-1,1) or right_sign not in (-1,1):
        raise ValueError('duty 1..200 permille; direction signs must be -1 or 1')
    # Gentle pivot turns: stop the inner side and power the outer side.
    patterns={'forward':(duty,duty),'backward':(-duty,-duty),
              'left':(0,duty),'right':(duty,0),'stop':(0,0)}
    left,right=patterns[action]
    pair=(left*left_sign,right*right_sign)
    return pair[::-1] if swap else pair

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('forward','backward','left','right','stop'))
    parser.add_argument('--send',action='store_true',help='transmit to the board; otherwise show frames only')
    parser.add_argument('--port',default=PORT)
    parser.add_argument('--duty',type=int,default=200,help='permille, 200 = 20 percent')
    parser.add_argument('--ms',type=int,default=250,help='1..400 ms; output stops on the MCU timer')
    parser.add_argument('--left-sign',type=int,choices=(-1,1),default=1)
    parser.add_argument('--right-sign',type=int,choices=(-1,1),default=1)
    parser.add_argument('--swap',action='store_true',help='Motor2 is left, Motor1 is right')
    args=parser.parse_args()
    pair=duties(args.action,args.duty,args.left_sign,args.right_sign,args.swap)
    values=pair+(args.ms,)
    if args.action!='stop':validate_motion('PWM_PAIR',values)
    if not args.send:
        sequence=[('STOP',())] if args.action=='stop' else [
            ('HELLO',()),('STATUS',()),('ARM',()),('PWM_PAIR',values),('STOP',())]
        for seq,(command,parameters) in enumerate(sequence,1):
            print(encode(1,seq,command,*parameters).decode('ascii').strip())
        print('DRY_RUN: no serial port opened')
        return
    client=MotorClient(args.port)
    try:
        if args.action=='stop':
            print(json.dumps(client.halt(),sort_keys=True))
        else:
            client.motion('PWM_PAIR',values,args.ms/1000.+.2)
            print('ACTION_COMPLETED '+args.action+'; PWM_PAIR='+str(values)+'; STOP_ACK_RECEIVED')
    finally:client.close()

if __name__=='__main__':
    try:main()
    except (ValueError,RuntimeError,IOError) as exc:
        print('CAR_SIGNAL_ERROR: '+str(exc),file=sys.stderr)
        sys.exit(1)
