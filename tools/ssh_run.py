"""Run a UTF-8 shell script on the Nano; password stays in the environment."""
import argparse
import getpass
import os
from pathlib import Path
import sys
import paramiko

parser = argparse.ArgumentParser()
parser.add_argument("script", type=Path)
parser.add_argument("--timeout", type=int, default=45)
args = parser.parse_args()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
client = paramiko.SSHClient()
known_hosts = Path(__file__).resolve().parent / "known_hosts"
if known_hosts.exists():
    client.load_host_keys(str(known_hosts))
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    client.connect(os.environ.get("JETSON_HOST", "jetson.local"), username="jetson",
                   password=os.environ.get("JETSON_SSH_PASSWORD") or getpass.getpass("SSH password: "),
                   timeout=10, auth_timeout=10, look_for_keys=False, allow_agent=False)
    client.save_host_keys(str(known_hosts))
    stdin, stdout, stderr = client.exec_command("bash -s", timeout=args.timeout)
    stdin.write(args.script.read_text(encoding="utf-8"))
    stdin.channel.shutdown_write()
    print(stdout.read().decode("utf-8", errors="replace"), end="")
    print(stderr.read().decode("utf-8", errors="replace"), end="", file=sys.stderr)
    sys.exit(stdout.channel.recv_exit_status())
finally:
    client.close()
