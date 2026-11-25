# 面向巡检设备的开源鸿蒙末端感知节点

参赛主体是运行 OpenHarmony 轻量系统的 WS63。Jetson Nano 接收并显示采集结果，后续可接 ROS。截图要求的是轻量版开源鸿蒙和面向产业场景的末端采集与上报，IoT 总线组件和轻量网络协议属于鼓励项。截图未列出的提交要求，以赛事正式附件为准。

当前原型把板载 USER 键当作设备限位触点。WS63 通过 OpenHarmony IoT GPIO 读取电平，连续三次得到相同值后确认状态，状态变化立即上报，平时约每秒发送一次心跳。每帧包含节点运行时间、序号、触点状态和是否变化。板上的 USER 键模拟开关触点，按下为闭合。代码按润和 `nearlink_dk_3863` 产品的 GPIO13 编译，烧录前核对实物板型和原固件留存方式。

## 编译与实机检查

使用海思 `OpenHarmony-v5.1.0-Release` 的 `default-ws63-without-xts.xml`。构建产品为 `nearlink_dk_3863`，产品类型为 `mini`。安装构建工具后，在 Linux 下将独立 SDK 路径传给 `build.sh`。当前工作区已编译出 `artifacts/ws63_contact/ws63-liteos-app_all.fwpkg`，包内已核对采集程序入口。烧录步骤见 [海思 OpenHarmony WS63 构建和烧录指南](https://gitee.com/HiSpark/ohos_ws63/blob/master/README.md)。

2026-11-24，BurnTool 在 Windows 的 `COM34` 上记录了完整固件包烧录成功。该口对应 `USB\VID_1A86&PID_7522`（CH340K）。Windows 实机监听连续读到 16 帧，序号 22 到 37，设备时间戳每帧递增 1000 毫秒。WS63 接回 Jetson 后连续收到 35 帧，序号无断档，记录在 `artifacts/ws63_contact/live_jetson.jsonl`。后续实测 USER 键按下时 Jetson 收到 `closed=1, event=1`（序号 223，215490 毫秒），松开时收到 `closed=0, event=1`（序号 228，219900 毫秒）。原始记录在 `artifacts/ws63_contact/user_key_jetson.jsonl`。

烧录后把 WS63 数据口重新接回 Jetson。Jetson 上已安装 `99-ws63-contact.rules`，用 `1a86:7522` 确认串口型号，并给 `jetson` 账号访问权限。使用固定名称 `/dev/ws63-contact`，无需随 `/dev/ttyUSB*` 编号变化修改命令。监视器已上传到 Jetson。

同日有线验收监听 45 秒，收到 50 帧。序号无断档，设备时间戳始终递增，稳定状态下的心跳间隔为 1000 毫秒。记录到 3 组完整闭合与释放，其中 2 组闭合约 50 毫秒。摘要和原始数据分别为 `artifacts/ws63_contact/wired_20261124-141430.json` 和同名 `.jsonl`。

```bash
python3 /home/jetson/ws63_node/monitor.py /dev/ws63-contact --baud 115200 --seconds 30
```

观察心跳以及按住和松开 USER 键时的状态。按住时预期 `closed=1`，松开时预期 `closed=0`。`seq=0`、`event=1` 也可能是启动后的初始状态帧。接收端已在 Jetson 上通过伪串口测试。Windows 捕获的启动日志中有 LittleFS 挂载告警，持久化存储尚未验收。

## 参赛演示还需完成的实测

- 将触点原型接到相应的实际场景。可将按键替换成限位开关，或接入 IMU 做巡检振动监测。若要展示雷达、IMU、轮速三源同步，需另完成车端传感器接线、雷达协议适配及编码器采集。
- 双板星闪 SLE 已通过真实雷达上报测试。若计划将分布式软总线写入参赛报告，需要实测软总线组网和数据传输。
- 采集上电到首包的时间、连续上报的丢包情况、断开后的恢复时间，以及供电端工作和待机电流。当前代码用 10 毫秒采样确认触点，低功耗指标仍需在实物上验证。

## 多传感器感知固件

`fusion` 是运行在 WS63 上的 OpenHarmony mini 感知节点。当前接线下，Jetson 订阅已有 ROS 驱动发布的 `/scan`，也可订阅 `sensor_msgs/Imu` 和由轮编码器生成的 `nav_msgs/Odometry`。它先用每个角度分组内的最近有效距离将雷达数据压到最多 72 个距离值，然后把三类数据通过 USB 送给 WS63。WS63 负责时间对齐、滤波、校验和上报。压缩距离用于感知遥测，原始 `/scan` 可继续供 SLAM 使用。

- 三种输入使用同一 ROS 时钟的采样时间。雷达以扫描中点为基准，WS63 额外记录接收时刻的本机运行时间。源时间和本机时间各自以毫秒记录，按 32 位回卷。ROS 消息的时间戳要由实际驱动提供。
- WS63 缓存各 32 个 IMU 和里程计样本，轮询时最多等待 80 ms，也可在收到下一帧雷达时先发出上一帧。它选择距基准最近的样本，IMU 时间差允许 ±40 ms，里程计允许 ±80 ms。上报附带所选样本的时间差，缺测值显示为 `null`。
- WS63 剔除超出传感器量程的距离值，对连续 IMU 的加速度、角速度按 0.5 权重做一阶平滑，超过 100 ms 的间隔会重置滤波。轮式里程计保留其原始样本。
- USB 采用 115200 8N1。二进制帧由 `A5 5A`、类型、单字节载荷长度、载荷和两字节小端 CRC-16/CCITT-FALSE 组成，CRC 覆盖类型、长度和载荷。建议将 IMU 速率控制在 100 Hz 以内进行初测。测试输入和输出带 `test` 标记。

### 打包和接收

`build.sh <SDK 路径> fusion` 构建感知端，`build.sh <SDK 路径> receiver` 构建第二块 WS63 上的 SLE 接收端。每个角色构建后请立即保存编译产物，因为 SDK 使用同一个输出路径。省略角色参数仍构建触点版本。

当前已在 Jetson 上验收的双板固件是 `artifacts/ws63_burn/WS63-1-Fusion-Sender-SSAP.fwpkg` 和 `artifacts/ws63_burn/WS63-2-SLE-Receiver-SSAP.fwpkg`。两块板接回各自的 Jetson USB 口后，可以先跑有线自检，再在 ROS 驱动发布真实数据时验证 `/scan`。网关脚本本身不启动雷达或小车。

```bash
python3 /home/jetson/ws63_node/fusion_gateway.py --self-test
source /opt/ros/melodic/setup.bash
python /home/jetson/ws63_node/fusion_gateway.py --ros \
  --receive-port /dev/serial/by-path/platform-70090000.xusb-usb-0:2.3:1.0-port0 \
  --output-topic /ws63/fusion
```

`--receive-port` 使输出仅来自接收端的星闪回传。启用时，默认以最多 4 Hz 向感知端提交雷达帧，保留最多 72 个分区，并丢弃采样时间距 Jetson 接收时钟超过 1000 ms 的旧报文。用户可用 `--scan-hz`、`--bins` 和 `--max-age-ms` 调整。`/ws63/fusion` 发布 JSON 字符串，含传输方式、采样时间戳和接收时的数据年龄。

IMU 和轮编码器驱动接入后，用 `--imu` 和 `--odom` 指定实际话题。Jetson 目前的 `/dev/imu_usb` 是雷达 CP2102 串口的别名。SLE 传输用 SSAP Notification，节点名为 `WS63-FUSION`，接收端将收到的完整报文转发到其 USB 串口。两块板同时接入时根据物理 USB 路径区分。

### 验证边界

- Jetson 上使用伪串口连接其原生编译的感知逻辑，Python 2 和 Python 3 自检均通过。测试用例覆盖三路匹配、IMU 滤波、雷达量程、CRC 拒收、时钟回卷，以及过期和不同测试模式样本的隔离。另在隔离的 ROS Melodic Master 上用三种 ROS 消息验证了转换、时间对齐和输出。两项均使用合成输入。
- 真实雷达测试中，Jetson 收到 83 帧原始 `/scan` 数据，逐帧核对了 40 帧经 WS63 处理并通过 SLE 返回的上报。采样时间戳和各分区距离均匹配，测试后雷达停止。IMU 尚未接入，当前 STM32 固件未采集编码器，两项在实测上报中为 `null`。要让 WS63 直接采样，需确认实物雷达接口和配置，把 IMU 接到可用的 I²C 或 SPI，并让 STM32 经 UART 上报编码器采样和时间戳。
- 已另外编译 STM32 只读编码器固件，并部署计数接收及里程计节点。完成四轮标定后，网关可用 `--odom /wheel/odom` 接收。固件与标定说明见 [STM32 四路编码器](../nano_slam/firmware/stm32f103rc_comm/FOUR_MOTOR.md#只读编码器固件)。
- 当前 SDK 的 `nearlink_dk_3863` mini 产品链接了 SLE 协议栈。鸿蒙分布式软总线仍需为两端选定可运行、可互通的运行时和适配方案，当前 SSAP 路径不经 DSoftBus。 [OpenHarmony 分布式软总线](https://github.com/openharmony/communication_dsoftbus/blob/master/README_zh.md) · [海思 SLE 传感器上报](https://docs.hisilicon.com/projects/fbb_ws63/master/samples/connectivity/sle/data-comm/sensor-report.html)

## Jetson 桌面 SLAM 界面

双击 Jetson 桌面的「星闪 SLAM」，或在 Jetson 浏览器打开 `http://127.0.0.1:8787/`。桌面快捷方式会在需要时启动本机服务。界面显示占据地图、星闪扫描点、雷达姿态、轨迹与两路帧计数。支持拖动、滚轮缩放和图层切换。

「实测记录」显示用原地实测的 `/scan_sle` 重新建出的局部地图。打开界面无需启动硬件。「实时」在 `run_sle_slam.sh` 启动采集期间显示同一条链路的实时地图。该脚本会启动 ROS、雷达、WS63 接收和 Hector。完成现场扫图后可通过 ROS `map_saver` 另行保存整图和 YAML。

最终机架的激光扫描面离地 40 cm。采集脚本默认选取原始 `laser` 坐标中以 175° 为中心的 110° 扇区，忽略 0.40 m 以内的近距回波，建图上限为 10.0 m，并受雷达驱动量程限制。缺失测距留空。发布给 Hector 的 `/scan_sle` 使用 `laser_front` 坐标系，正前方为 `+X`，避免 Hector 将实体前方的近距回波按雷达后方过滤。原始 `/scan` 照常写入同一会话的 ROS bag，供复核安装角度。

安装改变时可用 `WS63_FRONT_CENTER`、`WS63_FRONT_WIDTH`、`WS63_MIN_RANGE`、`WS63_MAX_RANGE` 在启动时覆盖默认值。角度用度，距离用米。将 `WS63_FRONT_WIDTH` 设为 `0` 可关闭扇区裁剪和坐标旋转。

前向模式默认使用 144 个角度桶。网关把同一帧按角度拆成两段，间隔 180 ms 发送，每段走现有 WS63 固件和 SLE 协议。Jetson 收齐采集时间和角度参数匹配的两段后，再发布融合报告和 `/scan_sle`。原地实测在 144 桶模式下完整回传约 2.35 帧/秒，同场景下 72 桶约 3.63 帧/秒。需要更高帧率时，可以用 `WS63_SCAN_BINS=72` 启动。

机架保持原位时，可用 `WS63_STATIC_SWEEP=1` 采集静止精扫图。此模式默认使用 350 桶，110° 扇区下角度步距约 0.314°。星闪每帧分成五段，完整扫描约每秒一帧。网关在最近七帧里找同角度下至少三次相差不超过 12 cm 的回波，从最近的可信距离组中取一个实测值，通过 `/scan_sle_static` 建图。此模式需要机架全程静止，原始雷达缺测的方向留为未知。移动时使用默认 144 桶，或设置 `WS63_SCAN_BINS=72` 获得更高帧率。

星闪建图的栅格发布周期为 0.5 秒，Hector 的栅格更新位姿阈值为 7 cm 或约 2°。桌面每 0.4 秒读取一次实时状态，保持默认 5 cm 地图分辨率。

## 参赛现场演示

以工业通道巡检为例，Jetson 的雷达驱动产生 `/scan`，网关裁剪和分段后通过 USB 串口交给运行 OpenHarmony 轻量版的感知端 WS63。感知端复核距离、标记节点时间并通过星闪 SLE SSAP Notification 上报。接收端 WS63 使用另一个 USB 串口把无线回传交给 Jetson，Jetson 校验、重组并发布 `/scan_sle` 供 Hector 建图。 [OpenHarmony WS63 构建仓库](https://gitee.com/HiSpark/ohos_ws63) · [海思星闪传感器上报](https://docs.hisilicon.com/projects/fbb_ws63/master/samples/connectivity/sle/data-comm/sensor-report.html)

双击桌面「星闪 SLAM」打开全屏演示。地图、逐段追踪和逐行日志共用「实时／实测记录」切换。选择追踪帧可查看每段提交和返回的时间、长度、WS63 序号、CRC、节点时间及整帧发布，也可导出 JSON。`run_sle_slam.sh` 会把 `/ws63/link` 一并存入本次 ROS bag。完成率按已经发布或已超时的整帧统计，采集到 ROS 发布的时间包含采集、USB、固件处理及无线回传，功耗和纯空口时延需要单独测量。

「逐跳链路」显示激光雷达、感知 WS63、星闪 SLE、接收 WS63 和 Jetson 的分段进度。实测记录可用「播放此帧」按原捕获时序回放，实时采集时显示当前帧的提交、回传、CRC 与整帧发布状态。

桌面「星闪传输日志」在独立终端逐行打印最近一次实测，并自动接续实时采集。终端和地图可以同时查看。

现场采集时，在 Jetson 终端运行以下命令，在界面选择「实时」。结束采集时按 Ctrl+C，采集程序会关闭雷达并保存 ROS bag。

```bash
bash ~/ws63_node/run_sle_slam.sh "$HOME/ws63_node/maps/demo_$(date +%Y%m%d_%H%M%S)"
```

界面的「拟合墙线」使用同一帧连续回波提取短直线，遇到缺测或相邻点间距超过 24 cm 时分段。紫色线段显示在占据栅格上方，只供观察。 [ROS 激光线段提取项目](https://github.com/kam3k/laser_line_extraction)
