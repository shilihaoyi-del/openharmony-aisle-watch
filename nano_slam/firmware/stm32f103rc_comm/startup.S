.syntax unified
.cpu cortex-m3
.thumb
.eabi_attribute 24,1
.eabi_attribute 25,1

.section STACK,"aw",%nobits
.balign 8
.space 4096
.global __initial_sp
__initial_sp:

.section HEAP,"aw",%nobits
.balign 8
.global __heap_base
__heap_base:
.space 1024
.global __heap_limit
__heap_limit:

.section RESET,"a",%progbits
.balign 256
.global __Vectors
__Vectors:
.word __initial_sp
.word Reset_Handler
.rept 13
.word Default_Handler
.endr
.word SysTick_Handler
#if defined(BOARD_ENCODER_ONLY) || defined(BOARD_ENCODER_QUERY)
.rept 6
.word Default_Handler
.endr
.word EXTI0_IRQHandler
.word EXTI1_IRQHandler
.rept 15
.word Default_Handler
.endr
.word EXTI9_5_IRQHandler
.rept 16
.word Default_Handler
.endr
.word EXTI15_10_IRQHandler
.rept 19
.word Default_Handler
.endr
#else
.rept 60
.word Default_Handler
.endr
#endif

.section .text.Reset_Handler,"ax",%progbits
.balign 2
.global Reset_Handler
.type Reset_Handler,%function
.thumb_func
Reset_Handler:
  bl SystemInit
  b __main

.global __use_no_semihosting
.equ __use_no_semihosting,0
