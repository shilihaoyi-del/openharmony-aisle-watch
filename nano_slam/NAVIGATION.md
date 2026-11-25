# 不依赖驱动板的 SLAM 与自主导航软件

本包包含两个互相隔离的运行环境：实物雷达建图沿用 ROS master `11311`，仿真使用仅监听本机通信的 `http://127.0.0.1:11312`。仿真中所有速度指令只进入模拟底盘。`sim_base.py` 与自动验收程序会拒绝在其他 master 地址运行。

仿真是软件闭环验证，不能代替实物底盘验收。模型使用理想轮里程计、二维矩形环境、差速底盘和带少量测距噪声的模拟雷达；不模拟丢步、轮胎打滑、倾斜、地面高差、接线或驱动板故障。

## 已实现的软件流程

1. `sim_base.py` 发布模拟 `/scan`、`/odom` 和 `odom → base_link → laser`。模拟真值 `/sim/ground_truth` 只用于独立评判到点误差，不供导航算法使用。
2. GMapping 读取模拟激光与里程计，生成一张新的地图。测试沿固定路线扫图并保存 `~/maps/sim_room.pgm` 和 YAML；导航不能直接读取仿真场景中的障碍物定义。
3. 独立重新启动底盘后，`map_server` 加载刚才 SLAM 保存的地图，AMCL 通过激光与里程计定位。
4. `move_base` 调用 Navfn 全局规划、DWA 局部规划和代价地图，输出 `/nav_cmd_vel`。
5. `safety_gate.py` 在激光超时、里程计超时、指令超时、软件急停或非有限速度指令时输出零速度，否则限速后发往 `/cmd_vel`。
6. 模拟底盘另有 0.4 秒指令超时停车，并记录模拟接触次数。自动验收要求接触次数为零，不能靠模拟器的接触保护冒充避障成功。

## 一键运行

以下命令在 Nano 终端执行。依赖已按需安装：`move_base`、`amcl`、`map_server`、`gmapping`、`dwa_local_planner`；apt 新增 19 个包，并因依赖升级 1 个 SDL 库，未进行全系统升级，新增磁盘占用约 19 MB。

```bash
# 1. 在独立 master 上开启仿真建图
bash ~/slam_ws/src/nano_slam/scripts/run_simulation.sh mapping
source ~/slam_ws/src/nano_slam/scripts/simulation_env.sh

# 2. 自动移动模拟底盘扫图，保存 sim_room.pgm / sim_room.yaml
python ~/slam_ws/src/nano_slam/scripts/sim_acceptance.py mapping

# 3. 重新启动为地图定位与导航模式
bash ~/slam_ws/src/nano_slam/scripts/run_simulation.sh navigation

# 4. 自动执行到点、绕障和停车验收
python ~/slam_ws/src/nano_slam/scripts/sim_acceptance.py navigation
```

再次建图会为已有的仿真地图加时间戳备份；不会覆盖真实房间地图。正在运行自动验收时不要同时在 RViz 下发目标或另起一个验收进程。

显示仿真导航：

```bash
source ~/slam_ws/src/nano_slam/scripts/simulation_env.sh
rviz -d ~/slam_ws/src/nano_slam/rviz/navigation_simulation.rviz __name:=simulation_rviz
```

在窗口中使用 **2D Nav Goal**，在白色可通行区域按下并拖动设置位置与朝向。可使用 **2D Pose Estimate** 提供初始位姿。地图单位为米，绿色为全局路径，橙色为局部路径，蓝色箭头为模拟底盘真值；仿真场景不是之前扫到的真实房间。

```bash
# 软件急停与解除（仅当前 source 的 master）
rosservice call /safety/estop 'data: true'
rosservice call /safety/estop 'data: false'

# 停止仿真场景与导航节点，保留独立 master
bash ~/slam_ws/src/nano_slam/scripts/run_simulation.sh stop
```

## 验收内容与文件

自动验收包含：完整模拟扫图且零接触、保存非空地图、独立 AMCL 定位、多目标到点、静态障碍绕行、地图外新增障碍绕行、激光中断停车、里程计中断停车、速度指令超时停车、软件急停、非法数值拦截。

导航到点判据使用独立真值：位置误差小于 0.30 米，AMCL 位置误差小于 0.25 米；这些是当前仿真验收阈值，不是实车精度承诺。

结果在 `~/slam_ws/logs/simulation/mapping_report.json`、`navigation_report.json`；进程日志为 `mapping.log`、`navigation.log`；自动测试输出为 `mapping_test.log`、`navigation_test.log`。报告中的 `passed` 字段和实际终端输出是判定依据。

### 2026-11-06 实际验收结果

建图整圈零接触，保存地图包含 17757 个已观测栅格、1182 个占据值不低于 65 的栅格。此地图随后重新加载供导航使用。

导航 5 个目标全部成功，模拟真值的最大到点位置误差为 0.194 米，到点时最大 AMCL 位置误差为 0.060 米，全程模拟接触次数为零。原地图中不存在的新增障碍在第 3 个目标测试期间出现，规划器绕行通过，随后移除；其他测试的轨迹可能穿过这个障碍曾经所在的位置，这不表示第 3 次测试发生穿越。

激光超时、里程计超时、速度指令超时、软件急停和非有限速度输入拦截均通过。另有矩形碰撞几何测试，覆盖直墙、旋转车身、动态障碍插入及角点间隙。

已实测仿真 master 仅监听 `127.0.0.1:11312`。真实 master 的 `/cmd_vel` 不存在，仿真 master 上 `/cmd_vel` 的底盘订阅者为 `/sim_base`，没有将模拟指令发送给实物底盘。

本地副本为 `artifacts/simulation/` 中的 JSON 报告、PGM/YAML 地图、`navigation_preview.png`。这些数字只描述此次理想里程计模型下的仿真结果。

## 将来接实物时的接口

导航主体与电机驱动板型号无关。底盘适配层至少实现：订阅安全限速后的 `/cmd_vel`（米/秒、弧度/秒），输出带正确时间戳的 `/odom`，发布 `odom → base_link`；雷达输出 `/scan`，并提供实测安装外参 `base_link → laser`。AMCL 或 SLAM 负责 `map → odom`，二者不能同时争用这一变换。

`launch/navigation.launch` 是预留的硬件无关导航入口，要求显式传入地图路径；它不启动任何板卡驱动或仿真底盘。示例：

```bash
# 仅在底盘、TF、真实扫描已独立验收后执行
roslaunch nano_slam navigation.launch map:=/absolute/path/to/map.yaml config:=/absolute/path/to/measured_robot_navigation.yaml
```

`config/navigation.yaml` 中车身 0.40×0.30 米、最高 0.35 米/秒等参数均为仿真占位值。接实车前必须换成实测车身轮廓、速度、加速度和安装外参，并在单片机侧实现独立通信超时停车与硬件急停。当前 `map → laser` 的纯雷达 Hector 配置不能直接与这个导航入口混用。

上游：ROS Navigation `melodic-devel`、OpenSLAM GMapping、AMCL 和 DWA。当前仿真不需要购买或确定电机驱动板。
