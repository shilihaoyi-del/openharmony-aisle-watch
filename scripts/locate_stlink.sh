echo 'JETSON USB INVENTORY'
lsusb
echo 'STLINK DEVICE NODES'
ls -l /dev/stlink* /dev/serial/by-id/* 2>/dev/null || true
echo 'PROGRAMMING TOOLS'
command -v st-info || true
command -v st-flash || true
command -v openocd || true
echo 'RECENT USB EVENTS'
dmesg | grep -Ei 'usb.*(new|disconnect)|ST-LINK|STLink|STM32|0483' | tail -n 16
