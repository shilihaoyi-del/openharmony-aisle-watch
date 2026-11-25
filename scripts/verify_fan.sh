for item in temp_control target_pwm cur_pwm pwm_cap state_cap tach_enable rpm_measured; do
  printf '%s=' "$item"
  cat "/sys/devices/pwm-fan/$item"
done
echo 'FAN PWM TABLE'
cat /sys/devices/pwm-fan/pwm_rpm_table
echo 'BOARD PORT STILL PRESENT'
ls -l /dev/serial/by-id/usb-1a86_USB_Serial-if00-port0
