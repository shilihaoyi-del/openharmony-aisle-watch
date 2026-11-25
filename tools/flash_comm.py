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
    parser.add_argument('--profile',choices=('communication','dc-bench','dc-four','encoder'),default='communication')
    args=parser.parse_args()
    paths={'communication':IMAGE,'dc-bench':ROOT/'artifacts/stm32f103rc_dc_bench/stm32f103rc_dc_bench.bin',
           'dc-four':ROOT/'artifacts/stm32f103rc_dc_four/stm32f103rc_dc_four.bin',
           'encoder':ROOT/'artifacts/stm32f103rc_encoder/stm32f103rc_encoder.bin'}
    chosen_image=paths[args.profile]
    image = chosen_image.read_bytes()
    metadata = json.loads(chosen_image.with_name('build_metadata.json').read_text(encoding='utf-8-sig'))
    digest = hashlib.sha256(image).hexdigest()
    expected={'communication':'communication_only','dc-bench':'dc_bench','dc-four':'dc_four_wheel','encoder':'encoder_only'}[args.profile]
    motor_image = args.profile in ('dc-bench','dc-four')
    if metadata.get('image') != expected or metadata.get('motor_interface_bound') != motor_image:
        raise RuntimeError('Firmware profile does not match the explicit selection')
    if motor_image and (metadata.get('max_pwm_permille')!=200 or metadata.get('max_pwm_duration_ms')!=400 or metadata.get('default_state')!='DISARMED'):
        raise RuntimeError('Unexpected finite DC test limits')
    if args.profile=='dc-bench' and metadata.get('pwm_pair_supported') is not True:
        raise RuntimeError('Selected DC image is missing simultaneous two-channel PWM support')
    if args.profile=='dc-four' and (metadata.get('pwm_four_supported') is not True or metadata.get('independent_channels')!=4 or metadata.get('board_profile')!='original_board_four_pwm'):
        raise RuntimeError('Selected image does not match the four-channel board')
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
    report = {'time':stamp.isoformat(),'stlink_serial':SERIAL,'image':str(chosen_image),
              'image_sha256':digest,'image_bytes':len(image),'motor_interface_bound':metadata['motor_interface_bound'],
              'profile':expected,
              'programmed':False,'readback_verified':False,'running':False}
    def save():
        (folder/'flash_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    def run(*args):
        command = [str(CLI),'-c','SN='+SERIAL,'SWD','HOTPLUG','FREQ=100']+list(args)
        result = subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
        output = result.stdout.decode('utf-8',errors='replace')
        print(output,flush=True)
        with (folder/'stlink.log').open('a',encoding='utf-8') as handle:
            handle.write('COMMAND: '+subprocess.list2cmdline(command)+'\n'+output+'\n')
        if result.returncode or re.search(r'No target connected|Unable to connect|Error:',output,re.I):
            raise RuntimeError('ST-Link operation failed; see stlink.log')
        return output
    save()
    try:
        probe = run('-SCore','-rOB')
        if not re.search(r'Device ID:\s*0x414\b',probe,re.I):
            raise RuntimeError('Unexpected target device ID')
        if not re.search(r'Device flash Size:\s*256\s*Kbytes',probe,re.I):
            raise RuntimeError('Unexpected target flash size')
        if not re.search(r'RDP\s*:\s*DISABLED',probe):
            raise RuntimeError('Read protection must not be changed by this tool')
        voltage = re.search(r'Target voltage\s*=\s*([0-9.]+)',probe)
        if not voltage or not 3.0 <= float(voltage.group(1)) <= 3.6:
            raise RuntimeError('Target supply outside expected 3.0..3.6V')
        backup = folder/'original_flash_08000000_256k.bin'
        run('-Dump','0x08000000','0x40000',str(backup),'-Q')
        original = backup.read_bytes()
        if len(original) != 262144:
            raise RuntimeError('Incomplete original flash backup')
        report['backup_sha256'] = hashlib.sha256(original).hexdigest()
        report['backup'] = str(backup)
        save()
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
