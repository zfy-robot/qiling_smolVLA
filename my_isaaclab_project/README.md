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
    ├── 06_eval_smolvla_in_isaaclab.py # 在线 rollout：policy server -> 26D action -> IsaacLab
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

## 完整流程命令

下面是当前已经跑通的完整链路。先按这个顺序走，后续主要是在第 3 步增加更多成功数据。

### 1. 检查项目配置

```bash
cd /home/zfy/smolVLA/my_isaaclab_project
bash run.sh inspect-config
```

确认输出里至少看到：

```text
feature state:   48
active state:    26
feature action:  26
action dim code: 26
```

### 2. 启动仿真检查场景和动作

终端 A：

```bash
conda activate env_isaaclab
cd /home/zfy/smolVLA/my_isaaclab_project
bash run.sh sim
```

需要显示 TCP/目标箭头调试坐标系时：

```bash
bash run.sh sim --show-tcp-frames
```

终端 B 发送控制命令：

```bash
cd /home/zfy/smolVLA/my_isaaclab_project
bash run.sh control reset-scene
bash run.sh control grasp-block
```

如果只想测试手部开合：

```bash
bash run.sh control hand open
bash run.sh control hand close
```

### 3. 采集 HDF5 数据

先采 1 条，确认相机和抓放成功：

```bash
conda activate env_isaaclab
cd /home/zfy/smolVLA/my_isaaclab_project
bash run.sh record-hdf5 --num-episodes 1 --block blue
```

默认输出：

```text
/home/zfy/smolVLA/datasets/staging/s4_bimanual_red_blue_plate_v0/s4_right_blue_cylinder_plate_scripted.hdf5
```

确认 1 条没问题后，再逐步扩大：

```bash
bash run.sh record-hdf5 --num-episodes 10 --block blue
bash run.sh record-hdf5 --num-episodes 50 --block blue
bash run.sh record-hdf5 --num-episodes 100 --block blue
```

默认采集使用 `320x240` 图像、每 2 个仿真 step 录 1 帧，并压缩 RGB。需要高分辨率时再显式传：

```bash
bash run.sh record-hdf5 --num-episodes 1 --block blue \
  --camera-width 640 --camera-height 480 --record-every-n 1
```

### 4. 转换为 LeRobotDataset

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

如果这个输出目录已经存在，并且你要用新 HDF5 重新生成同名数据集，加 `--overwrite`：

```bash
bash run.sh convert-lerobot \
  --root-path /home/zfy/smolVLA/datasets/staging/s4_bimanual_red_blue_plate_v0/s4_right_blue_cylinder_plate_scripted.hdf5 \
  --overwrite
```

不要把目录和文件名拆成两行。下面这种写法是错的，第二行文件名会被 shell 当作一条新命令：

```bash
bash run.sh convert-lerobot \
  --root-path /home/zfy/smolVLA/datasets/staging/s4_bimanual_red_blue_plate_v0/
  s4_right_blue_cylinder_plate_scripted.hdf5
```

同样不要在路径中间加空格。下面这种写法会把文件路径拆成两个参数：

```bash
bash run.sh convert-lerobot --root-path /home/zfy/smolVLA/datasets/staging/ s4_bimanual_red_blue_plate_v0/s4_right_blue_cylinder_plate_scripted.hdf5 --overwrite
```

虽然当前脚本会尽量把这种拆开的路径自动拼回去，但推荐始终使用完整路径一行。

### 5. 训练 SmolVLA

```bash
conda activate smolvla
cd /home/zfy/smolVLA/my_isaaclab_project
bash run.sh train-smolvla
```

训练配置：

```text
configs/smolvla_s4_bimanual.yaml
```

当前默认训练步数是 `20000` step，适合 50 条左右成功 scripted demo 的第一轮检查。`steps` 是 optimizer update 次数，不会因为 episode 数量增加自动变大。

默认输出：

```text
/home/zfy/smolVLA/outputs/train/smolvla_s4_bimanual_v0
```

如果想继续在已有输出上 resume，先把配置里的：

```yaml
resume: true
```

或者直接用命令行参数：

```bash
bash run.sh train-smolvla --resume
```

如果你刚重新转换了数据集，想删除旧 checkpoint 从头训练：

```bash
bash run.sh train-smolvla --overwrite-output
```

临时覆盖训练步数、batch size 和保存频率：

```bash
bash run.sh train-smolvla --overwrite-output --steps 20000 --batch-size 4 --save-freq 2000
```

数据更多时可以继续加大，例如：

```bash
bash run.sh train-smolvla --overwrite-output --steps 50000 --batch-size 4 --save-freq 5000
```

### 6. 离线查看训练后的策略

```bash
conda activate smolvla
cd /home/zfy/smolVLA/my_isaaclab_project
bash run.sh preview-smolvla --num-frames 20
```

指定 checkpoint：

```bash
bash run.sh preview-smolvla \
  --checkpoint /home/zfy/smolVLA/outputs/train/smolvla_s4_bimanual_v0/checkpoints/003000/pretrained_model \
  --num-frames 20
```

输出 CSV：

```text
/home/zfy/smolVLA/outputs/eval/offline_policy_preview.csv
```

重点看最后一行：

```text
group_mean_mae(LA/LH/RA/RH)=...
```

当前右臂任务主要看 `RA/RH`。如果 `right_arm/right_hand` 误差还很大，不要急着接在线 rollout，先继续增加成功 demo 并重新训练。

注意：preview/visualize/eval 必须走 LeRobot checkpoint 自带的 `policy_preprocessor` 和 `policy_postprocessor`。SmolVLA 训练时对 state/action 使用 `MEAN_STD` 归一化，模型原始输出也需要 postprocessor 反归一化成真实关节角。不要手工 tokenize 后直接调用 `policy.select_action(batch)`，那会绕过归一化，输出会落在错误空间，表现为在线手臂乱抖、raw policy action 明显离谱。

2026-07-28 已修复：

- `preview-smolvla` 使用 `make_pre_post_processors(...)`。
- `visualize-smolvla` 使用 `make_pre_post_processors(...)`。
- `eval-smolvla` 的 `09_smolvla_policy_server.py` 使用官方流程：`prepare_observation_for_inference -> preprocessor -> policy.select_action -> postprocessor`。

修复后，用当前 50-demo/020000 checkpoint 做 CPU 抽样 preview，`mean_mae` 约 `0.034`，比绕过 processor 时的 `0.38+` 明显合理。

### 7. 在线策略可视化

先做离线视频可视化，不启动 IsaacLab：

```bash
conda activate smolvla
cd /home/zfy/smolVLA/my_isaaclab_project
bash run.sh visualize-smolvla --episode-index 0 --max-frames 360
```

输出：

```text
/home/zfy/smolVLA/outputs/eval/policy_visualization.mp4
```

这个视频会显示录制相机画面，并在右侧叠加：

- right arm 的 policy action vs expert action。
- right hand 的 policy action vs expert action。
- 当前帧的总体 MAE、right_arm MAE、right_hand MAE。

指定 checkpoint 或 episode：

```bash
bash run.sh visualize-smolvla \
  --checkpoint /home/zfy/smolVLA/outputs/train/smolvla_s4_bimanual_v0/checkpoints/020000/pretrained_model \
  --episode-index 10 \
  --max-frames 360
```

它不是在线闭环，只是在 recorded dataset state/image 上看策略输出是否接近 expert。物体轨迹仍然是 recorded expert 的轨迹，不是 policy 在仿真里实际执行出来的轨迹。判断策略能不能真的抓取，必须看下面 `eval-smolvla` 生成的 rollout 视频和最终物体位置。

在线 rollout 命令：

```bash
conda activate env_isaaclab
cd /home/zfy/smolVLA/my_isaaclab_project
bash run.sh eval-smolvla \
  --checkpoint /home/zfy/smolVLA/outputs/train/smolvla_s4_bimanual_v0/checkpoints/020000/pretrained_model \
  --steps 20 \
  --policy-device cpu \
  --output-video /home/zfy/smolVLA/outputs/eval/smolvla_rollout_smoke.mp4
```

上面这条是优先使用的 smoke test。它用 CPU 跑 SmolVLA policy server，只跑 20 个 IsaacLab step，用来确认：

- IsaacLab 场景能启动。
- policy server 能加载 checkpoint 并返回 ready。
- 48D state + RGB image 能发给 server。
- server 能返回 26D action。
- 仿真端能把 26D action 写回机器人并生成视频。

当前在线 eval 默认是安全模式：

- `--policy-control-groups right_arm right_hand`：只执行策略输出的右臂/右手，左臂/左手保持当前姿态。当前训练数据是右臂蓝色圆柱任务，左臂几乎是常量，直接执行 policy 的左臂预测会引入无意义乱动。
- `--action-clip dataset_minmax`：把 26D policy action 裁剪到 LeRobotDataset `meta/stats.json` 里的训练动作 min/max 范围。想看原始策略输出时可以传 `--action-clip none`，但不建议直接在线执行。
- `--task-description` 默认读取 `configs/s4_bimanual_dataset.json` 里的训练 task 文本，保证在线语言条件和转换数据集时一致。要实验新语言再显式传这个参数。

当前默认采集、转换和在线执行频率已对齐到 20Hz：

- IsaacLab 物理仿真约 120Hz。
- `record-hdf5` 默认 `--record-every-n 6`，每 6 个仿真 step 录 1 帧，约 20fps。
- `convert-lerobot` 默认写入 dataset fps=20。
- `eval-smolvla` 默认 `--policy-every-n-steps 6`，每 6 个仿真 step 请求一次 policy action，约 20Hz。

旧数据如果是 `record_every_n=2` 采集的，会以 60Hz 原始抽帧被转换成 20fps dataset，导致一个约 5-6 秒真实回合在 LeRobotDataset 里显示成约 17 秒。用这种数据训练出的 checkpoint 时间尺度不对，不适合判断在线策略质量。

为了测试当前已经采集并训练过的 50 条旧数据，`eval-smolvla` 默认 `--policy-every-n-steps 0`，表示自动推断。如果检测到当前 50-demo legacy dataset，会使用旧采集节奏 `policy_every_n_steps=2`，并使用旧 dataset task 文本：

```text
Use the left hand to put the red block into the tray and the right hand to put the blue block into the tray.
```

这不是后续推荐的新配置，只是为了公平测试已经训练好的 `020000` checkpoint。

smoke test 通过后，再跑完整 CUDA rollout：

```bash
bash run.sh eval-smolvla \
  --checkpoint /home/zfy/smolVLA/outputs/train/smolvla_s4_bimanual_v0/checkpoints/020000/pretrained_model \
  --steps 900 \
  --policy-device cuda \
  --policy-control-groups right_arm right_hand \
  --action-clip dataset_minmax \
  --policy-every-n-steps 0 \
  --video-every-n-steps 2 \
  --output-video /home/zfy/smolVLA/outputs/eval/smolvla_rollout_020000.mp4
```

默认输出：

```text
/home/zfy/smolVLA/outputs/eval/smolvla_rollout.mp4
```

这个入口会在 IsaacLab 进程中启动场景和相机，同时用 `/home/zfy/miniconda3/envs/smolvla/bin/python` 启动独立 SmolVLA policy server。IsaacLab 进程把 48D joint state 和相机 RGB 发给 server，server 返回 26D action，仿真端再通过 `control_mapping.py` 写回机器人关节目标。

在线 rollout 日志会打印三类右手信息：

- `raw_policy RH`：SmolVLA 经过 postprocessor 后输出的右手 6D action。
- `desired RH` / 视频里的 `cmd_right_hand`：经过 action clipping 和平滑后实际下发的右手 6D 命令。
- `RH_tracking actual` / 视频里的 `act_right_hand`：仿真里真实读回来的右手 6D 关节位置。

如果 `cmd` 明显变化但 `actual` 基本不动，问题在 26D action 到 URDF/actuator 的手部映射或关节驱动；如果 `raw/desired/cmd` 本身就几乎不变，问题在训练数据、策略输出或裁剪范围。不要只用视觉判断“灵巧手没动”。

如果日志停在：

```text
[SERVER] loading .../pretrained_model
Loading weights: 100%
```

说明 IsaacLab 主进程正在等 policy server 发 ready。当前脚本会继续打印：

```text
[SERVER] checkpoint loaded
[SERVER] moving policy to ...
[SERVER] policy on ...
[SERVER] ready image_key=...
[EVAL] policy server ready: ...
```

如果超过 `--policy-startup-timeout` 还没有 ready，脚本会退出并提示先用 `--policy-device cpu --steps 20` 做 smoke test。CUDA 模式下 SmolVLA server 和 IsaacSim 共用同一张 GPU，初始化可能更慢，也可能因为显存竞争卡住。

注意：`eval-smolvla` 会先把 IsaacLab 场景跑在 `env_isaaclab`，再启动 `/home/zfy/miniconda3/envs/smolvla/bin/python` 作为 policy server。policy server 现在会使用隔离环境：

- `CONDA_PREFIX=/home/zfy/miniconda3/envs/smolvla`
- `PATH=/home/zfy/miniconda3/envs/smolvla/bin:/usr/bin:/bin`
- `PYTHONPATH` unset
- `LD_LIBRARY_PATH=/home/zfy/miniconda3/envs/smolvla/lib`

如果看到 server 日志里的 `python=` 或 `conda_prefix=` 不是 `smolvla`，先修这个环境隔离问题，不要继续调控制器。

常用调参：

```bash
bash run.sh eval-smolvla \
  --checkpoint /home/zfy/smolVLA/outputs/train/smolvla_s4_bimanual_v0/checkpoints/020000/pretrained_model \
  --steps 900 \
  --policy-every-n-steps 0 \
  --video-every-n-steps 2 \
  --output-video /home/zfy/smolVLA/outputs/eval/smolvla_rollout_020000.mp4
```

如果策略动作太猛，先增大 `--policy-every-n-steps` 或减小 `--max-joint-step/--hand-max-joint-step`。如果推理太慢，先保持 `--camera-width 320 --camera-height 240`，不要上高分辨率。

如果启动后“不是去抓东西，而是手臂明显乱动”，优先看日志里的三行：

```text
[EVAL] raw_policy ...
[EVAL] clipped_policy ...
[EVAL] desired ...
```

`raw_policy` 是模型原始输出，`clipped_policy` 是按数据集范围裁剪后的输出，`desired` 是最终送入仿真的 26D 目标。若 `raw_policy` 已经和 expert 差很远，说明策略还没学好，继续加数据/训练；若 `clipped_policy` 合理但 `desired` 或实际运动不合理，再查 action 映射和控制器。

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
record_every_n=6
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

`bash run.sh eval-smolvla --checkpoint ...` 已经是第一版在线 rollout 入口：

1. IsaacLab 进程实时读取 48D state 和胸前 RGB。
2. 用独立 `smolvla` policy server 加载 SmolVLA checkpoint。
3. 构造 language tokens。
4. 输出 26D action。
5. 通过 `control_mapping.py` 写入仿真关节目标。
6. 保存 rollout 视频。

当前评估还只是第一版闭环，不代表策略质量已经可用。先用 CPU smoke test 验证链路：

```bash
conda activate env_isaaclab
cd /home/zfy/smolVLA/my_isaaclab_project
bash run.sh eval-smolvla \
  --checkpoint /home/zfy/smolVLA/outputs/train/smolvla_s4_bimanual_v0/checkpoints/020000/pretrained_model \
  --steps 20 \
  --policy-device cpu \
  --output-video /home/zfy/smolVLA/outputs/eval/smolvla_rollout_smoke.mp4
```

通过后再用 `--policy-device cuda --steps 900` 跑完整视频。若停在 policy server 加载阶段，优先看 `[SERVER] checkpoint loaded / moving policy / ready` 这些日志；超过超时时间仍无 ready，先用 CPU smoke test 排除 CUDA/显存竞争。

## 必须保留的经验

- 后续只改 `my_isaaclab_project`，不要改 `../lerobot` 或 `../qi-studio-benchhub`。
- `--offset-frame world` 的 z 是世界/base 竖直方向，不是手腕局部 z。
- 目标 frame 朝向不一致不代表 position reach 错；姿态控制是单独问题。
- 不要再用固定 `action_target_bias` 硬补关节位置误差。
- 放置后不要突然回 home，之前会把圆柱带飞；当前用 release 后世界坐标退避。
- 右手 6D 控制和实际 mimic joints 的映射必须保留。
- 当前任务先专注右臂蓝色圆柱，把数据采集和策略可视化做扎实，再扩展双臂。
