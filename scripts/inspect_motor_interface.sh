echo 'BOARD INTERFACE'
ls -l /dev/serial/by-id/usb-1a86_USB_Serial-if00-port0 /dev/ttyUSB1 2>/dev/null
udevadm info --query=property --name=/dev/ttyUSB1 | grep -E '^ID_(MODEL|VENDOR|SERIAL|USB_DRIVER)='
echo 'SERIAL PORT USERS (PORT NOT OPENED BY THIS CHECK)'
if command -v fuser >/dev/null; then fuser -v /dev/ttyUSB1 2>&1 || true; fi
echo 'LOCAL FIRMWARE FILE CANDIDATES'
for folder in /home/jetson/Desktop /home/jetson/Documents /home/jetson/Downloads; do
  find "$folder" -maxdepth 3 -type f \( -iname '*.ino' -o -iname '*stepper*' -o -iname '*motor*.py' -o -iname '*protocol*' \) -print 2>/dev/null | head -n 25
done
