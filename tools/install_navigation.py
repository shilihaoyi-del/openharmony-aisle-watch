"""Install only the navigation components required by the simulation."""
import getpass
import os
import sys
import paramiko

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
client = paramiko.SSHClient()
client.load_host_keys('tools/known_hosts')
password = os.environ.get('JETSON_SSH_PASSWORD') or getpass.getpass('SSH password: ')
try:
    client.connect(os.environ.get("JETSON_HOST", "jetson.local"), username='jetson', password=password,
                   look_for_keys=False, allow_agent=False, timeout=10)
    command = ('sudo -S -p "" env DEBIAN_FRONTEND=noninteractive apt-get install -y '
               '--no-install-recommends --no-upgrade ros-melodic-move-base ros-melodic-amcl '
               'ros-melodic-map-server ros-melodic-gmapping ros-melodic-dwa-local-planner')
    stdin, stdout, stderr = client.exec_command(command, timeout=240)
    stdin.write(password+'\n'); stdin.flush(); stdin.channel.shutdown_write()
    for line in stdout:
        print(line, end='', flush=True)
    print(stderr.read().decode('utf-8', errors='replace'), end='')
    sys.exit(stdout.channel.recv_exit_status())
finally:
    client.close()
