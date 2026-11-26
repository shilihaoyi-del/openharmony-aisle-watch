#ifndef J1_PROTOCOL_H
#define J1_PROTOCOL_H
#include <stddef.h>
#include <stdint.h>

namespace j1 {
// Extended limits apply only to explicitly selected four-channel bench images.
#if defined(J1_PWM_FOUR_80)
constexpr int16_t PWM_FOUR_MAX = 800;
#elif defined(J1_PWM_FOUR_60)
constexpr int16_t PWM_FOUR_MAX = 600;
#elif defined(J1_PWM_FOUR_50)
constexpr int16_t PWM_FOUR_MAX = 500;
#elif defined(J1_PWM_FOUR_40)
constexpr int16_t PWM_FOUR_MAX = 400;
#elif defined(J1_PWM_FOUR_30)
constexpr int16_t PWM_FOUR_MAX = 300;
#else
constexpr int16_t PWM_FOUR_MAX = 200;
#endif
#if defined(J1_PWM_FOUR_5S)
constexpr uint16_t PWM_FOUR_DURATION_MAX = 5000;
#elif defined(J1_PWM_FOUR_1S)
constexpr uint16_t PWM_FOUR_DURATION_MAX = 1000;
#else
constexpr uint16_t PWM_FOUR_DURATION_MAX = 400;
#endif
enum State { DISARMED, ARMED, RUNNING, JOGGING, ESTOP, FAULT, PWM_TEST };
// Board-specific implementation must initialise pins and timers before Controller exists.
// All stop/disable functions must stop timers and pending pulses, not just target velocity.
struct MotorHal {
  virtual ~MotorHal() {}
  virtual bool ready() const = 0;
  virtual bool healthy() const = 0;
  virtual bool estopInput() const = 0;
  virtual bool enable(bool on) = 0;
  virtual void stop() = 0;
  virtual bool rates(int32_t left, int32_t right) = 0;
  virtual bool jog(uint8_t axis, int32_t pulses, uint16_t rate) = 0;
  virtual bool busy() const = 0;
  // Optional finite DC test; never reinterpret stepper rates as PWM duty.
  virtual bool pwm(uint8_t, int16_t, uint16_t) { return false; }
  virtual bool pwmPair(int16_t, int16_t, uint16_t) { return false; }
  virtual bool pwmFour(int16_t, int16_t, int16_t, int16_t, uint16_t) { return false; }
};
struct ReplySink {
  virtual ~ReplySink() {}
  virtual void send(const char* frame) = 0;
  virtual bool reportEncoders() { return false; }
};
uint16_t crc16(const char* text, size_t length);
class Controller {
 public:
  Controller(MotorHal& hal, ReplySink& sink);
  void feed(char byte, uint32_t now_ms);
  void tick(uint32_t now_ms);
  State state() const { return state_; }
 private:
  MotorHal& hal_; ReplySink& sink_;
  State state_;
  uint32_t session_, retired_session_, last_seq_, lease_ms_, jog_start_ms_;
  uint16_t pwm_timeout_ms_;
  bool enabled_, collecting_;
  size_t length_;
  char line_[160], last_request_[160], cached_reply_[160];
  void stop(State next);
  void process(uint32_t now_ms);
  void reply(uint32_t session, uint32_t seq, const char* kind, const char* command,
             const char* reason = 0, bool cache = false);
  const char* stateName() const;
};
}
#endif
