# Jetson Nano 二维激光建图

SSH 维护工具默认连接 `jetson@jetson.local`，可用 `JETSON_HOST` 指定实际主机。

最新电机状态（2026-11-23）：用户确认实物有两块 TB6612、OM1..OM4 四个输出。当前已从目标板原始固件备份恢复四路引脚，烧录 6472 字节四路硬件 PWM 版，并分别发送四路点动和一次四路同步信号；运行期间寄存器与结束后停车状态均核实。实际车轮转动、左右分组与前进方向仍待用户确认。使用 `car4_signal.py`，当前说明见 [四电机控制](nano_slam/firmware/stm32f103rc_comm/FOUR_MOTOR.md)。雷达保持停止，Nano 风扇自启动配置保持有效。以下电机记录为早期阶段，不能覆盖这里的最新板型确认。

## 早期电机协议与测试记录

2026-11-22 已新增 [J1 串口协议](nano_slam/MOTOR_PROTOCOL.md)、Nano 端收发和有限点动工具、可移植的 C++ 板端状态机及 Arduino 风格未绑定硬件示例。CLI 默认预览报文；已在 Nano 的 Python 2.7/3.6 与 C++ 模拟板之间通过跨语言伪串口测试。后续电机控制固件仍需实现实际硬件接口，当前没有向实际电机发送运动指令。

同日已根据用户原理图确认 STM32F103RCT6＋TB6612FNG，并通过 ST-Link 烧录[禁止电机输出的通信测试版](nano_slam/firmware/stm32f103rc_comm/README.md)。5320 字节逐字节读回一致，实际 CH340 串口握手成功；ARM 返回 UNBOUND，电机输出保持禁止。当前完成了真实板卡的通信验证，尚未适配真实电机运动。备份、校验与串口记录在 `artifacts/stlink_flash/20261122-211901/`。

当前实际状态已更新：用户确认使用 10V 编码器直流电机，已烧录 5996 字节 DC 有限测试版并逐字节校验，两路分别以 20% 占空比、250 毫秒点动。Motor1 编码器变化 +330、Motor2 变化 -365；每次另一路计数不变，结束后 STATUS 为 DISARMED、PWM/方向引脚归零。当前原理图通过两路基础测试，详情见 [DC 点动测试](nano_slam/firmware/stm32f103rc_comm/DC_BENCH.md)。雷达保持停用。转速闭环、方向标定和 ROS 实车里程计仍待实现。

最新接线变更：用户确认四个电机现在接为每通道并联两个，电机型号/电流未知。尚未对新并联负载发送运动指令，需先确认编码器接法和限流/电流条件。驱动软件仍为两个独立通道，不能把历史两路单电机结果当作四电机全部通过。

## 无驱动板阶段的自主导航

现已新增独立的模拟底盘、激光与里程计，配合 GMapping 建图、AMCL 定位、move_base/Navfn/DWA 导航、速度门控与自动验收脚本。使用专用 ROS master 11312，与实物雷达所在的 11311 隔离；模拟器拒绝在实物 master 上启动。软件操作、局限和未来板卡接口见 [导航说明](nano_slam/NAVIGATION.md)。

此功能验证的是仿真软件闭环。真实地图仍保持原样，不能把仿真通过视为真实底盘、真实导航或地图精度已通过验收。

2026-11-06 已完成一轮实际仿真验收：模拟扫图零接触；AMCL + move_base 的 5 个目标全部通过，最大到点误差约 0.194 米；包含新增障碍绕行；激光、里程计和指令超时、软件急停及非法速度拦截均通过。结果副本在 `artifacts/simulation/`。Nano 桌面已打开 `simulation_rviz`，可以在独立仿真 master 中使用 2D Nav Goal；模拟底盘在验收结束后处于停车状态。

## 当前实际状态（2026-11-05）

- Ubuntu 18.04.6、L4T 32.7.3、ROS Melodic；Hector SLAM 已安装。
- 已有 `/home/jetson/slam_ws` 工作空间与 RPLIDAR 驱动，原配置为 A1、115200 波特率、`laser` 坐标系。雷达实际型号仍待核实，不能仅凭 launch 文件认定型号。
- 雷达重新插入后变为 `/dev/ttyUSB1`。已恢复驱动，实际 `/scan` 频率约 6.96 Hz，每帧约 1147 个测量点；其中一次采样有 551 个有效测距。
- 新包已部署到 `/home/jetson/slam_ws/src/nano_slam`；`/nano_hector_mapping` 已启动，真实地图有已观测栅格和障碍物，`map → laser` TF 持续更新。
- 已在 Nano 桌面启动 `/nano_mapping_rviz` 显示真实 `/map`、`/scan`。初始静止地图保存为 `/home/jetson/maps/initial_20261105_221250.pgm` 和同名 YAML。
- 启动脚本已改用 `/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0`，避免插拔后串口编号变化。
- 地图保存脚本已在独立测试话题验证像素翻转、占据/空闲/未知编码、分辨率、原点和角度、防覆盖、拒绝全未知地图。测试文件已清除，没有发布模拟 `/scan`。
- 根分区检查时约剩 2.9 GB；本项目未安装大依赖、未录制 rosbag、未删除原有文件。

## 第一轮扫图结果（2026-11-05 23:28，中国时间）

用户确认扫图完成后，已保存真实地图：

- Nano：`/home/jetson/maps/room_20261105_232806.pgm`、同名 `.yaml`。
- 本地：`artifacts/room_20261105_232806.pgm`、同名 `.yaml`；`.png` 是只裁掉外围未知区域并放大的显示预览，原始 PGM 未裁剪。
- 栅格 1024×1024，分辨率 0.05 米；已观测 112157 个栅格，原始地图中有 8340 个占据值不低于 65 的栅格。
- 已观测栅格的外接范围约 19.35×20.70 米，这不是经实测校准的房间尺寸。已观测栅格面积合计约 280.39 平方米，不能用作房间建筑面积。
- 保存时仍能收到真实 `/scan`，地图日志未发现匹配所查关键词的错误；已验证下载的 PGM 尺寸、YAML 图片引用和分辨率。
- 地图预览存在明显墙线重影、重复轮廓与错位。此结果证明数据采集、SLAM 与地图导出流程已跑通；没有完成导航精度验收。不能通过简单图片修饰修复定位漂移。
- 后续改善先检查雷达固定水平、移动速度与转弯稳定性，建议从小房间短路线重新验证。较长路线需进一步评估真实轮里程计/IMU 与具备回环优化的方案；现有步进电机不能自动提供可靠实测里程计。
- 本次没有录制历史扫描 rosbag，不能事后从当前 PGM 恢复完整扫描序列来重新优化。

已保存文件不会随继续建图而改变。后台雷达、建图节点和 RViz 仍运行；停止方式见下文。没有发送车轮控制命令。

## 在 Nano 上继续

1. 给雷达供电，并用 USB 数据线接入 Nano。默认使用已确认的固定设备标识，无需依赖 ttyUSB 编号；也可以给启动脚本传入明确的串口路径。
2. 恢复驱动和建图：

```bash
bash ~/slam_ws/src/nano_slam/scripts/start.sh
```

脚本先检查串口和真实扫描，必要时只重启失效的 `rplidarNode`；保留已有 ROS master 和其他节点。新驱动配置沿用现有 A1 参数，启动将使激光雷达自身旋转。没有任何车轮控制或 `/cmd_vel` 发布。

3. 在 Nano 桌面终端显示地图：

```bash
source ~/slam_ws/src/nano_slam/scripts/env.sh
rviz -d ~/slam_ws/src/nano_slam/rviz/mapping.rviz
```

RViz 固定坐标为 `map`，显示 `/map` 和 `/scan`。先检查静止时墙壁形状，再缓慢推车；雷达保持水平、安装牢固，避开车体遮挡。步进电机尚未接入。不要在电机保持锁定时强行推车，按底盘允许的方式手动移动。

4. 完成一圈后，在另一个终端保存真实地图，名称可自行更改：

```bash
source ~/slam_ws/src/nano_slam/scripts/env.sh
python ~/slam_ws/src/nano_slam/scripts/save_map.py ~/maps/room_01
```

输出 `~/maps/room_01.pgm` 和 `~/maps/room_01.yaml`。已有文件不会覆盖；没有收到地图或地图没有观测区域时退出报错。此脚本替代尚未安装的 `map_server/map_saver`，生成常规 ROS 三值地图文件。

## 坐标与范围

当前是以雷达为本体的建图模式：`map → laser`，不需要轮里程计，不伪造 `odom → base_link`，不假定雷达与底盘之间的安装偏移。地图分辨率为 0.05 米，1024×1024 栅格，范围约 51.2×51.2 米。该配置不包含小车导航或底盘控制。

后续接入底盘时，需要确认电机驱动器、控制板、轮径、轮距、减速比、编码器与 IMU，并测量 `base_link → laser`。Hector 没有全局回环优化，不能保证长距离行驶后无累计漂移。

## 诊断与停止

```bash
source ~/slam_ws/src/nano_slam/scripts/env.sh
python ~/slam_ws/src/nano_slam/scripts/check_scan.py
rosnode info /nano_hector_mapping
tail -n 40 ~/slam_ws/logs/nano_lidar.log
tail -n 40 ~/slam_ws/logs/nano_slam.log
```

停止建图：`rosnode kill /nano_hector_mapping`。该操作会丢弃未保存的内存地图，先保存。需要停止雷达时用 `rosnode kill /rplidarNode`。项目未设置开机自启。

## 本地维护

`tools/ssh_run.py` 和 `tools/deploy.py` 使用 Paramiko，通过临时环境变量 `JETSON_SSH_PASSWORD` 或交互提示读取密码。本地首次接受的主机公钥保存在被 Git 忽略的 `tools/known_hosts`，后续拒绝不匹配的公钥。

部署后通过 ROS launch 解析和目标机 Python 2.7 语法检查。`scripts/test_map_save.sh` 使用 `/nano_slam_verification/map` 验证保存器；其模拟数据与真实 `/map`、`/scan` 隔离。运行测试会创建并清理专用临时目录。

## 固定机位通道监测

- 第一块 WS63 使用 `artifacts/ws63_watch/WS63-1-Change-Watch-Sender.fwpkg`，在 OpenHarmony LiteOS Mini 上建立基线、判断变化并上报证据。第二块使用 `artifacts/ws63_watch/WS63-2-Change-Watch-Receiver.fwpkg`，通过星闪 SLE SSAP 接收后从 USB 串口交给 Jetson。
- 雷达保持水平、固定在离地约 40 厘米的位置。每次启动时先保持通道处于正常状态，让节点用 7 帧建立基线。每个角格至少需要 5 个距离相差不超过 15 厘米的样本，至少三分之二的监测角格要有基线。默认监测正前方约 73°，可用 `WS63_WATCH_ROI_FIRST`、`WS63_WATCH_ROI_COUNT` 调整 72 格前向扇区中的监测范围。安装位置、方向或正常背景变动后，重新启动采集基线。
- 稳定版默认只对 3 米内的障碍报警，远处回波仍用于建立基线和复核恢复。近距回波需要比基线缩短 25 厘米。至少 3 个固定相邻角格持续 3 帧即可确认占道，移动目标需在连续 3 帧中覆盖至少 5 个相邻角格且相邻帧的区段重叠。目标跨到另一个区段时仍保持同一次占道。受影响区段至少三分之二的角格重新测到可信距离，且稳定 3 帧，才上报恢复。持续缺测和扫描中断会进入可见性不足状态。
- 正常运行每秒上报一条 41 字节心跳，变更事件立即上报并在后续报告中最多补发两次，带触发帧时间戳和最多 16 格的前后测距。接收端按会话、报告序号及事件号统计并去重。显示的是收到的应用层字节数，不含链路开销。同帧数完整上报按每帧 176 字节估算。
- 原型路径为雷达 USB → Jetson ROS `/scan` → USB 串口 → 感知端 WS63 → 星闪 SLE → 接收端 WS63 → Jetson。各传感器的当前数据输入以实物和接线为准，当前监测数据源为 2D 雷达。软件监测沿用离地 40 厘米的扫描面，使用场景包括遮挡或占道事件记录。

稳定版只需为感知端刷入 `artifacts/ws63_watch/WS63-1-Change-Watch-Stable-Sender.fwpkg`。接收端沿用已安装的监测固件。在 Nano 终端启动时可用 `WS63_WATCH_DETECT_RANGE` 设定障碍距离上限（米），该选项要求感知端支持新版配置握手。脚本等到接收端收到有效星闪报告后才启动雷达。

```bash
session="$HOME/slam_ws/logs/watch/$(date +%Y%m%d_%H%M%S)"
WS63_CHANGE_WATCH=1 WS63_WATCH_DETECT_RANGE=3.0 bash ~/ws63_node/run_sle_slam.sh "$session"
```

在 SLAM 全屏界面选择「通道监测」查看状态、链路流量和事件前后距离。终端用 Ctrl+C 结束，或创建 `$session/stop`；`$session/scans.bag` 保存输入扫描和监测 ROS 话题，`$session/gateway.log` 保存事件 JSON。原 SLAM 启动入口认得相同两块固件，继续使用 `run_sle_slam.sh` 的默认模式即可。

用 `python3 ws63_node/tests/test_change_watch.py` 在具备 C 编译器的开发机上验证固件算法与 Jetson 解析器。这个回放用合成输入验证协议与判断流程。
