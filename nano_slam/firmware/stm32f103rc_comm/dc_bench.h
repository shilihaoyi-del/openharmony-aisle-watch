// Finite DC bench test for the confirmed STM32F103RC / TB6612 schematic.
// Included after outputs_off() and the millisecond counter in main.cpp.
static volatile bool bench_pwm_active=false;
static volatile uint32_t bench_pwm_start=0,bench_pwm_duration=0;

static void bench_stop_outputs() {
  bench_pwm_active=false;
  if (RCC->APB1ENR & RCC_APB1ENR_TIM3EN) {
    TIM3->CCER=0;TIM3->CCR1=0;TIM3->CCR2=0;TIM3->CR1=0;
  }
  outputs_off();
}
static void bench_timer_tick() {
  // Stops the pulse even if the UART/main protocol loop is busy.
  if (bench_pwm_active && static_cast<uint32_t>(milliseconds-bench_pwm_start)>=bench_pwm_duration)
    bench_stop_outputs();
}
static void encoder_timer(TIM_TypeDef* timer) {
  timer->CR1=0;timer->SMCR=3;timer->CCMR1=0x3131;timer->CCER=0;
  timer->PSC=0;timer->ARR=0xffff;timer->CNT=0;timer->EGR=1;timer->CR1=1;
}
static void bench_init() {
  RCC->APB2ENR |= RCC_APB2ENR_IOPAEN|RCC_APB2ENR_IOPBEN|RCC_APB2ENR_IOPCEN;
  RCC->APB1ENR |= RCC_APB1ENR_TIM2EN|RCC_APB1ENR_TIM3EN|RCC_APB1ENR_TIM4EN;
  GPIOA->CRL=(GPIOA->CRL & ~0xffU)|0x44U;
  GPIOB->CRL=(GPIOB->CRL & ~0xff000000U)|0x44000000U;
  encoder_timer(TIM4); // Motor1 PB6/PB7
  encoder_timer(TIM2); // Motor2 PA0/PA1
  bench_stop_outputs();
  DBGMCU->CR |= DBGMCU_CR_DBG_IWDG_STOP;
  // PR/RLR update flags cannot clear while the LSI clock is stopped.
  RCC->CSR |= RCC_CSR_LSION;
  uint32_t began=milliseconds;
  while (!(RCC->CSR & RCC_CSR_LSIRDY)) {
    if (static_cast<uint32_t>(milliseconds-began)>100U) {bench_stop_outputs();for(;;){}}
  }
  IWDG->KR=0x5555;IWDG->PR=4;IWDG->RLR=312;
  began=milliseconds;
  while (IWDG->SR) {
    if (static_cast<uint32_t>(milliseconds-began)>100U) {bench_stop_outputs();for(;;){}}
  }
  IWDG->KR=0xaaaa;IWDG->KR=0xcccc;
}
class DcBenchMotor : public j1::MotorHal {
  bool enabled_;
 public:
  DcBenchMotor():enabled_(false) {}
  bool ready() const {return true;}
  bool healthy() const {return true;}
  bool estopInput() const {return false;} // No independent estop GPIO in the supplied schematic.
  bool enable(bool on) {bench_stop_outputs();enabled_=on;return true;}
  void stop() {bench_stop_outputs();}
  bool rates(int32_t,int32_t) {return false;} // Stepper pulse units are unsupported.
  bool jog(uint8_t,int32_t,uint16_t) {return false;}
  bool busy() const {return bench_pwm_active;}
  bool pwm(uint8_t axis,int16_t duty,uint16_t duration) {
    if(axis>1||!duty)return false;
    return pwmPair(axis==0?duty:0,axis==1?duty:0,duration);
  }
  bool pwmPair(int16_t left,int16_t right,uint16_t duration) {
    if(!enabled_||left>200||left< -200||right>200||right< -200||(!left&&!right)||!duration||duration>400)return false;
    bench_stop_outputs();
    // TIM3 clock is 8 MHz. PWM frequency = 8 MHz/(799+1) = 10 kHz.
    TIM3->PSC=0;TIM3->ARR=799;TIM3->CCMR1=0x6868;TIM3->CCR1=0;TIM3->CCR2=0;
    GPIOA->CRL=(GPIOA->CRL & ~0xff000000U)|0xaa000000U;
    uint32_t channels=0;
    if(left) {
      GPIOA->BSRR=left>0 ? (1U<<5)|(1U<<(4+16)) : (1U<<4)|(1U<<(5+16));
      TIM3->CCR1=static_cast<uint32_t>(left<0?-left:left)*800U/1000U;
      channels|=TIM_CCER_CC1E;
    }
    if(right) {
      GPIOC->BSRR=right>0 ? (1U<<4)|(1U<<(5+16)) : (1U<<5)|(1U<<(4+16));
      TIM3->CCR2=static_cast<uint32_t>(right<0?-right:right)*800U/1000U;
      channels|=TIM_CCER_CC2E;
    }
    TIM3->CCER=channels;
    TIM3->EGR=TIM_EGR_UG;
    bench_pwm_start=milliseconds;bench_pwm_duration=duration;bench_pwm_active=true;
    TIM3->CR1=TIM_CR1_ARPE|TIM_CR1_CEN;
    return true;
  }
};
