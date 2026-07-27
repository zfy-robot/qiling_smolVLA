# S4 SmolVLA IsaacLab Project

这个目录是当前自有项目。`../lerobot` 和 `../qi-studio-benchhub` 只作为参考，不在后续开发中直接修改。

当前主线已经跑通：

```text
IsaacLab scripted demo
  -> HDF5 staging dataset
  -> LeRobotDataset
  -> SmolVLA training
  -> offline policy preview
```

当前策略效果还不好，主要原因是成功数据太少。下一阶段重点不是继续改训练入口，而是稳定采集更多高质量 demo，然后再训练更久并做 IsaacLab 在线 rollout 可视化。

## 环境

使用两个 conda 环境，职责不要混：

```text
env_isaaclab
  IsaacSim / IsaacLab 仿真、场景调试、HDF5 采集

smolvla
  LeRobotDataset 转换、SmolVLA 训练、checkpoint 离线预览
```

`run.sh` 只会在仿真相关命令里切到 `env_isaaclab` 的 Python 路径。`convert-lerobot`、`train-smolvla`、`preview-smolvla` 使用当前 shell 环境，所以运行前要手动 `conda activate smolvla`。

## 目录

```text
my_isaaclab_project/
├── README.md
├── run.sh
├── configs/
│   ├── s4_bimanual_dataset.json      # 数据/场景/特征约定
│   └── smolvla_s4_bimanual.yaml      # 本地 SmolVLA 训练配置
├── data/
│   ├── hdf5_schema.py                # HDF5 字段名
│   ├── dataset_writer.py             # HDF5 writer
│   └── lerobot_conversion.py         # HDF5 -> LeRobotDataset
├── s4_pipeline/
│   ├── paths.py
│   └── config.py
├── s4_robot/
│   ├── s4_robot_cfg.py               # URDF、关节分组、默认姿态、限位
│   ├── simulation.py                 # IsaacLab 场景、机器人、物体、相机
│   ├── arm_control.py                # 右臂 TCP 控制、手部目标、JSON 控制命令
│   └── control_mapping.py            # 26D action <-> 机器人关节映射
├── tasks/
│   └── bimanual_red_blue_plate.py
└── scripts/
    ├── 00_inspect_project.py
    ├── 03_joint_debug.py
    ├── 03_record_physics_dataset.py  # 主仿真/采集循环
    ├── 04_record_bimanual_hdf5.py    # HDF5 采集 wrapper
    ├── 05_convert_hdf5_to_lerobot.py
    ├── 06_eval_smolvla_in_isaaclab.py # 在线 rollout 待实现
    ├── 07_preview_smolvla_policy.py  # 离线策略预览
    ├── control_arm.py
    ├── set_joint_command.py
    └── train_smolvla_local.sh
```

生成数据、模型和输出不进 git：

```text
/home/zfy/smolVLA/datasets/
/home/zfy/smolVLA/models/
/home/zfy/smolVLA/outputs/
```

## 当前任务

当前已经稳定的是右臂 scripted smoke test：

```text
右手抓蓝色圆柱 -> 放到盘子 -> 张手 -> 世界坐标 Y-0.20m / Z+0.15m 退避并保持
```

场景默认：

- S4 机器人固定 base，腿部不作为策略动作。
- 桌面上有红色圆柱、蓝色圆柱、盘子和三个 5cm 垫块。
- 默认布局整体向机器人右侧偏移 `task_y=-0.05`。
- 默认相机为右前上方视角，覆盖右臂抓取、移动、放置和退避过程。
- 默认不显示 TCP/目标箭头，避免影响相机数据。

策略接口：

```text
observation.state: 48D full robot joint position
observation.images.chest_front_rgb: 3 x 240 x 320 in converted dataset
action: 26D
```

26D action 顺序：

```text
0:7    left_arm
7:13   left_hand
13:20  right_arm
20:26  right_hand
```

手部仍是每只手 6 个主动控制量，mimic joints 在 `s4_robot/control_mapping.py` 里展开。不要让策略直接输出所有手指物理关节。

## 常用命令

检查配置：

```bash
cd /home/zfy/smolVLA/my_isaaclab_project
bash run.sh inspect-config
```

启动仿真窗口：

```bash
conda activate env_isaaclab
cd /home/zfy/smolVLA/my_isaaclab_project
bash run.sh sim
```

调试 TCP 坐标系时显示箭头：

```bash
bash run.sh sim --show-tcp-frames
```

另一个终端控制右臂抓放：

```bash
cd /home/zfy/smolVLA/my_isaaclab_project
bash run.sh control grasp-block
```

只开合右手，不改变手臂目标：

```bash
bash run.sh control hand open
bash run.sh control hand close
```

重置场景和任务：

```bash
bash run.sh control reset-scene
```

## 数据采集

先用 1 条 episode 确认动作和相机都正常：

```bash
conda activate env_isaaclab
cd /home/zfy/smolVLA/my_isaaclab_project
bash run.sh record-hdf5 --num-episodes 1 --block blue
```

默认输出：

```text
/home/zfy/smolVLA/datasets/staging/s4_bimanual_red_blue_plate_v0/s4_right_blue_cylinder_plate_scripted.hdf5
```

默认采集参数已经为数据体积做过压缩：

```text
camera_width=320
camera_height=240
record_every_n=2
obs/chest_front_rgb 使用 gzip 压缩
```

采集日志里会打印：

```text
[RECORD] wrote ... frames=... sim_steps=... sim_seconds=... wall_seconds=... realtime_factor=...
```

目标是一个 scripted 回合约 5 秒仿真时间。若 `lower` 或 `place_lower` 没到 tolerance，回合会变长，这是为了避免空抓或高处放置。

扩大数据量时建议逐步来：

```bash
bash run.sh record-hdf5 --num-episodes 10 --block blue
bash run.sh record-hdf5 --num-episodes 50 --block blue
```

当前 scripted 数据只是右臂蓝色圆柱任务。后续需要：

- 增加更多成功 demo。
- 加入物体位置扰动。
- 扩展左臂红色圆柱。
- 再扩展双臂同时抓放。
- 最后接 VR/真机采集。

## 转换

使用 `smolvla` 环境：

```bash
conda activate smolvla
cd /home/zfy/smolVLA/my_isaaclab_project
bash run.sh convert-lerobot \
  --root-path /home/zfy/smolVLA/datasets/staging/s4_bimanual_red_blue_plate_v0/s4_right_blue_cylinder_plate_scripted.hdf5
```

默认输出：

```text
/home/zfy/smolVLA/datasets/lerobot_data/s4_bimanual_red_blue_plate_v0
```

命令换行不要把目录和文件名拆成两个 shell 命令。错误写法会导致 `s4_right_blue_cylinder_plate_scripted.hdf5：未找到命令`。

## 训练

使用 `smolvla` 环境：

```bash
conda activate smolvla
cd /home/zfy/smolVLA/my_isaaclab_project
bash run.sh train-smolvla
```

配置文件：

```text
configs/smolvla_s4_bimanual.yaml
```

当前默认输出：

```text
/home/zfy/smolVLA/outputs/train/smolvla_s4_bimanual_v0
```

已生成过的 checkpoint：

```text
outputs/train/smolvla_s4_bimanual_v0/checkpoints/001000/pretrained_model
outputs/train/smolvla_s4_bimanual_v0/checkpoints/002000/pretrained_model
outputs/train/smolvla_s4_bimanual_v0/checkpoints/003000/pretrained_model
```

当前训练能跑通，但数据太少。3000 step / 约 5 条 scripted demo 的 checkpoint 只能证明链路通了，不能作为可部署策略。

## 离线看策略

使用 `smolvla` 环境：

```bash
conda activate smolvla
cd /home/zfy/smolVLA/my_isaaclab_project
bash run.sh preview-smolvla
```

默认会：

- 自动加载最新 checkpoint。
- 读取默认 LeRobotDataset。
- 均匀抽样 20 帧。
- 调 `SmolVLAPolicy.from_pretrained(...)` 和 `policy.select_action(...)`。
- 打印总体 MAE/RMSE/max_abs。
- 按 `left_arm/left_hand/right_arm/right_hand` 打印分组 MAE。
- 写出：

```text
/home/zfy/smolVLA/outputs/eval/offline_policy_preview.csv
```

常用：

```bash
bash run.sh preview-smolvla --num-frames 20
bash run.sh preview-smolvla --checkpoint /home/zfy/smolVLA/outputs/train/smolvla_s4_bimanual_v0/checkpoints/003000/pretrained_model
bash run.sh preview-smolvla --num-frames 1 --device cpu
```

SmolVLA 推理从随机噪声 denoise 出 action。预览脚本默认 `--seed 42`，同一命令应可复现。不要只看 `pred[:8]`，因为右臂单任务的关键动作在 `right_arm(13:20)` 和 `right_hand(20:26)`。

当前离线预览结论：

- checkpoint 能加载。
- 数据字段和 checkpoint 对齐。
- 策略能输出 26D action。
- 右臂分组误差仍偏大，说明数据/训练不足。

## 在线策略可视化

`bash run.sh eval-smolvla --checkpoint ...` 目前仍是待实现入口。下一步要把策略真正接回 IsaacLab：

1. IsaacLab 进程实时读取 48D state 和胸前 RGB。
2. 加载 SmolVLA checkpoint 或连接独立 policy server。
3. 构造 language tokens。
4. 输出 26D action。
5. 通过 `control_mapping.py` 写入仿真关节目标。
6. 保存 rollout 视频和成功率。

由于 `env_isaaclab` 和 `smolvla` 是两个环境，在线 rollout 要先决定：

- 在 `env_isaaclab` 里补齐 LeRobot/SmolVLA 依赖，直接进程内推理。
- 或保留环境隔离，做一个 `smolvla` policy server，IsaacLab 通过 socket/ZMQ 请求 action。

短期建议先做 policy server，避免污染 IsaacSim 环境。

## 必须保留的经验

- 后续只改 `my_isaaclab_project`，不要改 `../lerobot` 或 `../qi-studio-benchhub`。
- `--offset-frame world` 的 z 是世界/base 竖直方向，不是手腕局部 z。
- 目标 frame 朝向不一致不代表 position reach 错；姿态控制是单独问题。
- 不要再用固定 `action_target_bias` 硬补关节位置误差。
- 放置后不要突然回 home，之前会把圆柱带飞；当前用 release 后世界坐标退避。
- 右手 6D 控制和实际 mimic joints 的映射必须保留。
- 当前任务先专注右臂蓝色圆柱，把数据采集和策略可视化做扎实，再扩展双臂。
