"""Enable the Jetson Nano PWM fan for the current boot; no clock changes."""
import getpass
import os
import sys
from pathlib import Path
import paramiko

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
client = paramiko.SSHClient()
client.load_host_keys(str(Path(__file__).resolve().parent/'known_hosts'))
password = os.environ.get('JETSON_SSH_PASSWORD') or getpass.getpass('SSH password: ')
try:
    client.connect(os.environ.get("JETSON_HOST", "jetson.local"), username='jetson', password=password,
                   look_for_keys=False, allow_agent=False, timeout=10)
    # Keep firmware/kernel interfaces unchanged except for the fan duty setting.
    command = "sudo -S -p '' sh -c 'set -e; test -f /sys/devices/pwm-fan/target_pwm; "
    command += "printf 0 > /sys/devices/pwm-fan/temp_control; printf 255 > /sys/devices/pwm-fan/target_pwm; "
    command += "sleep 3; for item in temp_control target_pwm cur_pwm tach_enable rpm_measured; do "
    command += "printf \"%s=\" \"$item\"; cat \"/sys/devices/pwm-fan/$item\"; done'"
    stdin, stdout, stderr = client.exec_command(command, timeout=15)
    stdin.write(password+'\n'); stdin.flush(); stdin.channel.shutdown_write()
    print(stdout.read().decode('utf-8', errors='replace'), end='')
    print(stderr.read().decode('utf-8', errors='replace'), end='', file=sys.stderr)
    sys.exit(stdout.channel.recv_exit_status())
finally:
    client.close()
