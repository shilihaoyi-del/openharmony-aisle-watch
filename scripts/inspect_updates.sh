echo 'DISK'
df -h /
echo 'PACKAGE AUDIT'
dpkg --audit
echo 'HELD PACKAGES'
apt-mark showhold
echo 'SIMULATED UPGRADE (NO PACKAGES CHANGED)'
python3 - <<'PY'
import subprocess
try:
    p = subprocess.run(['apt-get', '-s', 'upgrade'], stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, universal_newlines=True, timeout=30,
                       env=dict(__import__('os').environ, LC_ALL='C'))
    lines = p.stdout.splitlines()
    for i,line in enumerate(lines):
        if any(s in line for s in ('kept back', 'upgraded,', 'not upgraded', 'E:', 'W:', 'unmet dependencies', 'REMOVED', 'NEW packages')):
            print('\n'.join(lines[max(0,i-1):min(len(lines),i+5)]))
    print('SIMULATION_EXIT={}'.format(p.returncode))
except subprocess.TimeoutExpired:
    print('SIMULATION_TIMEOUT')
PY
