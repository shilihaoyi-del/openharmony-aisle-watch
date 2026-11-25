# STM32F103RCT6 电机与通信固件

当前实际运行的是四路硬件 PWM 版 `DcFourWheel`，引脚来自目标板的原始固件备份。OM3/OM4 的 PWM 是 PB0/PB1，方向分别 PC6/PC7、PB14/PB15。新镜像和 MCU 输出测试已完成，实际车轮转动仍待用户确认。当前命令和验证范围见 [四电机说明](FOUR_MOTOR.md)。下文为保留的两路板与通信测试历史配置，不是当前四驱板的完整引脚定义。

来源为用户提供的《STM32 ROS机器人驱动板原理图.pdf》，第 1 页。主控为 STM32F103RCT6、256 KB Flash / 48 KB SRAM；CH340G 接 USART1，PA9 为 MCU TX、PA10 为 MCU RX。引脚档案见 `board_profile.json`。

原理图中 TB6612FNG 接两组 Motor1/2 编码器电机接口：PA6/PA7 为两路 PWM，PA5/PA4 为 AIN1/AIN2，PC4/PC5 为 BIN1/BIN2，编码器分别接 PB6/PB7 与 PA0/PA1。STBY 硬连 5V，没有 MCU STEP、DIR、EN 接口。

此前运行过 `DcBench` 配置，用户已确认 10V 编码器直流电机。2026-11-23 新增两路同步 `PWM_PAIR` 并完成指令测试后，用户反馈后两个电机未转，随后才确认实际板有第二块 TB6612。此两路方案现已由上述四路版替代。此前测试详见 [DC 测试结果](DC_BENCH.md)。

这与之前“两个步进轴、脉冲/秒”的假设不同。没有确认实际电机类型前，不把 J1 的脉冲命令解释成 PWM 占空比，也不生成默认启用 TB6612 电机的固件。

本目录提供一个可实际编译的、通信专用固件：

- 使用 8 MHz 内部 HSI，UART 115200、8N1；不依赖外部 PLL 配置。
- 保留 PA13/PA14 SWD，PC1 蓝灯以 1 秒周期闪烁。
- 启动早期即把 PA4/PA5/PA6/PA7、PC4/PC5 拉低，运行中也持续保持低。该设置不等于物理隔离电机电源或把 TB6612 STBY 拉低。
- J1 HELLO/STATUS 可响应；硬件绑定位始终为 0，ARM 返回 UNBOUND，任何步进点动或连续速度命令均不能驱动电机。
- 未实现实际电机控制、编码器采样、硬件急停输入或基于真实电机的看门狗验收。

在本机执行 `build.ps1`，使用已安装 Keil Arm Compiler 6、STM32F1xx DFP 2.4.1 和 CMSIS 5.8.0，输出到工作区 `artifacts/stm32f103rc_comm/`：

- `stm32f103rc_comm.bin`：Flash 起始地址 `0x08000000` 的二进制镜像。
- `stm32f103rc_comm.hex`：含地址信息的 Intel HEX。
- `stm32f103rc_comm.elf`：供调试使用。

构建脚本不会连接 ST-Link，也不会烧录。已有原固件备份在 `artifacts/stlink_backup/20261122-172929/`，文件为完整 256 KB。

2026-11-22，用户确认继续烧录并重新接好 SWD 后，通信测试镜像已经通过 ST-Link 写入目标 STM32。写入前再次完整备份 256 KB Flash；5320 字节的镜像通过 ST-Link 校验及独立逐字节读回比较，随后复位运行。

已通过 Nano 的实际 CH340 串口完成 HELLO/STATUS，状态为 DISARMED、bound=0、enabled=0、busy=0；ARM 实际返回 UNBOUND，之后 STATUS 仍禁止输出，STOP 成功。只测试了协议和使能拒绝，没有发送 JOG/WHEELS。ST-Link 读得 GPIOA ODR=0xA000、GPIOC ODR=0x2，与 PA4..PA7、PC4..PC5 均为低一致。

通信专用版的烧录记录、当次原固件备份和实际串口报告位于工作区 `artifacts/stlink_flash/20261122-211901/`。该保留镜像不支持任何电机运动；当前板上已更新为上述 DC 测试版。
