#include <stdio.h>

// Order follows the target's original encoder counters (0x20000074..80).
// Left rear PB6/7, right rear PA0/1, right front PC8/9, left front PA11/12.
static const uint32_t ENCODER_LINES = 0x1bc3U;
static volatile uint32_t encoder_count[4];
static volatile uint32_t encoder_invalid[4];
static uint8_t encoder_state[4];

static void encoder_read(unsigned wheel, uint8_t state) {
  static const int8_t transitions[16] = {0, 1, -1, 0, -1, 0, 0, 1,
                                          1, 0, 0, -1, 0, -1, 1, 0};
  const uint8_t before = encoder_state[wheel];
  encoder_state[wheel] = state;
  if ((before ^ state) == 3U) {
    ++encoder_invalid[wheel];
  } else {
    encoder_count[wheel] += static_cast<uint32_t>(transitions[before * 4U + state]);
  }
}

static uint32_t pending(uint32_t lines) {
  const uint32_t active = EXTI->PR & lines;
  EXTI->PR = active;
  return active;
}

extern "C" void EXTI0_IRQHandler() {
  if (pending(1U)) encoder_read(1, GPIOA->IDR & 3U);
}

extern "C" void EXTI1_IRQHandler() {
  if (pending(2U)) encoder_read(1, GPIOA->IDR & 3U);
}

extern "C" void EXTI9_5_IRQHandler() {
  const uint32_t active = pending(0x3c0U);
  if (active & 0xc0U) encoder_read(0, (GPIOB->IDR >> 6) & 3U);
  if (active & 0x300U) encoder_read(2, (GPIOC->IDR >> 8) & 3U);
}

extern "C" void EXTI15_10_IRQHandler() {
  if (pending(0x1800U)) encoder_read(3, (GPIOA->IDR >> 11) & 3U);
}

static void encoder_init() {
  RCC->APB2ENR |= RCC_APB2ENR_AFIOEN | RCC_APB2ENR_IOPAEN | RCC_APB2ENR_IOPBEN | RCC_APB2ENR_IOPCEN;
  (void)RCC->APB2ENR;
  // Floating input mode leaves the encoder interface's existing pull networks in control.
  GPIOA->CRL = (GPIOA->CRL & ~0xffU) | 0x44U;
  GPIOA->CRH = (GPIOA->CRH & ~0x000ff000U) | 0x00044000U;
  GPIOB->CRL = (GPIOB->CRL & ~0xff000000U) | 0x44000000U;
  GPIOC->CRH = (GPIOC->CRH & ~0xffU) | 0x44U;
  AFIO->EXTICR[0] &= ~0xffU;
  AFIO->EXTICR[1] = (AFIO->EXTICR[1] & ~0xff00U) | 0x1100U;
  AFIO->EXTICR[2] = (AFIO->EXTICR[2] & ~0xf0ffU) | 0x22U;
  AFIO->EXTICR[3] &= ~0xfU;
  encoder_state[0] = (GPIOB->IDR >> 6) & 3U;
  encoder_state[1] = GPIOA->IDR & 3U;
  encoder_state[2] = (GPIOC->IDR >> 8) & 3U;
  encoder_state[3] = (GPIOA->IDR >> 11) & 3U;
  EXTI->RTSR |= ENCODER_LINES;
  EXTI->FTSR |= ENCODER_LINES;
  EXTI->PR = ENCODER_LINES;
  EXTI->IMR |= ENCODER_LINES;
#ifdef BOARD_ENCODER_QUERY
  NVIC_SetPriority(EXTI0_IRQn, 2U);
  NVIC_SetPriority(EXTI1_IRQn, 2U);
  NVIC_SetPriority(EXTI9_5_IRQn, 2U);
  NVIC_SetPriority(EXTI15_10_IRQn, 2U);
#endif
  NVIC_EnableIRQ(EXTI0_IRQn);
  NVIC_EnableIRQ(EXTI1_IRQn);
  NVIC_EnableIRQ(EXTI9_5_IRQn);
  NVIC_EnableIRQ(EXTI15_10_IRQn);
}

static void encoder_report(j1::ReplySink& replies, uint32_t sequence) {
  uint32_t tick, count[4], invalid[4];
  const uint32_t flags = __get_PRIMASK();
  __disable_irq();
  tick = milliseconds;
  for (unsigned i = 0; i < 4; ++i) {
    count[i] = encoder_count[i];
    invalid[i] = encoder_invalid[i];
  }
  __set_PRIMASK(flags);
#ifdef BOARD_ENCODER_FORWARD
  // Convert these two channels to chassis-forward polarity, with uint32 wraparound.
  count[1] = 0U - count[1];  // PA0/PA1
  count[2] = 0U - count[2];  // PC8/PC9
  const char* prefix = "J1ENC2";
#else
  const char* prefix = "J1ENC1";
#endif
  char body[118];
  const int length = snprintf(body, sizeof(body), "%s,%lu,%lu,%lu,%lu,%lu,%lu,%lu,%lu,%lu,%lu",
      prefix, (unsigned long)sequence, (unsigned long)tick,
      (unsigned long)count[0], (unsigned long)count[1], (unsigned long)count[2], (unsigned long)count[3],
      (unsigned long)invalid[0], (unsigned long)invalid[1], (unsigned long)invalid[2], (unsigned long)invalid[3]);
  if (length < 0 || static_cast<unsigned>(length) >= sizeof(body)) return;
  char frame[125];
  snprintf(frame, sizeof(frame), "$%s*%04X\n", body, j1::crc16(body, static_cast<size_t>(length)));
  replies.send(frame);
}
