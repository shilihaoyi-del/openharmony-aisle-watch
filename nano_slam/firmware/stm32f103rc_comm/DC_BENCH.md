# TB6612 直流电机有限点动

本页为此前两路配置的历史记录。用户之后确认有第二块 TB6612 和 OM3/OM4；当前已由原始固件备份恢复完整四路硬件 PWM，引脚、最新执行记录和命令见 [四电机说明](FOUR_MOTOR.md)。

用户已确认实际为编码器直流电机，电机动力供电为 10V。主控和引脚继续使用 `board_profile.json` 中从原理图核对的 STM32F103RCT6/TB6612 配置。

## 2026-11-23 两路同步直行与转弯

随后用户反馈：四个电机中同一组的两个均未转动。因此下述记录仅代表信号执行成功，整车四电机测试未通过。已追加两路各一次 20%/400 毫秒点动，在运行期间通过 ST-Link 独立读取实际寄存器：Motor1 的 TIM3 CCER=1、CCR1=160、CCR2=0、PA5/PA4=1/0；Motor2 的 CCER=16、CCR1=0、CCR2=160、PC4/PC5=1/0；两次 CR1=129，AFIO MAPR=0，PA6/PA7 为复用输出。两路实际 MCU 配置均符合当前原理图引脚档案，测试后 PWM 和方向均关闭。没有测量 TB6612 输出端电压，也未确认车轮转动；仍待用户确认不转组的实际接口丝印及是否接在另一块驱动模块。诊断报告：`artifacts/car_diagnosis/20261123-180413/report.json`。

按用户要求新增有限开环指令 `PWM_PAIR,left,right,duration_ms`。左右占空比均为 -200..200 千分数，不能同时为零，时长为 1..400 毫秒；停止使用 STOP。两路使用同一个 TIM3 计数器一起启动、一起定时停止，保留 300 毫秒通信超时、500 毫秒协议硬上限和独立看门狗。上电仍为 DISARMED，不自动运动。

6228 字节的新镜像已烧录、逐字节读回验证并复位运行。已实际依次发送直行 `(200,200,250)`、左转 `(0,200,250)`、右转 `(200,0,250)`，每次之间停顿 1.5 秒；每次均收到 PWM_TEST/busy=1、随后任务完成、最后 STOP/DISARMED 确认。最终独立读回 TIM3 CR1=0、CCER=0，电机方向和 PWM GPIO 均为低。烧录备份位于 `artifacts/stlink_flash/20261123-175915/`，指令测试报告位于 `artifacts/car_signals/20261123-180021/report.json`。

当前按 Motor1=左侧、Motor2=右侧、正 PWM=前进配置。现场车轮前进方向尚未确认，发送成功不代表已验证整车轨迹。并联的编码器输入不参与开环控制，也未用于证明四个电机分别转动。

Nano 上执行以下命令，每条均为一次短时输出并自动停止：

```bash
python /home/jetson/slam_ws/src/nano_slam/scripts/car_signal.py forward --send
python /home/jetson/slam_ws/src/nano_slam/scripts/car_signal.py left --send
python /home/jetson/slam_ws/src/nano_slam/scripts/car_signal.py right --send
python /home/jetson/slam_ws/src/nano_slam/scripts/car_signal.py stop --send
```

支持 `backward`、`--duty 200`、`--ms 250`；去掉 `--send` 只显示协议帧。若一侧前进方向相反，使用 `--left-sign -1` 或 `--right-sign -1`；若左右通道相反，使用 `--swap`。这些方向选项每次命令都需携带，不会自动保存标定。雷达在本次测试中保持停止。

## 当前接线变更

用户随后将四个电机接为“两路驱动、每路并联两个电机”，且没有电机型号。驱动通道仍只有两路，不是四路独立控制。此前下文中的两次结果是在原两路点动阶段取得，不能直接作为新并联负载的四电机验收结果。

此前接线检查时尚未发送运动命令：每组编码器应只取一套或另行独立接入，不能将两套 A/B 并联后当作每个电机的反馈。并联启动电流会叠加，原板没有电流传感器。现有程序不能从两个计数输入分别证明四个电机都转动。本次开环信号测试没有完成电机电流或驱动负载能力验收。

用户随后确认 A/B 也并联。当时已向真实板发送 STOP 并读回 DISARMED、enabled=0、busy=0，尚未执行新接线的运动测试。编码器输出应在断开动力电源后分开：每个驱动组只接一台电机的 A/B，另外一台 A/B 分别绝缘，或接到独立的额外输入。用户之后明确要求先实现基本开环信号，最新执行结果见上节。

构建：`build.ps1 -Mode DcBench`。输出为 `artifacts/stm32f103rc_dc_bench/`，与通信专用镜像分开。镜像上电 DISARMED，不会自动转动。2026-11-22 已烧录并逐字节读回校验 DC 测试版，真实板报告 bound=1、上电未使能。初次初始化等待 IWDG 更新时发现 LSI 尚未开启，已修复为先启动 LSI 再配置看门狗，并加入有界等待。

已先后单独执行 `PWM,0,200,250` 与 `PWM,1,200,250`：每次一个电机，正方向 20% 占空比、250 毫秒。它不是步进脉冲命令，不能保证某个转速或角度。测试期间另一个电机保持停止。

## 实物结果

- Motor1 编码器 TIM4 CNT 从 0 到 330，变化 +330；Motor2 当次变化为 0。
- Motor2 编码器 TIM2 CNT 从 0 到 65171，按 16 位回绕解释为 -365；Motor1 当次变化为 0。
- 两次均完成有限运动，随后 STATUS 为 DISARMED、enabled=0、busy=0。
- 两次均独立读回 TIM3 CR1/CCER 和电机控制 GPIO，确认 PWM 关闭、控制线归零。
- 编码器符号不一致需在实际底盘里程计中按轮子安装方向标定；它不等于某个方向接错。
- 基础电机通道和反馈测试通过，不代表转速闭环、整车里程计或自主导航已完成实车验收。

此前单通道版本固件为 5996 字节，烧录与备份记录在 `artifacts/stlink_flash/20261122-214042/`。两次原始测试报告分别位于 `artifacts/dc_bench/20261122-214146/`、`artifacts/dc_bench/20261122-214219/`。

实现的停止机制：

- PWM 限于绝对值 200 千分数（20%），单次 1..400 毫秒，协议硬上限 500 毫秒。
- SysTick 中断负责独立计时清除 TIM3 输出，不依赖 UART 主循环完成；通信续期超时仍为 300 毫秒。
- IWDG 看门狗用于主循环停滞后的复位，正常循环持续喂狗；调试暂停时冻结看门狗，避免烧录时持续复位。
- STOP/ESTOP 禁止 PWM、清除方向并撤销会话；运行中不接受新的 WHEELS。
- 此板无 MCU 控制的 STBY/硬件急停引脚；仍需保留切断动力的能力。

引脚：TIM3 CH1/CH2 对应 PA6/PA7，PWM 10kHz；AIN1/AIN2=PA5/PA4，BIN1/BIN2=PC4/PC5。正方向映射 IN1 高、IN2 低，实际车轮前进方向需现场确认。TIM4（PB6/PB7）和 TIM2（PA0/PA1）启用编码器计数，后续可在测试前后读取 CNT 核实转动；尚未将这些计数作为 ROS 里程计发布。

已完成 Cortex-M3 镜像编译；在本机 WSL 以及 Nano 的 C++ 原生模拟板与 Python 伪串口中，10 项测试全部通过，覆盖 PWM 限幅、时长、重复帧不重发、超时和停止。实物结果如上，仅对应本次有限点动。

完成烧录并读回校验后才可执行：

```bash
python ~/slam_ws/src/nano_slam/scripts/motor_link.py --send --port /dev/serial/by-id/usb-1a86_USB_Serial-if00-port0 pwm --axis 0 --duty 200 --ms 250
```

Nano 侧客户端会先握手、确认硬件已绑定、ARM、发送 PWM、每约 80 毫秒续期、确认有限任务完成，再 STOP。当前旧通信固件会在运动前被 bound 检查拦截。

雷达已通过现有 Slamtec SDK 发送 `stop()` 和 `setMotorSpeed(0)`，均返回成功，当时没有扫描驱动进程。测试中不启动雷达。
