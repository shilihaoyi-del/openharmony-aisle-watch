"""Flash a reviewed STM32F103RC communication or explicit finite DC bench image."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CLI = Path('D:/ST-LINK/ST-LINK Utility/ST-LINK_CLI.exe')
SERIAL = '34FF74064D56383341362443'
IMAGE = ROOT/'artifacts/stm32f103rc_comm/stm32f103rc_comm.bin'
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    high_duty_profiles = {'dc-four-30': ('dc-four', 400),
                          'dc-four-30-1s': ('dc-four-30', 1000),
                          'dc-four-30-5s': ('dc-four-30-1s', 5000),
                          'dc-four-30-5s-paired': ('dc-four-30-5s', 5000),
                          'dc-four-30-5s-paired-enc': ('dc-four-30-5s-paired', 5000),
                          'dc-four-30-5s-paired-enc-forward': ('dc-four-30-5s-paired-enc', 5000),
                          'dc-four-40-5s-paired-enc-forward': ('dc-four-30-5s-paired-enc-forward', 5000),
                          'dc-four-50-5s-paired-enc-forward': ('dc-four-40-5s-paired-enc-forward', 5000),
                          'dc-four-60-5s-paired-enc-forward': ('dc-four-50-5s-paired-enc-forward', 5000),
                          'dc-four-80-5s-paired-enc-forward': ('dc-four-60-5s-paired-enc-forward', 5000)}
    parser.add_argument('--profile',choices=('communication','dc-bench','dc-four','encoder',*high_duty_profiles),default='communication')
    parser.add_argument('--single-probe',action='store_true',
                        help='use the sole detected ST-Link when it does not report a serial number')
    args=parser.parse_args()
    if args.single_probe:
        if args.profile not in high_duty_profiles:
            parser.error('--single-probe requires a four-channel extended PWM profile')
        listing=subprocess.run([str(CLI),'-List'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=15)
        if (listing.returncode or len(re.findall(rb'^ST-LINK Probe \d+:',listing.stdout,re.M))!=1
                or re.search(rb'No ST-LINK ready|USB Communication Error',listing.stdout,re.I)):
            raise RuntimeError('Connect one available ST-Link for serial-independent selection')
    paths={'communication':IMAGE,'dc-bench':ROOT/'artifacts/stm32f103rc_dc_bench/stm32f103rc_dc_bench.bin',
           'dc-four':ROOT/'artifacts/stm32f103rc_dc_four/stm32f103rc_dc_four.bin',
           'dc-four-30':ROOT/'artifacts/stm32f103rc_dc_four_30/stm32f103rc_dc_four_30.bin',
           'dc-four-30-1s':ROOT/'artifacts/stm32f103rc_dc_four_30_1s/stm32f103rc_dc_four_30_1s.bin',
           'dc-four-30-5s':ROOT/'artifacts/stm32f103rc_dc_four_30_5s/stm32f103rc_dc_four_30_5s.bin',
           'dc-four-30-5s-paired':ROOT/'artifacts/stm32f103rc_dc_four_30_5s_paired/stm32f103rc_dc_four_30_5s_paired.bin',
           'dc-four-30-5s-paired-enc':ROOT/'artifacts/stm32f103rc_dc_four_30_5s_paired_enc/stm32f103rc_dc_four_30_5s_paired_enc.bin',
           'dc-four-30-5s-paired-enc-forward':ROOT/'artifacts/stm32f103rc_dc_four_30_5s_paired_enc_forward/stm32f103rc_dc_four_30_5s_paired_enc_forward.bin',
           'dc-four-40-5s-paired-enc-forward':ROOT/'artifacts/stm32f103rc_dc_four_40_5s_paired_enc_forward/stm32f103rc_dc_four_40_5s_paired_enc_forward.bin',
           'dc-four-50-5s-paired-enc-forward':ROOT/'artifacts/stm32f103rc_dc_four_50_5s_paired_enc_forward/stm32f103rc_dc_four_50_5s_paired_enc_forward.bin',
           'dc-four-60-5s-paired-enc-forward':ROOT/'artifacts/stm32f103rc_dc_four_60_5s_paired_enc_forward/stm32f103rc_dc_four_60_5s_paired_enc_forward.bin',
           'dc-four-80-5s-paired-enc-forward':ROOT/'artifacts/stm32f103rc_dc_four_80_5s_paired_enc_forward/stm32f103rc_dc_four_80_5s_paired_enc_forward.bin',
           'encoder':ROOT/'artifacts/stm32f103rc_encoder/stm32f103rc_encoder.bin'}
    chosen_image=paths[args.profile]
    image = chosen_image.read_bytes()
    metadata = json.loads(chosen_image.with_name('build_metadata.json').read_text(encoding='utf-8-sig'))
    digest = hashlib.sha256(image).hexdigest()
    expected={'communication':'communication_only','dc-bench':'dc_bench','dc-four':'dc_four_wheel',
              'dc-four-30':'dc_four_wheel_30','dc-four-30-1s':'dc_four_wheel_30_1s',
              'dc-four-30-5s':'dc_four_wheel_30_5s','dc-four-30-5s-paired':'dc_four_wheel_30_5s_paired',
              'dc-four-30-5s-paired-enc':'dc_four_wheel_30_5s_paired_enc',
              'dc-four-30-5s-paired-enc-forward':'dc_four_wheel_30_5s_paired_enc_forward',
              'dc-four-40-5s-paired-enc-forward':'dc_four_wheel_40_5s_paired_enc_forward',
              'dc-four-50-5s-paired-enc-forward':'dc_four_wheel_50_5s_paired_enc_forward',
              'dc-four-60-5s-paired-enc-forward':'dc_four_wheel_60_5s_paired_enc_forward',
              'dc-four-80-5s-paired-enc-forward':'dc_four_wheel_80_5s_paired_enc_forward',
              'encoder':'encoder_only'}[args.profile]
    previous_profile, expected_duration = high_duty_profiles.get(args.profile, (None, 400))
    four_wheel = args.profile == 'dc-four' or previous_profile is not None
    motor_image = four_wheel or args.profile == 'dc-bench'
    expected_limit = 10 * int(args.profile.split('-')[2]) if previous_profile is not None else 200
    if metadata.get('image') != expected or metadata.get('motor_interface_bound') != motor_image:
        raise RuntimeError('Firmware profile does not match the explicit selection')
    if motor_image and (metadata.get('max_pwm_permille')!=expected_limit or metadata.get('max_pwm_duration_ms')!=expected_duration or metadata.get('default_state')!='DISARMED'):
        raise RuntimeError('Unexpected finite DC test limits')
    if args.profile=='dc-bench' and metadata.get('pwm_pair_supported') is not True:
        raise RuntimeError('Selected DC image is missing simultaneous two-channel PWM support')
    if four_wheel and (metadata.get('pwm_four_supported') is not True or metadata.get('independent_channels')!=4 or metadata.get('board_profile')!='original_board_four_pwm'):
        raise RuntimeError('Selected image does not match the four-channel board')
    if '-paired' in args.profile and metadata.get('paired_drivers') is not True:
        raise RuntimeError('Selected image is missing paired driver enforcement')
    if '-paired-enc' in args.profile and (metadata.get('encoder_query') is not True or metadata.get('encoder_channels')!=4):
        raise RuntimeError('Selected image is missing four-channel encoder readback')
    if args.profile.endswith('-enc-forward') and metadata.get('encoder_forward_signs') != [1,-1,-1,1]:
        raise RuntimeError('Selected image does not match the calibrated encoder polarity')
    if args.profile=='encoder' and (metadata.get('encoder_channels')!=4 or metadata.get('board_profile')!='original_board_four_pwm'):
        raise RuntimeError('Selected image does not match the four-channel encoder board')
    if metadata['sha256'] != digest or len(image) != metadata['image_bytes']:
        raise RuntimeError('Reviewed image hash/size mismatch')
    sp, reset = struct.unpack_from('<II',image)
    if not (0x20000000 < sp <= 0x2000c000 and sp%8 == 0 and reset&1
            and 0x08000000 <= reset-1 < 0x08000000+len(image)):
        raise RuntimeError('Invalid target vector table')
    stamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    folder = ROOT/'artifacts/stlink_flash'/stamp.strftime('%Y%m%d-%H%M%S')
    folder.mkdir(parents=True, exist_ok=False)
    report = {'time':stamp.isoformat(),'stlink_serial':None if args.single_probe else SERIAL,'image':str(chosen_image),
              'image_sha256':digest,'image_bytes':len(image),'motor_interface_bound':metadata['motor_interface_bound'],
              'profile':expected,
              'programmed':False,'readback_verified':False,'running':False}
    def save():
        (folder/'flash_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    def run(*operations):
        selection=[] if args.single_probe else ['SN='+SERIAL]
        command = [str(CLI),'-c']+selection+['SWD','HOTPLUG','FREQ=100']+list(operations)
        result = subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
        output = result.stdout.decode('utf-8',errors='replace')
        print(output,flush=True)
        with (folder/'stlink.log').open('a',encoding='utf-8') as handle:
            handle.write('COMMAND: '+subprocess.list2cmdline(command)+'\n'+output+'\n')
        if result.returncode or re.search(r'No (?:target connected|ST-LINK detected)|Unable to connect|Error:',output,re.I):
            raise RuntimeError('ST-Link operation failed; see stlink.log')
        return output
    save()
    try:
        probe = run('-SCore','-rOB','-r32','0x40000420','1')
        if not re.search(r'Device ID:\s*0x414\b',probe,re.I):
            raise RuntimeError('Unexpected target device ID')
        if not re.search(r'Device flash Size:\s*256\s*Kbytes',probe,re.I):
            raise RuntimeError('Unexpected target flash size')
        if not re.search(r'RDP\s*:\s*DISABLED',probe):
            raise RuntimeError('Read protection must not be changed by this tool')
        voltage = re.search(r'Target voltage\s*=\s*([0-9.]+)',probe)
        # DS5792 table 29 specifies 2.0–3.6 V for STM32F103xC Flash programming.
        minimum_voltage=2.0 if args.single_probe else 3.0
        if not voltage or not minimum_voltage <= float(voltage.group(1)) <= 3.6:
            raise RuntimeError('Target voltage outside expected %.1f..3.6 V' % minimum_voltage)
        timer = re.search(r'0x40000420\s*:\s*([0-9a-f]{8})',probe,re.I)
        if not timer or int(timer.group(1),16)&0x1111:
            raise RuntimeError('Could not verify that all four motor outputs were off')
        report['target_voltage_v']=float(voltage.group(1))
        backup = folder/'original_flash_08000000_256k.bin'
        run('-Dump','0x08000000','0x40000',str(backup),'-Q')
        original = backup.read_bytes()
        if len(original) != 262144:
            raise RuntimeError('Incomplete original flash backup')
        report['backup_sha256'] = hashlib.sha256(original).hexdigest()
        report['backup'] = str(backup)
        save()
        if args.single_probe:
            previous=paths[previous_profile].read_bytes()
            if not (original.startswith(previous) or original.startswith(image)):
                raise RuntimeError('Existing image did not match the expected four-channel firmware')
        if original.startswith(image):
            report['readback_verified']=True
            report['running']='Core is Running' in probe
            save()
            print('FLASH_ALREADY_MATCHES '+str(folder/'flash_report.json'),flush=True)
            return
        # No mass erase, no option-byte changes and no automatic protection removal.
        run('-Halt','-P',str(chosen_image),'0x08000000','-V','after_programming','-Q')
        report['programmed'] = True
        save()
        readback = folder/'communication_readback.bin'
        run('-Dump','0x08000000',hex(len(image)),str(readback),'-Q')
        if readback.read_bytes() != image:
            raise RuntimeError('Byte-for-byte flash readback mismatch; application left halted')
        report['readback_verified'] = True
        save()
        output = run('-Rst','-Run','-SCore')
        if 'Core is Running' not in output:
            raise RuntimeError('Programming verified, but running status not confirmed')
        report['running'] = True
        save()
        print('FLASH_VERIFIED_AND_RUNNING '+str(folder/'flash_report.json'),flush=True)
    except Exception as exc:
        report['error'] = str(exc)
        save()
        raise

if __name__ == '__main__':
    main()
