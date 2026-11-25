// Protocol-only Arduino-style example. Board model/pins are intentionally unbound.
// It replies HELLO/STATUS, but ARM returns UNBOUND and cannot energise a motor.
#include "j1_protocol.h"

class UnboundMotor : public j1::MotorHal {
 public:
  bool ready() const { return false; }
  bool healthy() const { return true; }
  bool estopInput() const { return false; }
  bool enable(bool on) { return !on; }
  void stop() {}
  bool rates(int32_t,int32_t) { return false; }
  bool jog(uint8_t,int32_t,uint16_t) { return false; }
  bool busy() const { return false; }
};
class SerialReplies : public j1::ReplySink {
 public:
  void send(const char* frame) { Serial.print(frame); }
};
UnboundMotor motors;
SerialReplies replies;
j1::Controller protocol(motors,replies);
void setup() { Serial.begin(115200); }
void loop() {
  // Keep tick servicing bounded even if the UART receives continuous garbage.
  protocol.tick(millis());
  for (uint8_t n=0;n<32 && Serial.available();++n)
    protocol.feed(static_cast<char>(Serial.read()),millis());
}
