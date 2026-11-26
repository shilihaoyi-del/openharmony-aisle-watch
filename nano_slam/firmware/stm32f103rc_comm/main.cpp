// Default: communication only. BOARD_DC_BENCH adds bounded PWM tests after explicit ARM.
#include "stm32f10x.h"
#include "j1_protocol.h"
#include <stdint.h>

uint32_t SystemCoreClock = 8000000U;
static volatile uint32_t milliseconds = 0;

static void outputs_off() {
#ifdef BOARD_DC_FOUR
  RCC->APB2ENR |= RCC_APB2ENR_IOPAEN | RCC_APB2ENR_IOPBEN | RCC_APB2ENR_IOPCEN;
  (void)RCC->APB2ENR;
  if (RCC->APB1ENR & RCC_APB1ENR_TIM3EN) {
    TIM3->DIER=0;TIM3->CCER=0;TIM3->CCR1=0;TIM3->CCR2=0;TIM3->CCR3=0;TIM3->CCR4=0;TIM3->CR1=0;TIM3->SR=0;
  }
  GPIOA->BRR=(1U<<4)|(1U<<5)|(1U<<6)|(1U<<7);
  GPIOB->BRR=(1U<<0)|(1U<<1)|(1U<<14)|(1U<<15);
  GPIOC->BRR=(1U<<4)|(1U<<5)|(1U<<6)|(1U<<7);
  GPIOA->CRL=(GPIOA->CRL & 0x0000ffffU)|0x22220000U;
  GPIOB->CRL=(GPIOB->CRL & ~0xffU)|0x22U;
  GPIOB->CRH=(GPIOB->CRH & 0x00ffffffU)|0x22000000U;
  GPIOC->CRL=(GPIOC->CRL & 0x0000ffffU)|0x22220000U;
#else
  RCC->APB2ENR |= RCC_APB2ENR_IOPAEN | RCC_APB2ENR_IOPCEN;
  (void)RCC->APB2ENR;
  GPIOA->BRR = (1U<<4)|(1U<<5)|(1U<<6)|(1U<<7);
  GPIOC->BRR = (1U<<4)|(1U<<5);
  // Set the output latch low before changing input pins to push-pull outputs.
  GPIOA->CRL = (GPIOA->CRL & 0x0000ffffU) | 0x22220000U;
  GPIOC->CRL = (GPIOC->CRL & ~(0xffU<<16)) | (0x22U<<16);
#endif
}

#if defined(BOARD_ENCODER_ONLY) || defined(BOARD_ENCODER_QUERY)
#include "encoder_telemetry.h"
#endif
#if defined(BOARD_DC_FOUR) && !defined(BOARD_ENCODER_ONLY)
#include "dc_four_wheel.h"
#elif defined(BOARD_DC_BENCH)
#include "dc_bench.h"
#endif

extern "C" void SystemInit() {
  // Independent of external crystal/PLL: reset to internal 8 MHz HSI.
  RCC->CR |= RCC_CR_HSION;
  while (!(RCC->CR & RCC_CR_HSIRDY)) {}
  RCC->CFGR &= ~RCC_CFGR_SW;
  while (RCC->CFGR & RCC_CFGR_SWS) {}
  RCC->CFGR = 0;
  RCC->CR &= ~(RCC_CR_PLLON | RCC_CR_HSEON | RCC_CR_CSSON);
  FLASH->ACR = 0;
  SCB->VTOR = 0x08000000U;
  outputs_off();
}
extern "C" void SysTick_Handler() {
  ++milliseconds;
#ifdef BOARD_DC_BENCH
  bench_timer_tick();
#endif
}
extern "C" void Default_Handler() { outputs_off();for (;;) {} }
extern "C" void _sys_exit(int) { Default_Handler(); }
extern "C" void _ttywrch(int) {}
void operator delete(void*) noexcept {}
void operator delete[](void*) noexcept {}
extern "C" void __cxa_pure_virtual() { Default_Handler(); }

static void uart_init() {
  RCC->APB2ENR |= RCC_APB2ENR_IOPAEN | RCC_APB2ENR_USART1EN;
  // CH340 RXD -> PA9 (MCU TX), CH340 TXD -> PA10 (MCU RX).
  GPIOA->CRH = (GPIOA->CRH & ~((0xfU<<4)|(0xfU<<8))) | (0xaU<<4) | (0x4U<<8);
  USART1->CR1 = 0;USART1->CR2 = 0;USART1->CR3 = 0;
  USART1->BRR = 69U; // 8 MHz / 69 = 115942 baud, +0.64% nominal error.
#ifdef BOARD_ENCODER_ONLY
  USART1->CR1 = USART_CR1_UE | USART_CR1_TE;
#else
  USART1->CR1 = USART_CR1_UE | USART_CR1_TE | USART_CR1_RE;
#endif
}
class SafeMotor : public j1::MotorHal {
 public:
  bool ready() const { return false; }
  bool healthy() const { return true; }
  bool estopInput() const { return false; }
  bool enable(bool on) { outputs_off();return !on; }
  void stop() { outputs_off(); }
  bool rates(int32_t,int32_t) { outputs_off();return false; }
  bool jog(uint8_t,int32_t,uint16_t) { outputs_off();return false; }
  bool busy() const { return false; }
};
class UartReplies : public j1::ReplySink {
#ifdef BOARD_ENCODER_QUERY
  uint32_t encoder_sequence_ = 0;
#endif
 public:
#ifdef BOARD_ENCODER_QUERY
  bool reportEncoders() {
    encoder_report(*this, encoder_sequence_++);
    return true;
  }
#endif
  void send(const char* text) {
    for (;*text;++text) {
      uint32_t begin=milliseconds;
      while (!(USART1->SR & USART_SR_TXE)) {
        if (static_cast<uint32_t>(milliseconds-begin)>20U) { outputs_off();return; }
      }
      USART1->DR=static_cast<uint8_t>(*text);
    }
  }
};

int main() {
  outputs_off();
  uart_init();
  SysTick_Config(8000U);
#ifdef BOARD_ENCODER_QUERY
  // Encoder edge traffic must not delay the independent PWM deadline.
  NVIC_SetPriority(SysTick_IRQn, 0U);
  encoder_init();
#endif
#ifdef BOARD_ENCODER_ONLY
  UartReplies replies;
  encoder_init();
  uint32_t next = milliseconds;
  uint32_t sequence = 0;
  for (;;) {
    if (static_cast<int32_t>(milliseconds - next) >= 0) {
      next = milliseconds + 50U;
      encoder_report(replies, sequence++);
    }
    __WFI();
  }
#else
  // Blue PC1 LED is the only intentional toggling GPIO in this image.
  GPIOC->BRR=1U<<1;
  GPIOC->CRL=(GPIOC->CRL & ~(0xfU<<4)) | (0x2U<<4);
#ifdef BOARD_DC_BENCH
  bench_init();DcBenchMotor motors;
#else
  SafeMotor motors;
#endif
  UartReplies replies;j1::Controller protocol(motors,replies);
  for (;;) {
#ifdef BOARD_DC_BENCH
    IWDG->KR=0xaaaa;
#else
    outputs_off();
#endif
    protocol.tick(milliseconds);
    for (unsigned n=0;n<32 && (USART1->SR & (USART_SR_RXNE | USART_SR_ORE));++n) {
      uint32_t status=USART1->SR;
      char byte=static_cast<char>(USART1->DR); // SR then DR clears receive errors.
      if (status & (USART_SR_ORE | USART_SR_FE | USART_SR_NE)) continue;
      protocol.feed(byte,milliseconds);
    }
    if ((milliseconds/500U)&1U) GPIOC->BSRR=1U<<1;
    else GPIOC->BRR=1U<<1;
  }
#endif
}
