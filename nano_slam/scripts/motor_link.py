#!/usr/bin/env python
"""J1 motor protocol and explicit, bounded serial bench client (Python 2.7/3)."""
from __future__ import print_function
import argparse
import binascii
import math
import random
import re
import sys
import time

BAUD = 115200
MAX_LINE = 160
MAX_RATE = 200
MAX_JOG_STEPS = 200
MAX_MOTION_SECONDS = 2.0
FOUR_PWM_LIMIT = 200
FOUR_PWM_HIGH_LIMIT = 300
FOUR_PWM_40_LIMIT = 400
FOUR_PWM_50_LIMIT = 500
FOUR_PWM_60_LIMIT = 600
FOUR_PWM_80_LIMIT = 800
CLOCK = getattr(time, 'monotonic', time.time)

def encode(session, seq, command, *args):
    if not 1 <= int(session) <= 0xffffffff or not 1 <= int(seq) <= 0xffffffff:
        raise ValueError('session and sequence must be uint32, nonzero')
    fields = ['J1', str(int(session)), str(int(seq)), str(command)] + [str(a) for a in args]
    if any(not re.match(r'\A[A-Za-z0-9_\-]+\Z', f) for f in fields):
        raise ValueError('invalid field characters')
    body = ','.join(fields).encode('ascii')
    frame = b'$' + body + ('*%04X\n' % binascii.crc_hqx(body, 0xffff)).encode('ascii')
    if len(frame) > MAX_LINE:
        raise ValueError('frame too long')
    return frame

def decode(frame):
    if isinstance(frame, bytes):
        frame = frame.decode('ascii')
    if len(frame) > MAX_LINE or not re.match(r'\A\$[A-Za-z0-9_,\-]+\*[0-9A-F]{4}\r?\n\Z', frame):
        raise ValueError('invalid frame')
    body, checksum = frame[1:].rstrip('\r\n').split('*')
    if binascii.crc_hqx(body.encode('ascii'), 0xffff) != int(checksum, 16):
        raise ValueError('CRC mismatch')
    fields = body.split(',')
    if len(fields) < 4 or fields[0] != 'J1' or any(not f for f in fields):
        raise ValueError('invalid fields')
    if not fields[1].isdigit() or not fields[2].isdigit():
        raise ValueError('invalid identifiers')
    session, seq = int(fields[1]), int(fields[2])
    if not 1 <= session <= 0xffffffff or not 1 <= seq <= 0xffffffff:
        raise ValueError('identifier out of range')
    return session, seq, fields[3:]

def validate_motion(command, args, four_pwm_limit=FOUR_PWM_LIMIT, four_pwm_ms=400):
    if command == 'JOG':
        axis, steps, rate = args
        if axis not in (0, 1) or not 1 <= abs(steps) <= MAX_JOG_STEPS or not 1 <= rate <= MAX_RATE:
            raise ValueError('JOG: axis 0/1, |steps| 1..200, rate 1..200 pulses/s')
        if abs(steps) / float(rate) > 1.5:
            raise ValueError('JOG nominal duration must be <=1.5 seconds (2 second hard cap)')
    elif command == 'WHEELS':
        if any(abs(v) > MAX_RATE for v in args):
            raise ValueError('WHEELS: each axis limited to +/-200 pulses/s')
    elif command == 'PWM':
        axis,duty,duration=args
        if axis not in (0,1,2,3) or not 1<=abs(duty)<=200 or not 1<=duration<=400:
            raise ValueError('PWM: axis 0..3, duty +/-1..200 permille, duration 1..400 ms')
    elif command == 'PWM_PAIR':
        left,right,duration=args
        if abs(left)>200 or abs(right)>200 or not (left or right) or not 1<=duration<=400:
            raise ValueError('PWM_PAIR: duties -200..200 permille, not both zero, duration 1..400 ms')
    elif command == 'PWM_FOUR':
        if (four_pwm_limit, four_pwm_ms) not in ((FOUR_PWM_LIMIT,400),(FOUR_PWM_HIGH_LIMIT,400),
                                                (FOUR_PWM_HIGH_LIMIT,1000),(FOUR_PWM_HIGH_LIMIT,5000),
                                                (FOUR_PWM_40_LIMIT,5000),(FOUR_PWM_50_LIMIT,5000),
                                                (FOUR_PWM_60_LIMIT,5000),(FOUR_PWM_80_LIMIT,5000)):
            raise ValueError('unsupported four-channel PWM profile')
        values=args[:4]
        if len(args)!=5 or any(abs(v)>four_pwm_limit for v in values) or not any(values) or not 1<=args[4]<=four_pwm_ms:
            raise ValueError('PWM_FOUR: duties within +/- %d permille, not all zero, duration 1..%d ms' %
                             (four_pwm_limit,four_pwm_ms))
    else:
        raise ValueError('unsupported motion command: '+command)

class MotorClient(object):
    def __init__(self, port, session=None, serial_factory=None):
        self.session = random.SystemRandom().randint(1, 0xffffffff) if session is None else session
        if not 1 <= self.session <= 0xffffffff:
            raise ValueError('session must be uint32, nonzero')
        self.seq = 0
        if serial_factory is None:
            import serial
            serial_factory = serial.Serial
        self.serial = serial_factory(port=None, baudrate=BAUD, timeout=.05, write_timeout=.2)
        self.serial.dtr = False
        self.serial.rts = False
        self.serial.port = port
        self.serial.open()
    def exchange(self, command, *args):
        self.seq += 1
        frame = encode(self.session, self.seq, command, *args)
        # Deliberately no retry: a timed-out motion command might already have executed.
        if self.serial.write(frame) != len(frame):
            raise IOError('short serial write')
        deadline = CLOCK() + .8
        buffer = b''
        encoder_frame = None
        while CLOCK() < deadline:
            byte = self.serial.read(1)
            if not byte:
                continue
            if byte == b'$':
                buffer = byte
            elif buffer:
                buffer += byte
            if len(buffer) > MAX_LINE:
                buffer = b''
            if byte == b'\n' and buffer:
                if command == 'ENC' and buffer.startswith((b'$J1ENC1,', b'$J1ENC2,')):
                    encoder_frame, buffer = buffer, b''
                    continue
                try:
                    session, seq, reply = decode(buffer)
                except (ValueError, UnicodeError):
                    buffer = b''
                    continue
                buffer = b''
                if session != self.session or seq != self.seq:
                    continue
                if reply[0] == 'ERR':
                    raise RuntimeError('board rejected command: ' + ','.join(reply[1:]))
                if len(reply) != 6 or reply[0] != 'ACK' or reply[1] != command:
                    continue
                if reply[3] not in ('0','1') or reply[4] not in ('0','1') or reply[5] not in ('0','1'):
                    continue
                result = {'command':reply[1], 'state':reply[2], 'bound':reply[3]=='1',
                          'enabled':reply[4]=='1', 'busy':reply[5]=='1'}
                if command == 'ENC':
                    if encoder_frame is None:
                        raise RuntimeError('encoder response missing sample')
                    result['encoder_frame'] = encoder_frame
                return result
        raise RuntimeError('no matching J1 reply; motion is NOT retried')
    def connect(self):
        self.exchange('HELLO')
        return self.exchange('STATUS')
    def halt(self):
        return self.exchange('STOP')
    def motion(self, command, args, duration, four_pwm_limit=FOUR_PWM_LIMIT, four_pwm_ms=400):
        validate_motion(command, args, four_pwm_limit, four_pwm_ms)
        max_duration = MAX_MOTION_SECONDS
        if command == 'PWM_FOUR':
            max_duration = max(max_duration, args[4] / 1000.0 + .2)
        if not 0 < duration <= max_duration:
            raise ValueError('bench duration must be >0 and <=%g seconds' % max_duration)
        status = self.connect()
        if not status['bound']:
            raise RuntimeError('firmware has no bound motor hardware interface')
        try:
            armed = self.exchange('ARM')
            if not armed['enabled'] or armed['state'] != 'ARMED':
                raise RuntimeError('board did not enter the enabled ARMED state')
            started = self.exchange(command, *args)
            reply = started
            deadline = CLOCK() + duration
            finite = command in ('JOG','PWM','PWM_PAIR','PWM_FOUR')
            complete = not finite
            while CLOCK() < deadline:
                time.sleep(min(.08, max(0, deadline-CLOCK())))
                reply = self.exchange('KEEP' if finite else 'WHEELS',
                                      *(() if finite else args))
                if finite and not reply['busy']:
                    complete = True
                    break
            if not complete:
                raise RuntimeError('Finite motion did not report completion before its bounded deadline')
        finally:
            # Host shutdown is best-effort; the board's independent watchdog is mandatory.
            stopped = self.halt()
        return {'started':started,'completed':reply,'stopped':stopped}
    def close(self):
        self.serial.close()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', help='explicit board port; never selected automatically')
    parser.add_argument('--send', action='store_true', help='open the port and transmit; default only prints frames')
    parser.add_argument('--session', type=int, default=None)
    sub = parser.add_subparsers(dest='action')
    for action in ('hello','status','stop','estop','clear','enc'):
        sub.add_parser(action)
    jog = sub.add_parser('jog')
    jog.add_argument('--axis', type=int, default=0)
    jog.add_argument('--steps', type=int, default=50)
    jog.add_argument('--rate', type=int, default=100)
    wheels = sub.add_parser('wheels')
    wheels.add_argument('--left', type=int, required=True)
    wheels.add_argument('--right', type=int, required=True)
    wheels.add_argument('--seconds', type=float, default=.5)
    pwm = sub.add_parser('pwm')
    pwm.add_argument('--axis',type=int,default=0)
    pwm.add_argument('--duty',type=int,default=200,help='signed permille: 200 = 20 percent')
    pwm.add_argument('--ms',type=int,default=250)
    pair = sub.add_parser('pwm_pair')
    pair.add_argument('--left',type=int,required=True)
    pair.add_argument('--right',type=int,required=True)
    pair.add_argument('--ms',type=int,default=250)
    args = parser.parse_args()
    if not args.action:
        parser.error('choose a command')
    command = args.action.upper()
    values = ()
    duration = 0
    if command == 'JOG':
        values = (args.axis,args.steps,args.rate)
        validate_motion(command,values)
        duration = min(2.,abs(args.steps)/float(args.rate)+.3)
    elif command == 'WHEELS':
        values = (args.left,args.right)
        validate_motion(command,values)
        duration = args.seconds
        if math.isnan(duration) or math.isinf(duration):
            raise ValueError('duration must be finite')
        if not 0 < duration <= 2.:
            raise ValueError('duration must be >0 and <=2 seconds')
    elif command == 'PWM':
        values=(args.axis,args.duty,args.ms)
        validate_motion(command,values)
        duration=args.ms/1000.+.2
    elif command == 'PWM_PAIR':
        values=(args.left,args.right,args.ms)
        validate_motion(command,values)
        duration=args.ms/1000.+.2
    if not args.send:
        session = 1 if args.session is None else args.session
        sequence = [('HELLO',()),('STATUS',())]
        if command in ('JOG','WHEELS','PWM','PWM_PAIR'):
            sequence += [('ARM',()),(command,values),('STOP',())]
        elif command not in ('HELLO','STATUS'):
            sequence += [(command,values)]
        for seq,(name,parameters) in enumerate(sequence,1):
            print(encode(session,seq,name,*parameters).decode('ascii').strip())
        print('DRY_RUN: no serial port opened. Motion needs ARM and 10 Hz refresh; frames above are illustrative.')
        return
    if not args.port:
        parser.error('--send requires an explicit --port')
    client = MotorClient(args.port, args.session)
    try:
        if command in ('STOP','ESTOP'):
            print(client.exchange(command))
        elif command in ('JOG','WHEELS','PWM','PWM_PAIR'):
            client.motion(command,values,duration)
            print('BOUNDED_MOTION_FINISHED_AND_STOPPED')
        else:
            print(client.connect())
            if command in ('CLEAR','ENC'):print(client.exchange(command))
    finally:
        client.close()

if __name__ == '__main__':
    try:
        main()
    except (ValueError,RuntimeError,IOError) as exc:
        print('MOTOR_LINK_ERROR: '+str(exc),file=sys.stderr)
        sys.exit(1)
