// Stop scans and the motor using the existing Slamtec SDK, never start a scan.
#include "sl_lidar.h"
#include "sl_lidar_driver.h"
#include <stdio.h>
#include <unistd.h>
int main() {
  const char* port="/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0";
  sl::ILidarDriver* driver=*sl::createLidarDriver();
  sl::IChannel* channel=*sl::createSerialPortChannel(port,115200);
  if(!driver||!channel) return 2;
  sl_result connected=driver->connect(channel);
  if(SL_IS_FAIL(connected)){fprintf(stderr,"LIDAR_CONNECT_FAILED %x\n",connected);return 3;}
  sl_lidar_response_device_info_t info;
  sl_result identified=driver->getDeviceInfo(info,1000);
  sl_result scan=driver->stop(1000);
  sl_result motor=driver->setMotorSpeed(0);
  usleep(200000);
  printf("LIDAR_STOP_RESULTS identified=%x scan=%x motor=%x",identified,scan,motor);
  if(SL_IS_OK(identified))printf(" model=%02x",info.model);
  printf("\n");
  driver->disconnect();delete driver;delete channel;
  return SL_IS_FAIL(scan)||SL_IS_FAIL(motor)?4:0;
}
