# openharmony-aisle-watch
基于开源鸿蒙与星闪的工业通道变更取证节点，面向仓库周转通道、产线物料入口和设备间巡检。系统使用二维激光雷达采集通道轮廓，由运行轻量版开源鸿蒙的 WS63 建立正常测距基线，识别占道、恢复和可见性不足。正常时通过星闪 SLE 每秒发送心跳，发生变化时按需上报时间、角区和前后测距。同一目标横移时合并为一次占道事件。Jetson Nano 提供实时监测、事件回看、传输统计和局部 SLAM 显示，便于现场人员复核占道位置与清障结果。

## 源码与复现

- [WS63 固件、Jetson 网关和监测界面](ws63_node/)
- [两块 WS63 的构建与实机验证说明](ws63_node/README.md)
- [ROS 建图包及配置](nano_slam/)
- [项目部署和开发记录](PROJECT_NOTES.md)

SSH 维护脚本可用环境变量 JETSON_HOST 指定设备地址，默认尝试 jetson.local。设备密码通过环境变量或交互方式提供。

## ESP32 现场确认与电脑端接收

ESP32-S3 通过 USB 接入 Jetson。占道事件触发红灯，现场人员按下 BOOT 后，Jetson 按事件编号保存确认结果，ESP32 蓝灯反馈。监测页顶部展示 ESP32 的实际串口报文、收包计数和最近一次按键确认。

ESP32-S3 固件构建使用 ESP-IDF 5.5。进入 [固件目录](ws63_node/esp32_station/)，运行 `idf.py set-target esp32s3` 和 `idf.py build`。默认配置对应 32 MB 八线 Flash，板载 RGB 引脚可通过 `idf.py menuconfig` 调整。

在 Jetson 启动监测页服务后，电脑可通过 SSH 转发打开同一页面。电脑需要 Python 和 Paramiko。先核验 Jetson 的 SSH 主机密钥，再运行以下命令。可以用实际地址替换 `jetson.local`。

```powershell
python tools/open_jetson_dashboard.py --host jetson.local
```

浏览器页面为 `http://127.0.0.1:8787/watch`，关闭启动工具会结束转发。
