#!/bin/bash
set -euo pipefail
source_dir="$1"
sh -n "$source_dir/jetson-fan-start"
stamp="$(date +%Y%m%d-%H%M%S)"
for path in /usr/local/sbin/jetson-fan-start /etc/systemd/system/jetson-fan-start.service; do
  if [[ -e "$path" ]]; then
    install -D -m 0600 "$path" "/var/backups/jetson-fan-start/$stamp/$(basename "$path")"
  fi
done
install -m 0755 "$source_dir/jetson-fan-start" /usr/local/sbin/jetson-fan-start
install -m 0644 "$source_dir/jetson-fan-start.service" /etc/systemd/system/jetson-fan-start.service
systemd-analyze verify /etc/systemd/system/jetson-fan-start.service
systemctl daemon-reload
systemctl enable --now jetson-fan-start.service
echo 'BOOT ENABLEMENT'
systemctl is-enabled jetson-fan-start.service
echo 'CURRENT SERVICE STATE'
systemctl is-active jetson-fan-start.service
systemctl show jetson-fan-start.service -p ActiveState -p SubState -p ExecMainStatus -p UnitFileState
sleep 8
echo 'FAN READBACK'
for item in temp_control target_pwm cur_pwm; do
  printf '%s=' "$item";cat "/sys/devices/pwm-fan/$item"
done
test "$(cat /sys/devices/pwm-fan/target_pwm)" = 255
test "$(cat /sys/devices/pwm-fan/temp_control)" = 0
test "$(cat /sys/devices/pwm-fan/cur_pwm)" -gt 0
echo 'BOOT TARGET LINK'
readlink -f /etc/systemd/system/multi-user.target.wants/jetson-fan-start.service
echo 'SERVICE JOURNAL'
journalctl -u jetson-fan-start.service --no-pager -n 8
