"""Upload the mapping package without embedding SSH credentials."""
import getpass
import os
from pathlib import Path
import paramiko

root = Path(__file__).resolve().parents[1]
client = paramiko.SSHClient()
client.load_host_keys(str(root/'tools'/'known_hosts'))
try:
    client.connect(os.environ.get("JETSON_HOST", "jetson.local"), username='jetson',
                   password=os.environ.get('JETSON_SSH_PASSWORD') or getpass.getpass('SSH password: '),
                   look_for_keys=False, allow_agent=False, timeout=10)
    sftp = client.open_sftp()
    target = '/home/jetson/slam_ws/src/nano_slam'
    try:
        sftp.stat(target)
    except FileNotFoundError:
        sftp.mkdir(target)
    for path in sorted((root/'nano_slam').rglob('*')):
        remote = target+'/'+path.relative_to(root/'nano_slam').as_posix()
        if path.is_dir():
            try:
                sftp.stat(remote)
            except FileNotFoundError:
                sftp.mkdir(remote)
        else:
            if path.suffix in ('.pyc',) or '__pycache__' in path.parts:
                continue
            # Preserve an existing version before replacing project files.
            try:
                with sftp.open(remote, 'rb') as current:
                    if current.read() == path.read_bytes():
                        continue
                import time
                sftp.rename(remote, remote+'.bak.'+str(time.time_ns()))
            except FileNotFoundError:
                pass
            with sftp.open(remote, 'w') as handle:
                handle.write(path.read_bytes())
            sftp.chmod(remote, 0o755 if path.suffix in ('.py', '.sh') else 0o644)
            print(remote)
    sftp.close()
finally:
    client.close()
