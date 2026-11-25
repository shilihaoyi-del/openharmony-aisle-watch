from __future__ import print_function
import binascii
import os
import subprocess
import sys
import threading
import unittest

sys.path.insert(0,os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),'scripts'))
import motor_link as link
import car_signal
import car4_signal

class FakeSerial(object):
    def __init__(self,**kwargs):
        self.is_open=False;self.buffer=b'';self.writes=[];self.bad_reply=False;self.reject=False
    def open(self):self.is_open=True
    def close(self):self.is_open=False
    def write(self,wire):
        self.writes.append(wire)
        sid,seq,fields=link.decode(wire)
        if self.reject:
            self.buffer+=link.encode(sid,seq,'ERR',fields[0],'UNBOUND')
        else:
            self.buffer+=link.encode(sid+1,seq,'ACK',fields[0],'DISARMED',1,0,0)
            self.buffer+=link.encode(sid,seq,'ACK',fields[0],'DISARMED',1,0,0)
        return len(wire)
    def read(self,n):
        b,self.buffer=self.buffer[:n],self.buffer[n:]
        return b

class HostTests(unittest.TestCase):
    def test_standard_crc_and_roundtrip(self):
        self.assertEqual(binascii.crc_hqx(b'123456789',0xffff),0x29b1)
        frame=link.encode(1,4,'JOG',0,50,100)
        self.assertEqual(link.decode(frame),(1,4,['JOG','0','50','100']))
        self.assertEqual(link.decode(frame[:-1]+b'\r\n'),link.decode(frame))
    def test_crc_corruption_and_injection_rejected(self):
        for wire in (b'$J1,1,1,ARM*0000\n',b'$J1,1,1,ARM*ABCD',b'$J1,1,1,,ARM*0000\n'):
            with self.assertRaises(ValueError):link.decode(wire)
        for cmd in ('ARM\nSTOP','ARM,STOP','ARM*0000'):
            with self.assertRaises(ValueError):link.encode(1,1,cmd)
        for sid in (0,-1,0x100000000):
            with self.assertRaises(ValueError):link.encode(sid,1,'STATUS')
    def test_bounds(self):
        link.validate_motion('JOG',(0,-50,100))
        link.validate_motion('WHEELS',(-200,200))
        for values in ((2,50,100),(0,201,200),(0,50,0),(0,200,100),(0,0,100)):
            with self.assertRaises(ValueError):link.validate_motion('JOG',values)
        with self.assertRaises(ValueError):link.validate_motion('WHEELS',(201,0))
        link.validate_motion('PWM',(0,200,250))
        for values in ((4,100,250),(0,201,250),(0,0,250),(0,100,401),(0,100,0)):
            with self.assertRaises(ValueError):link.validate_motion('PWM',values)
    def test_transport_ignores_wrong_session(self):
        client=link.MotorClient('FAKE',123,FakeSerial)
        reply=client.exchange('STATUS')
        self.assertEqual(reply['state'],'DISARMED')
        self.assertEqual(len(client.serial.writes),1)
        client.close()
    def test_pair_bounds_and_car_directions(self):
        for pair in ((200,200,250),(0,200,250),(-200,0,400)):
            link.validate_motion('PWM_PAIR',pair)
        for pair in ((201,0,250),(0,-201,250),(0,0,250),(200,200,401),(200,200,0)):
            with self.assertRaises(ValueError):link.validate_motion('PWM_PAIR',pair)
        self.assertEqual(car_signal.duties('forward',200),(200,200))
        self.assertEqual(car_signal.duties('left',200),(0,200))
        self.assertEqual(car_signal.duties('right',200),(200,0))
        self.assertEqual(car_signal.duties('backward',200),(-200,-200))
        self.assertEqual(car_signal.duties('stop',200),(0,0))
        self.assertEqual(car_signal.duties('forward',200,1,-1),(200,-200))
        self.assertEqual(car_signal.duties('left',200,1,-1,True),(-200,0))
        script=os.path.join(os.path.dirname(link.__file__),'car_signal.py')
        result=subprocess.check_output([sys.executable,script,'left'])
        self.assertIn(b'DRY_RUN',result)
        self.assertIn(b'PWM_PAIR,0,200,250',result)
    def test_four_bounds_and_mapping(self):
        link.validate_motion('PWM_FOUR',(0,0,200,200,250))
        link.validate_motion('PWM',(3,200,250))
        for values in ((0,0,201,0,250),(0,0,0,0,250),(200,200,200,200,401)):
            with self.assertRaises(ValueError):link.validate_motion('PWM_FOUR',values)
        self.assertEqual(car4_signal.four_duties('motor3',200),(0,0,200,0))
        self.assertEqual(car4_signal.four_duties('motor4',200),(0,0,0,200))
        self.assertEqual(car4_signal.four_duties('forward',200),(200,200,200,200))
        self.assertEqual(car4_signal.four_duties('left',200),(0,0,200,200))
        self.assertEqual(car4_signal.four_duties('right',200,(1,3),(1,-1,1,-1)),(200,0,200,0))
        with self.assertRaises(ValueError):car4_signal.four_duties('left',200,(1,1))
        script=os.path.join(os.path.dirname(link.__file__),'car4_signal.py')
        result=subprocess.check_output([sys.executable,script,'motor4'])
        self.assertIn(b'PWM_FOUR,0,0,0,200,250',result)
        self.assertIn(b'DRY_RUN',result)
    def test_transport_rejection_not_retried(self):
        client=link.MotorClient('FAKE',124,FakeSerial);client.serial.reject=True
        with self.assertRaises(RuntimeError):client.exchange('ARM')
        self.assertEqual(len(client.serial.writes),1)
        client.close()
    def test_default_cli_never_opens_port(self):
        script=os.path.join(os.path.dirname(link.__file__),'motor_link.py')
        result=subprocess.check_output([sys.executable,script,'jog','--steps','50','--rate','100'])
        self.assertIn(b'DRY_RUN',result)
        self.assertIn(b'JOG,0,50,100',result)

@unittest.skipUnless(os.environ.get('J1_BOARD_EMULATOR'),'needs the compiled native mock board, not physical serial')
class NativeWireTests(unittest.TestCase):
    def setUp(self):
        import pty,tty
        master,slave=pty.openpty();tty.setraw(slave)
        self.master=master;self.slave=slave;self.path=os.ttyname(slave)
        self.peer=subprocess.Popen([os.environ['J1_BOARD_EMULATOR'],'--stdio'],stdin=master,stdout=master,stderr=subprocess.PIPE,close_fds=True)
        self.client=link.MotorClient(self.path,1001)
    def tearDown(self):
        self.client.close()
        self.peer.terminate();self.peer.wait()
        self.peer.stderr.close();os.close(self.master);os.close(self.slave)
    def test_host_and_cpp_firmware_bounded_jog(self):
        self.client.motion('JOG',(0,50,100),.9)
        # STOP invalidates the old session. A new connection nonce is required.
        self.client.session=1002
        status=self.client.connect()
        self.assertFalse(status['enabled']);self.assertFalse(status['busy'])
    def test_host_and_cpp_continuous_lease_then_stop(self):
        self.client.motion('WHEELS',(30,-30),.3)
        self.client.session=1003
        status=self.client.connect()
        self.assertEqual(status['state'],'DISARMED')
    def test_peer_handshake_and_reject_unarmed(self):
        status=self.client.connect();self.assertTrue(status['bound'])
        with self.assertRaises(RuntimeError):self.client.exchange('JOG',0,50,100)
    def test_host_and_cpp_finite_pwm(self):
        self.client.motion('PWM',(0,200,250),.5)
        self.client.session=1004
        self.assertFalse(self.client.connect()['enabled'])
    def test_host_and_cpp_finite_pair_then_stop(self):
        for sid,pair in ((1005,(200,200,250)),(1006,(0,200,250)),(1007,(200,0,250))):
            self.client.session=sid
            self.client.motion('PWM_PAIR',pair,.5)
        self.client.session=1008
        status=self.client.connect()
        self.assertFalse(status['enabled']);self.assertFalse(status['busy'])
    def test_host_and_cpp_finite_four_then_stop(self):
        result=self.client.motion('PWM_FOUR',(200,-200,200,-200,250),.5)
        self.assertTrue(result['started']['busy'])
        self.assertFalse(result['completed']['busy'])
        self.assertEqual(result['stopped']['state'],'DISARMED')

if __name__=='__main__':unittest.main()
