// Recovered from the target's original firmware: native TIM3 CH1..4 PWM.
// M1 PA5/PA4/PA6; M2 PC4/PC5/PA7; M3 PC6/PC7/PB0; M4 PB14/PB15/PB1.
static volatile bool bench_pwm_active=false;
static volatile uint32_t bench_pwm_start=0,bench_pwm_duration=0;
static GPIO_TypeDef* const direction_port[4]={GPIOA,GPIOC,GPIOC,GPIOB};
static const uint16_t direction_positive[4]={1U<<5,1U<<4,1U<<6,1U<<14};
static const uint16_t direction_negative[4]={1U<<4,1U<<5,1U<<7,1U<<15};

static void bench_stop_outputs() {bench_pwm_active=false;outputs_off();}
static void bench_timer_tick() {
  if(bench_pwm_active && static_cast<uint32_t>(milliseconds-bench_pwm_start)>=bench_pwm_duration)
    bench_stop_outputs();
}
static void bench_init() {
  outputs_off();RCC->APB1ENR|=RCC_APB1ENR_TIM3EN;
  DBGMCU->CR|=DBGMCU_CR_DBG_IWDG_STOP;RCC->CSR|=RCC_CSR_LSION;
  uint32_t began=milliseconds;
  while(!(RCC->CSR&RCC_CSR_LSIRDY)) {
    if(static_cast<uint32_t>(milliseconds-began)>100U){bench_stop_outputs();for(;;){}}
  }
  IWDG->KR=0x5555;IWDG->PR=4;IWDG->RLR=312;
  began=milliseconds;
  while(IWDG->SR) {
    if(static_cast<uint32_t>(milliseconds-began)>100U){bench_stop_outputs();for(;;){}}
  }
  IWDG->KR=0xaaaa;IWDG->KR=0xcccc;
}
class DcBenchMotor:public j1::MotorHal {
  bool enabled_;
 public:
  DcBenchMotor():enabled_(false){}
  bool ready() const{return true;}
  bool healthy() const{return true;}
  bool estopInput() const{return false;}
  bool enable(bool on){bench_stop_outputs();enabled_=on;return true;}
  void stop(){bench_stop_outputs();}
  bool rates(int32_t,int32_t){return false;}
  bool jog(uint8_t,int32_t,uint16_t){return false;}
  bool busy() const{return bench_pwm_active;}
  bool pwm(uint8_t axis,int16_t duty,uint16_t duration) {
    if(axis>3||!duty||duty>200||duty< -200||duration>400)return false;
    int16_t values[4]={0,0,0,0};values[axis]=duty;
    return pwmFour(values[0],values[1],values[2],values[3],duration);
  }
  bool pwmFour(int16_t m1,int16_t m2,int16_t m3,int16_t m4,uint16_t duration) {
    int16_t values[4]={m1,m2,m3,m4};
    if(!enabled_||!duration||duration>j1::PWM_FOUR_DURATION_MAX||(!m1&&!m2&&!m3&&!m4))return false;
    for(unsigned i=0;i<4;++i)if(values[i]>j1::PWM_FOUR_MAX||values[i]< -j1::PWM_FOUR_MAX)return false;
    bench_stop_outputs();
    // TIM3 clock is 8 MHz, ARR 799 -> hardware PWM at 10 kHz.
    TIM3->PSC=0;TIM3->ARR=799;TIM3->CNT=0;TIM3->CCMR1=0x6868;TIM3->CCMR2=0x6868;
    TIM3->CCR1=0;TIM3->CCR2=0;TIM3->CCR3=0;TIM3->CCR4=0;
    GPIOA->CRL=(GPIOA->CRL & ~0xff000000U)|0xaa000000U;
    GPIOB->CRL=(GPIOB->CRL & ~0xffU)|0xaaU;
    volatile uint16_t* compare[4]={&TIM3->CCR1,&TIM3->CCR2,&TIM3->CCR3,&TIM3->CCR4};
    uint32_t channels=0;
    for(unsigned i=0;i<4;++i) {
      const int16_t value=values[i];
      if(value) {
        direction_port[i]->BSRR=value>0?
          static_cast<uint32_t>(direction_positive[i])|(static_cast<uint32_t>(direction_negative[i])<<16):
          static_cast<uint32_t>(direction_negative[i])|(static_cast<uint32_t>(direction_positive[i])<<16);
        *compare[i]=static_cast<uint16_t>((value<0?-value:value)*800U/1000U);
        channels|=TIM_CCER_CC1E<<(4*i);
      }
    }
    TIM3->CCER=channels;TIM3->EGR=TIM_EGR_UG;TIM3->SR=0;
    const uint32_t saved=__get_PRIMASK();__disable_irq();
    bench_pwm_start=milliseconds;bench_pwm_duration=duration;bench_pwm_active=true;
    TIM3->CR1=TIM_CR1_ARPE|TIM_CR1_CEN;
    __set_PRIMASK(saved);return true;
  }
};
