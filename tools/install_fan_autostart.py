"""Install and enable the fan service; password is kept out of files."""
import getpass
import os
from pathlib import Path
import shlex
import sys
import uuid
import paramiko

sys.stdout.reconfigure(encoding='utf-8',errors='replace')
root=Path(__file__).resolve().parents[1]
password=os.environ.get('JETSON_SSH_PASSWORD') or getpass.getpass('SSH password: ')
client=paramiko.SSHClient();client.load_host_keys(str(root/'tools/known_hosts'))
stage='/home/jetson/.cache/jetson-fan-install-'+uuid.uuid4().hex
try:
    client.connect(os.environ.get("JETSON_HOST", "jetson.local"),username='jetson',password=password,timeout=10,
                   look_for_keys=False,allow_agent=False)
    with client.open_sftp() as sftp:
        sftp.mkdir(stage,mode=0o700)
        for name in ('jetson-fan-start','jetson-fan-start.service','install-fan-start.sh'):
            sftp.put(str(root/'system'/name),stage+'/'+name)
    command="sudo -S -p '' bash "+shlex.quote(stage+'/install-fan-start.sh')+' '+shlex.quote(stage)
    stdin,stdout,stderr=client.exec_command(command,timeout=65)
    stdin.write(password+'\n');stdin.flush();stdin.channel.shutdown_write()
    for line in stdout:print(line,end='',flush=True)
    print(stderr.read().decode('utf-8',errors='replace'),end='',file=sys.stderr)
    code=stdout.channel.recv_exit_status()
    if code:raise SystemExit(code)
    # Remove only this uploader's three files and its unique staging directory.
    with client.open_sftp() as sftp:
        for name in ('jetson-fan-start','jetson-fan-start.service','install-fan-start.sh'):
            sftp.remove(stage+'/'+name)
        sftp.rmdir(stage)
finally:client.close()
