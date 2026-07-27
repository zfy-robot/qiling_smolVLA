# S4 Isaac Lab 抓取调试项目说明

这个文件是当前项目的唯一调试记录和继续开发入口。后续 AI 或人工接手时，先读这个文件，不要再从零猜控制链路。

## 当前目标

在 Isaac Lab 中稳定导入 S4 人形机器人，搭建桌面、红蓝物块、盘子场景，然后控制右臂移动到目标物块上方，继续完成真实接触抓取流程。

当前阶段已经做到：

- 仿真和控制命令分离。
- 机器人启动后双臂基本稳定。
- 物块、盘子能稳定生成在桌面上。
- 右臂可以通过简单笛卡尔小步控制移动 TCP 到物块目标点附近。
- 可以可视化手部 TCP 和目标 TCP。
- 已加入关节限位、失稳保护、TCP 偏移修正。

下一阶段重点是：把 `reach-block` 扩展成 `approach -> lower -> close -> lift` 的抓取状态机，并继续调手腕姿态和手指闭合策略。

## 当前目录框架

```text
my_isaaclab_project/
├── README.md                         # 唯一项目说明、踩坑记录、后续计划
├── run.sh                            # 统一入口
├── configs/
│   └── s4_bimanual_dataset.json      # 桌面高度/场景资产参数
├── s4_robot/
│   ├── __init__.py
│   ├── s4_robot_cfg.py               # URDF 路径、关节分组、默认姿态、URDF 限位
│   ├── simulation.py                 # Isaac Lab 场景、机器人、桌子、物块、盘子、reset
│   ├── arm_control.py                # 右臂 TCP 控制、手部命令、键盘 jog、JSON 工具
│   └── control_mapping.py            # 26 维动作和仿真关节顺序映射
└── scripts/
    ├── 03_joint_debug.py             # joint-debug 入口
    ├── 03_record_physics_dataset.py  # 主仿真入口，轮询控制 JSON 并写入仿真
    ├── control_arm.py                # 非 Isaac 进程，只负责写 /tmp/s4_arm_control.json
    └── set_joint_command.py          # 写 /tmp/s4_joint_command.json 的手动关节工具
```

## 启动流程

先启动仿真：

```bash
cd /home/zfy/smolVLA/my_isaaclab_project
bash run.sh sim --print-layout --show-tcp-frames
```

`--show-tcp-frames` 会显示：

- `/World/Visuals/RightHandTCP`：估算右手 TCP，位置为 `right_wrist_yaw_link + wrist-frame TCP offset`，姿态跟随 `right_wrist_yaw_link`。
- `/World/Visuals/TargetBlockTCP`：当前物块目标 TCP，位置为 `block_pos + reach offset`，姿态为世界坐标对齐。

另开终端发送右臂控制命令：

```bash
cd /home/zfy/smolVLA/my_isaaclab_project
bash run.sh control reach-block --block blue --z-offset 0.20
```

停止自动右臂控制：

```bash
bash run.sh control stop
```

手部开合：

```bash
bash run.sh control hand open
bash run.sh control hand close
bash run.sh control reach-block --block blue --hand close
```

右臂直接关节目标测试，用来确认执行器链路是否正常：

```bash
bash run.sh control test-right-arm
```

键盘/JSON 手动调关节：

```bash
bash run.sh joint-debug --print-layout
python scripts/set_joint_command.py right_elbow_joint=-0.8 rh_index_mcp_pitch=1.0
```

## 控制链路

```text
bash run.sh control reach-block
  -> scripts/control_arm.py
  -> 写 /tmp/s4_arm_control.json
  -> 正在运行的 scripts/03_record_physics_dataset.py 轮询这个 JSON
  -> s4_robot/arm_control.py 计算右臂目标
  -> scripts/03_record_physics_dataset.py 把 right_arm/right_hand 覆盖到 full simulator-order joint target
  -> robot.set_joint_position_target(...)
```

重要点：

- 仿真启动时会把 `/tmp/s4_arm_control.json` 重置成 `idle`。
- `idle` 时保持 `reset_scene()` 返回的完整仿真关节目标，不再每帧从 26 维 action 重映射。
- 只有收到 `mode: reach-block` 后才启用右臂笛卡尔控制。
- 控制只覆盖 `RIGHT_ARM_JOINTS + RIGHT_HAND_JOINTS`，其余关节保持 reset 姿态。
- 最终写入仿真的关节目标会按 URDF limit clamp。

## 当前控制方法

`reach-block` 不使用 Isaac Lab `DifferentialIKController`。之前用过 IK，出现过手臂回零、卡住、不按预期移动的问题，所以现在不用。

当前方法在 `s4_robot/arm_control.py`：

1. 读取目标物块世界坐标。
2. 目标 TCP = `block_pos + reach offset`。
3. 当前 TCP = `right_wrist_yaw_link` 位置 + wrist 坐标系 TCP offset 旋转到世界系后的偏移。
4. 用目标 TCP 和当前 TCP 的误差，计算目标 wrist 位置。
5. 取右臂 7 个关节对应的 wrist 位置 Jacobian。
6. 用 damped least squares 算一个小的 `dq`。
7. 加一个 nullspace posture 项，把 7 自由度冗余轻微拉回默认折臂姿态。
8. 右臂目标按 URDF 关节限位 clamp。
9. `smooth_command()` 再做每帧目标平滑。

当前 TCP 偏移结论：

```python
DEFAULT_TCP_OFFSET_WRIST = np.array([0.0, 0.0, -0.10], dtype=np.float32)
```

也就是：最后一个手腕坐标系沿 z 负方向偏移 `0.1m` 近似为手掌 TCP。这个结论来自 `--show-tcp-frames` 可视化检查。之前误以为是 x 方向，导致手看起来去物块前方而不是正上方。

可调 TCP 长度：

```bash
bash run.sh control reach-block --block blue --z-offset 0.20 --tcp-z-offset -0.12
```

## 当前关键参数

这些是用户已经调过、当前比较合适的参数。不要在没有明确要求时改代码默认值。

`scripts/03_record_physics_dataset.py`：

- `--robot-base-z 0.98`
- `--task-x 0.50`
- `--task-y -0.05`
- `--block-y-offset 0.20`
- `--plate-x 0.50`
- `--joint-stiffness 140.0`
- `--joint-damping 28.0`
- `--target-alpha 0.08`
- `--max-joint-step 0.012`

`s4_robot/arm_control.py`：

- `DEFAULT_TCP_OFFSET_WRIST = (0.0, 0.0, -0.10)`
- `max_cart_step = 0.008`
- DLS damping 当前为 `0.08`
- 右臂每帧 `dq` clamp 到 `[-0.025, 0.025]`

`s4_robot/s4_robot_cfg.py` 默认手臂姿态：

- left shoulder pitch `-0.12`
- left shoulder roll `0.28`
- left elbow `-1.35`
- right shoulder pitch `-0.12`
- right shoulder roll `-0.28`
- right elbow `-1.35`

## 场景位置说明

世界坐标里机器人固定在原点附近，桌子和物块在正 X 方向。

当前代码中 `--task-x` 同时传给：

- `TaskLayout.table_center_x`
- `TaskLayout.block_x`

所以现在改 `--task-x` 会同时移动桌子视觉中心和物块 X。

如果只想让物块离机器人近一点、桌子位置不变，需要改 `scripts/03_record_physics_dataset.py` 的 `make_scene_cfg()`，把：

```python
table_center_x=float(args_cli.task_x)
block_x=float(args_cli.task_x)
```

拆成两个参数，例如新增 `--block-x`，或者固定：

```python
table_center_x=0.55
block_x=float(args_cli.task_x)
```

注意：用户明确说过“代码里面的位置参数是我调的，不要再改”。除非用户明确要求实现“只移动物块不移动桌子”，否则不要主动改默认位置参数。

## 已解决的问题和踩坑记录

1. 项目曾经混有 LeRobot、teleop、旧环境、缓存等无关文件，已清理到当前最小调试链路。
2. 仿真和控制必须分开。一个命令启动 Isaac 仿真，一个命令写控制 JSON。不要把控制器做成另一个 Isaac 进程。
3. 物块和盘子跑到机器人脚下/世界原点的问题，是 task object spawn/reset 坐标没处理好。现在通过 `RigidObjectCfg.init_state` 和 reset pose 修复。
4. 启动时 `/tmp/s4_arm_control.json` 必须重置成 `idle`，否则上一次控制命令会在新仿真启动时立刻生效。
5. idle 模式必须保持完整 simulator-order reset target，不能从 26 维 action 每帧重映射，否则容易导致导入后双臂乱甩。
6. actuators 不能用 `.*` 控制所有导入关节，应只控制 `ALL_DRIVE_JOINTS`。
7. 固定 base 时检查过脚和地面关系。URDF base 到 foot 大约 `0.909m`，当前 `--robot-base-z 0.98` 是用户调过的值，不要随便改。
8. 旧 IK 控制会让手臂回零或卡住，所以当前 reach 不再用 Isaac Lab IK。
9. 只控制 `right_wrist_yaw_link` 会让可见手掌偏离目标。现在控制估算 TCP。
10. TCP 方向曾经设错。可视化后确认应该是 wrist 坐标系负 z 方向 `0.1m`，不是 x 方向。
11. reach 时不能强制 wrist roll/pitch/yaw 每帧归零。这样会改变 TCP offset 方向，和位置控制打架。
12. 3D 位置控制 7 自由度手臂时，如果没有关节限位和姿态正则，接近目标可能让冗余关节绕飞。现在加入：
    - URDF limit clamp
    - NaN/Inf sanitize
    - nullspace 回默认折臂姿态
    - 更小的 Cartesian step
    - catastrophic state reset：如果右臂 `NaN/Inf` 或 `abs(q) > 20 rad`，写回当前安全目标并清零速度
13. `right_arm_cmd_lag` 爆到巨大值，而 `right_arm_q_err` 仍很小时，说明不是每帧 DLS 增量过大，而是实际关节状态已经炸了。

## 手部控制现状

右手 6 个主动控制量：

```text
rh_thumb_cmc_yaw
rh_thumb_cmc_pitch
rh_index_mcp_pitch
rh_middle_mcp_pitch
rh_ring_mcp_pitch
rh_pinky_mcp_pitch
```

当前开合目标在 `s4_robot/arm_control.py`：

```python
OPEN_RIGHT_HAND = [0.5, 0.12, 0.05, 0.05, 0.05, 0.05]
CLOSE_RIGHT_HAND = [0.8, 0.48, 1.05, 1.05, 1.05, 1.05]
```

当前只是设置手指目标，还没有完整抓取状态机，也没有基于接触/物块是否抬起的判定。

## 推荐下一步

优先顺序：

1. 重启仿真，确认现在 `reach-block` 不再在接近目标时乱甩。
2. 用 `--show-tcp-frames` 确认 `RightHandTCP` 能稳定接近 `TargetBlockTCP`。
3. 如果需要只移动物块不移动桌子，先新增独立参数 `--block-x`，不要复用 `--task-x`。
4. 调整右手接近姿态。现在只做 TCP 位置控制，尚未真正控制手掌朝向。手腕姿态应作为单独目标加入，而不是直接把 wrist 关节硬写成固定值。
5. 在 `s4_robot/arm_control.py` 增加抓取状态机：
   - `approach`: 到物块上方，例如 `z_offset=0.18~0.20`
   - `lower`: 慢慢下降到接触高度，例如 `z_offset=0.04~0.08`
   - `close`: 闭合右手
   - `lift`: TCP 上移，观察物块是否被带起
6. 加日志输出：
   - 当前阶段
   - TCP 距离
   - 右臂最大关节误差
   - 是否触发失稳保护
   - 物块高度变化
7. 只有物块能被真实接触抬起后，再恢复数据录制或训练代码。

## 后续开发原则

- 不要随便改用户调好的位置默认值：`robot-base-z/task-x/plate-x/block-y-offset`。
- 控制链路出问题时，先看 `/tmp/s4_arm_control.json` 是否正确，再看仿真端是否读取到 mode。
- 手臂不动时，先跑 `bash run.sh control test-right-arm`，确认执行器路径没断。
- 手臂去错方向时，优先打开 `--show-tcp-frames` 看 TCP frame，而不是盲目改关节。
- 手臂乱甩时，先看 `right_arm_cmd_lag`、关节限位、是否有 NaN/Inf，不要先改物块位置。
- 后续文档只维护这个 `README.md`，不要再新建多个调试记录文件。
