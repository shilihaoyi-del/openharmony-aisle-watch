echo 'SYSTEM'
hostname
uptime
echo 'FAN CURRENT STATE'
for item in temp_control target_pwm cur_pwm tach_enable rpm_measured; do
  if test -r "/sys/devices/pwm-fan/$item"; then printf '%s=' "$item";cat "/sys/devices/pwm-fan/$item";fi
done
echo 'EXISTING FAN SERVICES'
systemctl list-unit-files --no-pager | grep -Ei 'fan|jetson.*clock' || true
echo 'EXISTING FAN STARTUP CONFIGURATION'
for path in /etc/rc.local /etc/systemd/system/jetson-fan.service /etc/systemd/system/jetson-fan-start.service /usr/local/sbin/jetson-fan-start; do
  if test -f "$path"; then echo "$path"; cat "$path";fi
done
