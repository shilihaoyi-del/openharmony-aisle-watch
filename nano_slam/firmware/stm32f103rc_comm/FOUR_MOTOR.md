# 当前四路硬件 PWM 配置

2026-11-23 当前板上是 `DcFourWheel`，6472 字节，配置标识 `original_board_four_pwm`。四路分别为：

- OM1：TIM3_CH1 / PA6，方向 PA5 / PA4。
- OM2：TIM3_CH2 / PA7，方向 PC4 / PC5。
- OM3：TIM3_CH3 / PB0，方向 PC6 / PC7。
- OM4：TIM3_CH4 / PB1，方向 PB14 / PB15。

引脚依据是烧录前从这块目标板完整读取的原始固件，不是把两份 PDF 的引脚拼接。原始备份在 `artifacts/stlink_backup/20261122-172929/original_flash_08000000_256k.bin`，SHA256 为 `469fff7a9f38bc74a030c56dbed6f1bb59e8b7292792e165ddffcfe1858f3d6c`。原固件电机初始化/速度函数使用 Flash `0x08006448` 的四组方向 GPIO、`0x08006458` 的 PWM GPIO，以及 `0x08005fc4`、`0x08005fcc`、`0x08005fd4` 的引脚掩码，四个 PWM 都使用 TIM3 CH1..4。工作区 `tools/recover_original_motor_pins.py` 可重新验证这些表和方向寄存器写入函数，结果保存在 `artifacts/car_diagnosis/original_motor_pins.json`。当前正方向沿用此前两路点动的符号，与原始固件 spin-positive 相反；实际整车前进方向尚需标定。

此前按另一份四驱 PDF 的固定高电平 PWM 方案做过一次适配，用户反馈四个电机均未转动，因此该方案已弃用，不是当前固件。当前保留此前前两路硬件 PWM 配置，扩展 TIM3_CH3/CH4，未增加占空比。

## 只读编码器固件

`build.ps1 -Mode EncoderOnly` 生成独立的 `artifacts/stm32f103rc_encoder/stm32f103rc_encoder.bin`。固件保持四路驱动输出关闭，USART1 只发送计数。每帧包含 STM32 的采样 `ms32`、序号、四个累计脉冲计数和四个累计无效跳变计数，并附 CRC16。上报频率约为 20 Hz。

引脚依据是原板备份里的 EXTI 处理程序与原有编码器日志打印顺序。四个计数槽从 `0x20000074` 开始依次排列，位置名称沿用原装固件，仍需在当前底盘手转验证。

- 左后 PB6 / PB7，原计数槽 `0x20000074`。
- 右后 PA0 / PA1，原计数槽 `0x20000078`。
- 右前 PC8 / PC9，原计数槽 `0x2000007C`。
- 左前 PA11 / PA12，原计数槽 `0x20000080`。

烧录工具在 `--profile encoder` 下先保存当前 Flash，再写入及逐字节回读。接回 Jetson 后用原 STM32 的物理 USB 路径查看计数。用手转动一个车轮，检查对应字段变化并记录向前转动的计数符号、转一圈的计数差以及无效跳变计数。轮式里程计需要四轮的实际直径、每圈计数、方向符号和有效轮距。

```bash
python3 /home/jetson/ws63_node/encoder_odometry.py --port /dev/serial/by-path/platform-70090000.xusb-usb-0:2.2:1.0-port0
```

标定后，使用 `--ros --diameters ... --ticks-per-rev ... --signs ... --track ...` 发布 `/wheel/odom`，四轮参数按左后、右后、右前、左前输入。轮速积分使用 STM32 的采样间隔，ROS 时间按 Jetson 接收时刻扣除估计的串口传输时间。航向在平面差速模型下由轮速差估算，协方差暂用保守初值。

## 已验证与待确认

新镜像烧录后逐字节读回一致，完整备份和日志在 `artifacts/stlink_flash/20261123-182549/`。四路 HAL 的模拟寄存器测试、原生协议测试，以及 Nano Python 2.7/3.6 各 14 项主机/伪串口测试均通过。

已实际发送 OM1、OM2、OM3、OM4 各一次 20% / 400 毫秒指令，最后四路一起输出一次。五次均收到运行、完成和停止确认；运行期间独立读得 TIM3 四个通道使能和 CCR 符合指令，结束后计时器停用、四路 PWM/方向全部清零。报告在 `artifacts/four_motor_diagnosis/20261123-182633/report.json`。**这只验证了控制执行和 MCU 寄存器，仍待用户确认此次四个电机是否实际转动，以及各接口对应哪侧车轮。**

板载 PC0 ADC 在停车时估算 VIN 约 10.9V，依据两份原理图均为 10k/1k 分压和标称 1.2V 内部参考；它不是每个 TB6612 VM 引脚的万用表读数，也没有验证带载电流。记录在 `artifacts/car_power/20261123-181835/report.json`。

## Nano 控制命令

```bash
cd /home/jetson/slam_ws/src/nano_slam/scripts
python car4_signal.py motor3 --send
python car4_signal.py motor4 --send
python car4_signal.py u1
python car4_signal.py u2
python car4_signal.py forward --send
python car4_signal.py left --send
python car4_signal.py right --send
python car4_signal.py stop --send
```

每条运动命令默认 20% / 250 毫秒，默认配置的 `--ms` 最大 400。去掉 `--send` 只预览报文。按四驱版原理图，`u1` 同时点动 OM1/OM2，`u2` 同时点动 OM3/OM4。同组两轮各用一个独立的电机输出，使用同一个占空比。实物端子位置先用 `motor1` 至 `motor4` 逐口标定。转弯时左侧默认为 OM1/OM2，如果左侧实际连接 OM3/OM4，使用 `--left-motors 3,4`。某个车轮方向相反时，用 `--motor-signs` 修正该路，例如 `--motor-signs=1,-1,1,1` 只翻转 OM2 的电气极性。若需要在不同负载下保持实际轮速一致，需用各轮编码器做闭环控制。

板端命令 `PWM_FOUR,d1,d2,d3,d4,duration_ms`，每路 -200..200 千分数、不能全零。上电 DISARMED，运动必须先 ARM；300 毫秒通信超时、SysTick 独立定时停止、500 毫秒协议硬上限和 IWDG 保留。只做开环控制，编码器不参与反馈，雷达保持停止。先前两路的 `car_signal.py` / PWM_PAIR 不适用于当前四驱镜像。

构建：`build.ps1 -Mode DcFourWheel`；烧录：`python tools/flash_comm.py --profile dc-four`。这些操作不会改变 Nano 风扇自启动服务。

### 四路 30% 点动固件

`build.ps1 -Mode DcFourWheel30` 构建独立的四路镜像，`python tools/flash_comm.py --profile dc-four-30` 会校验镜像和目标板、备份原固件，并在烧录后逐字节回读。该镜像的 `PWM_FOUR` 上限为 300‰，上电停车、点动时限和通信超时沿用现有逻辑。

在确认对应的 STM32 镜像和车轮转向后，使用 `car4_signal.py forward --profile four-pwm-30 --duty 300 --ms 250`。按设备填写 `--port` 和 `--motor-signs`，确保四路实际朝车头方向。执行前先预览，再加 `--send` 发送单次指令。

成组固件通过 `build.ps1 -Mode DcFourWheel30 -FiveSeconds -PairedDrivers` 构建。使用 `--profile four-pwm-30-5s-paired` 选择相应的 Jetson 控制参数。板端 `PWM_FOUR` 要求 OM1/OM2 的带符号占空比相同，OM3/OM4 也相同，每组可以独立停转。`motor1` 至 `motor4` 仍可用 20% 以内、400 毫秒以内的单路诊断信号核对端子。若一组内的实体车轮方向相反，断电后核对电机动力线极性。

带 `-EncoderReadback` 的成组固件支持串口 `ENC` 查询。加 `-AlignEncoderForward` 后，STM32 按 PB6/PB7、PA0/PA1、PC8/PC9、PA11/PA12 的顺序应用 `+1、-1、-1、+1`，并用 `J1ENC2` 标记已校正的帧。Jetson 查询程序 `encoder_odometry.py --query --port <串口>` 对旧 `J1ENC1` 在主机端应用这组符号，对 `J1ENC2` 直接显示板端计数。反转仍返回负数，查询命令不使能电机。

增加 `-FortyPercent` 或 `-FiftyPercent` 构建 40% 或 50% 点动固件，Jetson 使用对应的 `--profile four-pwm-40-5s-paired` 或 `--profile four-pwm-50-5s-paired`。成组测试默认请求所选占空比，单次最长 5 秒。上电时 PWM 关闭，单口诊断仍为 20%、400 毫秒以内。

`-SixtyPercent` 构建 60% 成组固件，对应 Jetson 的 `--profile four-pwm-60-5s-paired`。可用 `--duty 550` 指定 55%。

`-EightyPercent` 构建 80% 成组固件，对应 Jetson 的 `--profile four-pwm-80-5s-paired`。

`car4_signal.py forward --profile four-pwm-50-5s-paired` 默认预览同一帧四路 50%、600 毫秒的启动指令。STM32 在 TIM3 上同时启动四路 PWM。该配置使用当前电机板的 USB 物理路径，换插口时可通过 `--port` 指定新路径。
