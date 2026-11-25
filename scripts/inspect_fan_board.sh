echo 'FAN CONTROLS'
find /sys/devices -maxdepth 4 \( -name target_pwm -o -name pwm1 -o -name rpm_measured \) -print 2>/dev/null
for path in /sys/devices/pwm-fan /sys/devices/platform/pwm-fan; do
  if test -d "$path"; then
    ls -l "$path"
    for item in target_pwm temp_control rpm_measured cur_pwm; do
      if test -r "$path/$item"; then printf '%s=' "$item"; cat "$path/$item"; fi
    done
  fi
done
echo 'USB DEVICES'
lsusb
echo 'SERIAL PORTS'
ls -l /dev/ttyUSB* /dev/ttyACM* /dev/serial/by-id/* /dev/ttyTHS* 2>/dev/null || true
for device in /dev/ttyUSB* /dev/ttyACM*; do
  if test -c "$device"; then
    echo "$device"
    udevadm info --query=property --name="$device" | grep -E '^ID_(VENDOR|MODEL|SERIAL|USB_DRIVER|PATH)='
  fi
done
echo 'USB SERIAL KERNEL MESSAGES'
dmesg | grep -Ei 'usb.*(new|Product|Manufacturer|disconnect)|ttyUSB|ttyACM|cp210|ch341|cdc_acm|ftdi' | tail -n 55
echo 'EXISTING BOARD PROCESSES'
ps -eo pid,args | grep -E '[R]osmaster|[M]cnamu_driver|[b]ase_node|[s]erial_node|[m]icro_ros|[m]odbus' || true
