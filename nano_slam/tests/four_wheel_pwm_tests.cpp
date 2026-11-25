// Actual four-channel HAL against simulated registers. No physical I/O.
#include "j1_protocol.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
struct PinWrite {
  uint32_t* odr;bool reset;
  void operator=(uint32_t value) {
    if(reset)*odr&=~value;else *odr=(*odr&~(value>>16))|(value&0xffffU);
  }
};
struct GPIO_TypeDef {
  uint32_t ODR=0,CRL=0x44444444,CRH=0x44444444;PinWrite BSRR,BRR;
  GPIO_TypeDef():BSRR{&ODR,false},BRR{&ODR,true}{}
};
struct Timer {
  uint32_t CR1=0,DIER=0,SR=0,PSC=0,ARR=0,CNT=0,CCMR1=0,CCMR2=0,CCER=0,EGR=0;
  uint16_t CCR1=0,CCR2=0,CCR3=0,CCR4=0;
};
struct Clock {uint32_t APB1ENR=0,CSR=2;};
struct Debug {uint32_t CR=0;};
struct Watchdog {uint32_t KR=0,PR=0,RLR=0,SR=0;};
static GPIO_TypeDef portA,portB,portC;
static Timer timer;static Clock clock_regs;static Debug debug;static Watchdog watchdog;
#define GPIOA (&portA)
#define GPIOB (&portB)
#define GPIOC (&portC)
#define TIM3 (&timer)
#define RCC (&clock_regs)
#define DBGMCU (&debug)
#define IWDG (&watchdog)
static const uint32_t RCC_APB1ENR_TIM3EN=2,DBGMCU_CR_DBG_IWDG_STOP=256;
static const uint32_t RCC_CSR_LSION=1,RCC_CSR_LSIRDY=2;
static const uint32_t TIM_CR1_CEN=1,TIM_CR1_ARPE=128,TIM_EGR_UG=1,TIM_CCER_CC1E=1;
static uint32_t milliseconds=0,primask=0;
static uint32_t __get_PRIMASK(){return primask;}
static void __disable_irq(){primask=1;}
static void __set_PRIMASK(uint32_t value){primask=value;}
static void outputs_off() {
  TIM3->DIER=0;TIM3->CCER=0;TIM3->CR1=0;TIM3->SR=0;
  TIM3->CCR1=TIM3->CCR2=TIM3->CCR3=TIM3->CCR4=0;
  GPIOA->BRR=0xf0;GPIOB->BRR=0xc003;GPIOC->BRR=0xf0;
  GPIOA->CRL=(GPIOA->CRL&0xffffU)|0x22220000U;
  GPIOB->CRL=(GPIOB->CRL&~255U)|0x22U;
  GPIOB->CRH=(GPIOB->CRH&0xffffffU)|0x22000000U;
  GPIOC->CRL=(GPIOC->CRL&0xffffU)|0x22220000U;
}
#include "../firmware/stm32f103rc_comm/dc_four_wheel.h"
int main() {
  bench_init();DcBenchMotor motor;
  assert(!motor.busy()&&GPIOA->ODR==0&&GPIOB->ODR==0&&GPIOC->ODR==0);
  assert(!motor.pwmFour(200,200,200,200,250));motor.enable(true);
  assert(!motor.pwmFour(0,0,201,0,250));assert(!motor.pwmFour(0,0,0,0,250));
  assert(!motor.pwmFour(0,0,200,0,401));
  assert(motor.pwmFour(200,200,200,200,400));
  assert(primask==0&&TIM3->PSC==0&&TIM3->ARR==799&&TIM3->CCER==0x1111&&TIM3->CR1==129);
  assert(TIM3->CCR1==160&&TIM3->CCR2==160&&TIM3->CCR3==160&&TIM3->CCR4==160);
  assert((GPIOA->CRL>>24)==0xaa&&(GPIOB->CRL&255)==0xaa);
  assert(GPIOA->ODR==(1U<<5)&&GPIOB->ODR==(1U<<14)&&GPIOC->ODR==((1U<<4)|(1U<<6)));
  milliseconds=399;bench_timer_tick();assert(motor.busy());
  milliseconds=400;bench_timer_tick();assert(!motor.busy()&&!TIM3->CR1&&!TIM3->CCER);
  assert(GPIOA->ODR==0&&GPIOB->ODR==0&&GPIOC->ODR==0);
  assert(motor.pwmFour(-200,-200,-200,-200,250));
  assert(GPIOA->ODR==(1U<<4)&&GPIOB->ODR==(1U<<15)&&GPIOC->ODR==((1U<<5)|(1U<<7)));
  motor.stop();assert(GPIOA->ODR==0&&GPIOB->ODR==0&&GPIOC->ODR==0);
  assert(motor.pwm(2,200,250));assert(GPIOC->ODR==(1U<<6)&&TIM3->CCER==0x100&&TIM3->CCR3==160);
  assert(GPIOA->ODR==0&&GPIOB->ODR==0);motor.stop();
  assert(motor.pwm(3,200,250));assert(GPIOB->ODR==(1U<<14)&&TIM3->CCER==0x1000&&TIM3->CCR4==160);
  milliseconds=650;bench_timer_tick();assert(!motor.busy()&&GPIOB->ODR==0);
  assert(!TIM3->CCR1&&!TIM3->CCR2&&!TIM3->CCR3&&!TIM3->CCR4);
  motor.enable(false);assert(!motor.pwm(3,200,250));assert(!motor.pwm(4,200,250));
  puts("FOUR_WHEEL_NATIVE_PWM_TESTS_PASSED");
}
