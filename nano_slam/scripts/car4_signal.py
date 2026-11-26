#!/usr/bin/env python
"""Grouped TB6612 driving and individual OM1..OM4 diagnostics."""
from __future__ import print_function
import argparse
import json
import sys
from motor_link import (FOUR_PWM_40_LIMIT, FOUR_PWM_50_LIMIT, FOUR_PWM_60_LIMIT, FOUR_PWM_80_LIMIT,
                        FOUR_PWM_HIGH_LIMIT, FOUR_PWM_LIMIT, MotorClient, encode, validate_motion)

PORT='/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0'
MOTOR_BOARD_PORT='/dev/serial/by-path/platform-70090000.xusb-usb-0:2.4:1.0-port0'
DRIVER_MOTORS={'u1':(1,2),'u2':(3,4)}
PROFILES={'standard':(FOUR_PWM_LIMIT,400),'four-pwm-30':(FOUR_PWM_HIGH_LIMIT,400),
          'four-pwm-30-1s':(FOUR_PWM_HIGH_LIMIT,1000),
          'four-pwm-30-5s':(FOUR_PWM_HIGH_LIMIT,5000),
          'four-pwm-30-5s-paired':(FOUR_PWM_HIGH_LIMIT,5000),
          'four-pwm-40-5s-paired':(FOUR_PWM_40_LIMIT,5000),
          'four-pwm-50-5s-paired':(FOUR_PWM_50_LIMIT,5000),
          'four-pwm-60-5s-paired':(FOUR_PWM_60_LIMIT,5000),
          'four-pwm-80-5s-paired':(FOUR_PWM_80_LIMIT,5000)}

def four_duties(action,duty,left=(1,2),signs=(1,1,1,1),max_duty=FOUR_PWM_LIMIT):
    if not 1<=duty<=max_duty or len(left)!=2 or len(set(left))!=2 or any(m not in (1,2,3,4) for m in left):
        raise ValueError('duty 1..%d; left side must have two distinct motor numbers 1..4' % max_duty)
    if len(signs)!=4 or any(s not in (-1,1) for s in signs):
        raise ValueError('four motor signs must each be -1 or 1')
    if action in ('left','right') and tuple(sorted(left)) not in DRIVER_MOTORS.values():
        raise ValueError('turning requires one complete driver per side: left motors 1,2 or 3,4')
    group=DRIVER_MOTORS.get(action,())
    values=[0,0,0,0]
    for index in range(4):
        motor=index+1
        if action in ('forward','backward'):
            values[index]=duty*(1 if action=='forward' else -1)
        elif action=='left':values[index]=duty if motor not in left else 0
        elif action=='right':values[index]=duty if motor in left else 0
        elif motor in group or action=='motor'+str(motor):values[index]=duty
        values[index]*=signs[index]
    return tuple(values)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('motor1','motor2','motor3','motor4','u1','u2','forward','backward','left','right','stop'),
                        help='u1 drives OM1/OM2 together, u2 drives OM3/OM4 together')
    parser.add_argument('--send',action='store_true')
    parser.add_argument('--port',help='STM32 serial port; defaults to the configured board port')
    parser.add_argument('--duty',type=int,help='permille; default 200, or the grouped limit in profiles at 40%% and above')
    parser.add_argument('--profile',choices=sorted(PROFILES),default='standard',
                        help='select the matching STM32 firmware profile')
    parser.add_argument('--ms',type=int,help='duration in milliseconds; default 600 for forward at 50%%, otherwise 250')
    parser.add_argument('--left-motors',default='1,2',help='for turns, select the complete driver on the left: 1,2 or 3,4')
    parser.add_argument('--motor-signs',default='1,1,1,1',help='OM1..4 direction polarity, e.g. 1,-1,1,-1')
    args=parser.parse_args()
    left=tuple(int(v) for v in args.left_motors.split(','))
    signs=tuple(int(v) for v in args.motor_signs.split(','))
    limit,max_ms=PROFILES[args.profile]
    if args.ms is None:
        duration_ms=600 if args.action=='forward' and limit==FOUR_PWM_50_LIMIT else 250
    else:
        duration_ms=args.ms
    paired=args.profile.endswith('-paired')
    diagnostic=args.action.startswith('motor') and (paired or args.profile=='standard')
    duty=args.duty
    if duty is None:
        duty=limit if limit>FOUR_PWM_HIGH_LIMIT and not diagnostic else FOUR_PWM_LIMIT
    duties=four_duties(args.action,duty,left,signs,limit)
    command='PWM_FOUR'
    values=duties+(duration_ms,)
    if diagnostic:
        axis=int(args.action[-1])-1
        command='PWM'
        values=(axis,duties[axis],duration_ms)
    elif paired and (duties[0]!=duties[1] or duties[2]!=duties[3]):
        raise ValueError('paired driver requires identical signed PWM within OM1/OM2 and OM3/OM4')
    if args.action!='stop':validate_motion(command,values,limit,max_ms)
    if not args.send:
        sequence=[('STOP',())] if args.action=='stop' else [
            ('HELLO',()),('STATUS',()),('ARM',()),(command,values),('STOP',())]
        for seq,(name,parameters) in enumerate(sequence,1):
            print(encode(1,seq,name,*parameters).decode('ascii').strip())
        print('DRY_RUN: no serial port opened')
        return
    port=args.port or (MOTOR_BOARD_PORT if limit>=FOUR_PWM_50_LIMIT else PORT)
    c=MotorClient(port)
    try:
        result=c.halt() if args.action=='stop' else c.motion(command,values,duration_ms/1000.+.2,limit,max_ms)
        print(json.dumps({'action':args.action,command.lower():values,'result':result},sort_keys=True))
    finally:c.close()

if __name__=='__main__':
    try:main()
    except (ValueError,RuntimeError,IOError) as exc:
        print('CAR4_SIGNAL_ERROR: '+str(exc),file=sys.stderr);sys.exit(1)
