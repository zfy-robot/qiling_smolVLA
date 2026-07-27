# S4 双臂 SmolVLA + IsaacLab 工作流路线图

更新时间：2026-07-27  
当前目标：用 S4 人形机器人在 IsaacLab 中完成双臂桌面任务，采集可训练数据，转换为 LeRobotDataset，并用 SmolVLA 训练/评估策略。任务第一版是：左手抓红色物块放入盘子，右手抓蓝色物块放入盘子，腿部不作为策略控制对象。

## 接手规则

每次继续工作前必须先读这个文件，再看相关代码。这个文件是后续开发的主索引，用来避免继续沿用已经废弃的入口或旧假设。

当前事实以本地文件系统为准：

- 旧的 `my_isaaclab_project/scripts/02_bimanual_plate_scene.py` 不存在，旧的 `bash run.sh bimanual --mode scripted_demo` 路线废弃。
- 旧的 `my_isaaclab_project/scripts/04_check_dataset_setup.py` 不存在，`bash run.sh check-dataset` 也不是当前入口。
- 当前 IsaacLab 调试入口是 `my_isaaclab_project/scripts/03_record_physics_dataset.py`，通过 `cd /home/zfy/smolVLA/my_isaaclab_project && bash run.sh sim ...` 启动。
- 新拉下来的 `qi-studio-benchhub/` 已有 S4 的 SmolVLA 简单闭环，入口是 `qi-studio-benchhub/train_smolvla.sh`。后续数据和训练链路优先参考它，而不是旧 MuJoCo 教程。

## 顶层仓库分工

```text
/home/zfy/smolVLA/
├── lerobot/                    # 上游 LeRobot/SmolVLA 代码，训练 API 的最终来源
├── qi-studio-benchhub/         # 已跑通 S4 数据采集、HDF5、LeRobotDataset、SmolVLA 训练/评估的参考仓库
├── my_robot/                   # 当前自有 S4 机器人 URDF/mesh
├── my_isaaclab_project/        # 当前最小 IsaacLab 调试项目，先在这里把任务物理链路做稳
├── datasets/                   # 本项目后续数据输出位置
└── SMOLVLA_ISAACLAB_ROADMAP.md # 当前路线图
```

`qi-studio-benchhub/` 的价值是生产线参考；`my_isaaclab_project/` 的价值是可控、可删改的最小实验场。不要把两个项目无脑合并。推荐先在 `my_isaaclab_project` 做稳物理和任务，再复用 BenchHub 的数据格式、转换脚本和训练参数。

## 环境职责

当前用户已有两个环境：

```text
env_isaaclab
  用途：IsaacSim/IsaacLab 仿真、场景调试、控制调试、后续录 HDF5/staging 数据
  当前入口：cd my_isaaclab_project && bash run.sh sim ...

smolvla
  用途：LeRobotDataset 检查、SmolVLA 训练、checkpoint 管理
  注意：训练环境是 Python 3.12，和 IsaacSim 环境分开维护
```

BenchHub 自己的脚本写死了 `lw_benchhub3` 或 `lw_benchhub` 环境，以及 `/home/ubuntu/...` 缓存路径。迁移到本机时不能直接照抄，需要把环境名、模型缓存、dataset root 改成 `/home/zfy/...`。

## BenchHub 已跑通工作流

入口：`/home/zfy/smolVLA/qi-studio-benchhub/train_smolvla.sh`

### 1. 采集 HDF5

BenchHub 的 README/配置显示，数据采集入口是：

```bash
cd /home/zfy/smolVLA/qi-studio-benchhub
python ./lw_benchhub/scripts/teleop/teleop_main.py --task_config s4-controller
python ./lw_benchhub/scripts/teleop/teleop_main.py --task_config s4-hand
```

典型配置：

- `configs/data_collection/teleop/s4-controller.yml`
  - `robot: S4-Controller`
  - `teleop_device: vr-controller`
  - `task: PlaceCubeInBowl`
  - `layout: robocasakitchen-4-2`
  - `dataset_file: ./datasets/s4real8.hdf5`
  - 支持 `deploy_mode: simulation | real | hybrid`
- `configs/data_collection/teleop/s4-hand.yml`
  - `robot: S4-Hand`
  - `teleop_device: vr-hand`
  - `task: PlaceCubeInBowl`
  - `dataset_file: ./datasets/dataset136.hdf5`

这说明 BenchHub 已有 VR/真机/仿真的统一采集框架，但它依赖自己的任务系统、场景系统和 S4 机器人定义。对我们当前自建 `task_sence.usd`/`my_robot` 项目来说，短期只借数据结构和流程，不直接迁移整套 Env。

### 2. 回放并补齐可训练数据

BenchHub 用 `replay_action_demo.py` 把采集动作在 IsaacLab 环境中回放，必要时打开相机，并生成带图像、状态、末端位姿等字段的新 HDF5。

典型命令：

```bash
python lw_benchhub/scripts/teleop/replay_action_demo.py \
  --dataset_file datasets/<your_dataset>.hdf5 \
  --replay_mode action \
  --record \
  --task <TaskName> \
  --layout <layout_or_usd> \
  --enable_cameras \
  --width 1920 \
  --height 1080
```

重要字段：

- 原始/回放 episode 在 `data/demo_*` 下。
- 动作字段常用 `processed_actions`。
- 状态字段常用 `states/articulation/robot/joint_position`。
- 回放时会记录 `obs/right_arm_eef_pose`、`obs/left_arm_eef_pose` 等额外字段。
- `--record` 输出文件名形如 `*_action_replay_record.hdf5`。

### 3. HDF5 转 LeRobotDataset

脚本：`qi-studio-benchhub/lw_benchhub/scripts/policy/convert_hdf5_to_lerobot_dataset.py`

典型命令：

```bash
python lw_benchhub/scripts/policy/convert_hdf5_to_lerobot_dataset.py \
  --root_path datasets/<your_data_dir_or_file.hdf5> \
  --quality-json datasets/<your_data_dir>/review.json \
  --camera_path_in_hdf5 obs/chest_center_rgbd_rgb \
  --tgt_repo_id <dataset_name> \
  --task_description "place cube in bowl" \
  --robot_type S4-Hand
```

脚本当前逻辑：

- 如果 `root_path` 是目录，会读取目录下所有 `.hdf5`。
- 在第一个有效 demo 里读：
  - `processed_actions` 作为 action，动作维度自动从 HDF5 读取。
  - `states/articulation/robot/joint_position` 作为 observation.state；如果没有则退到 `obs/real/joint_pos`。
  - `camera_path_in_hdf5` 指定的图像数组作为 `observation.images.<camera_name>`。
- 调 `LeRobotDataset.create(...)` 创建数据集。
- 每帧写入：
  - `observation.state`
  - `action`
  - `task`
  - `observation.images.*`
- 每个 demo 后调用 `dataset.save_episode()`。

质量过滤：

- 可选 `--quality-json`。
- 会跳过 `heuristic_success=false` 或 `review_status=bad` 的 demo。

### 4. SmolVLA 训练

入口：`qi-studio-benchhub/train_smolvla.sh`

默认配置：`qi-studio-benchhub/configs/policy/smolvla_s4.yaml`

核心训练命令最后是：

```bash
lerobot-train \
  --policy.type=smolvla \
  --dataset.repo_id="$DATASET" \
  --dataset.root="$DATASET_ROOT/$DATASET" \
  --dataset.video_backend=pyav \
  --output_dir="$OUTPUT_DIR" \
  --steps="$STEPS" \
  --batch_size="$BATCH_SIZE" \
  --save_freq="$SAVE_FREQ" \
  --policy.chunk_size="$CHUNK_SIZE" \
  --policy.n_action_steps="$CHUNK_SIZE" \
  --policy.n_obs_steps=1 \
  --policy.max_state_dim="$MAX_STATE_DIM" \
  --policy.max_action_dim="$MAX_ACTION_DIM" \
  --policy.resize_imgs_with_padding="[512,512]" \
  --policy.freeze_vision_encoder=true \
  --policy.train_expert_only=true \
  --policy.train_state_proj=true \
  --policy.load_vlm_weights=true \
  --policy.vlm_model_name="$VLM_PATH" \
  --policy.push_to_hub=false
```

`smolvla_s4.yaml` 的重要假设：

- 示例任务：`PlaceCubeInBowl`
- 示例机器人：`S4-Controller`
- 示例数据集：`s4confxied2_success_action_replay_record_sdg`
- 示例 `dataset_root: ./datasets/lerobot_data`
- `chunk_size: 100`
- `batch_size: 4`
- `steps: 100000`
- `max_state_dim: 50`
- `max_action_dim: 32`
- 图像 resize 到 `[512, 512]`
- 冻结视觉编码器，只训练 action expert/state projection。

注意：这个配置的注释写明数据集是 50D state + 26D action。它不是我们早期规划的 26D state + 26D action。

### 5. SmolVLA 评估

相关入口：

- `qi-studio-benchhub/eval_smolvla.sh`
- `qi-studio-benchhub/lw_benchhub/scripts/policy/eval_smolvla_policy.py`

评估脚本的重要映射：

- `STATE_ACTIVE_IDX = list(range(12, 26)) + [32, 42, 28, 29, 30, 31, 37, 47, 33, 34, 35, 36]`
- 从 50D `joint_pos` 抽取 26D active state。
- 策略输出 26D action。
- `action_mode=bypass` 时把 26D action 作为关节角控制输入传给环境。

这说明 BenchHub 的运行方式是：数据集保留完整 50D state，策略实际动作仍是上身/双手 26D。SmolVLA 用 `max_state_dim=50` 容纳完整 state。

## 当前 my_isaaclab_project 状态

当前目录：

```text
my_isaaclab_project/
├── README.md
├── run.sh
├── configs/
│   ├── s4_bimanual_dataset.json
│   └── smolvla_s4_bimanual.yaml
├── s4_pipeline/
│   ├── paths.py
│   └── config.py
├── s4_robot/
│   ├── s4_robot_cfg.py
│   ├── control_mapping.py
│   ├── simulation.py
│   └── arm_control.py
├── tasks/
│   └── bimanual_red_blue_plate.py
├── data/
│   ├── hdf5_schema.py
│   ├── dataset_writer.py
│   └── lerobot_conversion.py
├── training/
├── evaluation/
├── teleop/
└── scripts/
    ├── 00_inspect_project.py
    ├── 03_record_physics_dataset.py
    ├── 03_joint_debug.py
    ├── 04_record_bimanual_hdf5.py
    ├── 05_convert_hdf5_to_lerobot.py
    ├── 06_eval_smolvla_in_isaaclab.py
    ├── train_smolvla_local.sh
    ├── control_arm.py
    └── set_joint_command.py
```

### 当前能做的事

1. 启动 IsaacLab 场景、机器人、桌子、红蓝物块、盘子。
2. 固定 S4 base，只控制上肢/手，腿部保持默认姿态。
3. 通过 JSON 控制文件让右臂去接近红/蓝物块。
4. 通过键盘或命令行调试 26D action。
5. 用 `--show-tcp-frames` 可视化右手 TCP 和目标 TCP。
6. 使用 `control_mapping.py` 维护 26D 双臂双手控制空间。
7. 用 `s4_pipeline/config.py` 集中读取本项目配置和路径。
8. 用 `data/hdf5_schema.py` 固定后续 HDF5 字段名。
9. 用 `data/lerobot_conversion.py` 预留本项目 HDF5 -> LeRobotDataset 转换，不再改 BenchHub 仓库。

### 当前运行命令

启动仿真：

```bash
cd /home/zfy/smolVLA/my_isaaclab_project
bash run.sh sim
```

`run.sh sim` 默认已经带 `--print-layout --show-tcp-frames`。

检查本项目配置、路径和 26D action 顺序：

```bash
cd /home/zfy/smolVLA/my_isaaclab_project
bash run.sh inspect-config
```

发送右臂靠近命令：

```bash
cd /home/zfy/smolVLA/my_isaaclab_project
bash run.sh control reach-block --block blue --z-offset 0.20
```

停止控制：

```bash
bash run.sh control stop
```

运行中重置场景和任务，不重启 IsaacSim：

```bash
bash run.sh control reset-scene
bash run.sh control reload-scene  # alias
```

手部开合：

```bash
bash run.sh control hand open
bash run.sh control hand close
bash run.sh control reach-block --block blue --hand close
```

右手抓取 smoke test：

```bash
bash run.sh control grasp-block
bash run.sh control grasp-block --block red --approach-z 0.22 --grasp-z 0.08 --lift-z 0.24
```

右手带姿态锁定的抓取调试：

```bash
bash run.sh control grasp-block --block blue --grasp-pose current
bash run.sh control grasp-block --block blue --grasp-pose current --grasp-roll 0.20
bash run.sh control grasp-block --block blue --grasp-pose current --grasp-pitch -0.20
bash run.sh control grasp-block --block blue --grasp-pose current --grasp-yaw 0.20
```

`grasp-block` 参数语义：

- `--block red|blue`：选择右手要抓的物块。当前只是右手 smoke test，不会自动切左手。
- `--approach-z`：approach 阶段 TCP 相对物块中心的 Z 偏移，默认 `0.20m`，用于先到物块上方。
- `--grasp-z`：lower/close 阶段 TCP 相对物块中心的 Z 偏移，默认 `0.08m`，用于下降到接近抓取高度。
- `--lift-z`：lift 阶段 TCP 相对物块中心的 Z 偏移，默认 `0.22m`，闭合手后抬起。
- `--x-offset/--y-offset`：所有阶段共用的水平偏移，用于微调手指相对物块的位置。
- `--tolerance`：阶段切换的 TCP 距离阈值，默认 `0.06m`。如果 reach 误差仍约 `5cm`，不要把这个值调太小，否则状态机会卡在 approach/lower。
- `--approach-steps`：approach 阶段最大步数；到达 tolerance 或超过最大步数都会进入 lower。
- `--lower-steps`：lower 阶段等待到位的告警步数，不再允许靠超时进入 close。lower 必须达到 `--tolerance` 才能闭合手，避免 reset 后第一次命令在物块上方空抓。
- `--close-steps`：close 阶段保持闭合命令的步数，之后进入 lift。
- `--grasp-pose none|current`：`none` 只控位置；`current` 在命令开始时锁定当前 TCP 姿态，并用 pose IK 保持该姿态。
- `--grasp-roll/--grasp-pitch/--grasp-yaw`：在锁定的当前 TCP 姿态上叠加局部 RPY 微调，单位 rad。建议一次只调一个轴，每次 `0.1~0.2rad`。

右臂直接关节测试：

```bash
bash run.sh control test-right-arm
```

右臂控制链路诊断：

```bash
bash run.sh control diagnose-right-arm --eps 0.01 --hold-steps 120 --drive-steps 40
```

该命令会在运行中的仿真里打印三类 `[DIAG]`：

- `hold_drift`：不发 IK，只保持当前关节目标，看 TCP 是否仍明显向下漂移。若这里 z 明显为负，优先查重力、PD 增益、effort limit、URDF 导入质量，而不是继续调 IK。
- `fd ... row... cos=...`：直接写关节状态做有限差分，对比 PhysX Jacobian 的 body row/关节列。如果 cos 大量为负或接近 0，说明 Jacobian row、TCP offset 或关节列映射错。
- `drive+ ... q_delta ... tcp_delta`：逐个关节发 `q + eps` 的位置目标，看实际关节是否正向跟随。如果 `q_delta` 反向或几乎不动，说明 actuator/drive/effort/重力保持层有问题；如果 `q_delta` 正常但 TCP 方向和有限差分相反，再查 TCP frame 和 body pose 更新链路。

后续流程入口已经预留：

```bash
bash run.sh record-hdf5
bash run.sh convert-lerobot --root-path <hdf5 file or dir>
bash run.sh train-smolvla
bash run.sh eval-smolvla --checkpoint <checkpoint>
```

当前状态：`record-hdf5` 和 `eval-smolvla` 是 fail-fast scaffold，会明确提示未实现；`convert-lerobot` 已有本项目内转换逻辑，但需要先有符合 `data/hdf5_schema.py` 的 HDF5；`train-smolvla` 会先检查 LeRobotDataset 是否存在。

### 当前场景实现

`s4_robot/simulation.py` 现在使用：

- 默认背景：`/home/zfy/isaacsim_assets/Assets/Isaac/5.1/Isaac/Environments/Simple_Warehouse/warehouse.usd`
- 默认桌子：`/home/zfy/isaacsim_assets/Assets/Isaac/5.1/Isaac/Props/PackingTable/packing_table.usd`
- 机器人：从 `my_robot/urdf/s4_40dof_merged.urdf` 导入。
- 任务物体：
  - `/World/RecordTask/RedBlock`
  - `/World/RecordTask/BlueBlock`
  - `/World/RecordTask/Plate`
- 相机：
  - `/World/DebugFrontCamera`
  - 480x640 RGB
  - 胸前/前方视角，朝桌面看。

重要问题：之前用户创建的 `/home/zfy/smolVLA/task_sence.usd` 当前没有被 `simulation.py` 默认使用。当前默认又回到了官方 warehouse + packing table。如果后续要使用用户自建仓库/桌子场景，需要在 `SceneBuildCfg` 或配置里显式把 `scene_usd` 改为 `task_sence.usd`，并确认是否还需要额外 spawn 桌子。

### 当前控制实现

`s4_robot/control_mapping.py` 定义 26D policy/action 顺序：

```text
[0:7]   left_arm_7
[7:13]  left_hand_6
[13:20] right_arm_7
[20:26] right_hand_6
```

手部 6 控制输入保留为策略输出，不让 SmolVLA 直接输出物理全手关节。

已根据用户提供的 O6 hand C++ 底层控制逻辑记录 mimic：

- DIP mimic multiplier：`0.89`
- 左手 `lh_thumb_ip = lh_thumb_cmc_pitch * 2.29`
- 右手 `rh_thumb_ip = rh_thumb_cmc_pitch * 1.86`
- 四指 DIP 由 MCP pitch 乘 `0.89`

注意：BenchHub 的 S4-Hand 评估映射里把 12 个手 active state 取自 50D 的固定 index，而我们这里是按关节名映射。后续不要硬编码 index，除非已经打印并确认当前 IsaacLab 导入后的 `robot.joint_names` 顺序。

### 当前右臂控制

`s4_robot/arm_control.py` 当前只实现右臂：

- `RightArmReachController`
- 用右腕位置 Jacobian 做小步 damped least squares。
- 当前 TCP 估计为 `right_wrist_yaw_link` 沿 wrist 负 z 偏移 `0.10m`。
- 只控制 TCP 位置，不稳定控制手掌朝向。
- 有 joint limit clamp、低通平滑和失稳重置保护。
- `reach-block --z-offset` 的语义是世界坐标偏移：`target_tcp = block_pos + [x_offset, y_offset, z_offset]`，不是沿手掌末端局部 z 轴移动。因此如果当前手不在物块正上方，执行命令后先出现 x/y 方向移动是正常现象。
- 2026-07-27 根据用户复测，新增 `--offset-frame {world,wrist}`：
  - 默认 `--offset-frame world`：`--z-offset` 是世界坐标 Z，目标在物块世界 Z 上方。
  - `--offset-frame wrist`：`--x/y/z-offset` 先按当前右腕/手坐标系解释，再旋转到世界系；这时 `--z-offset` 才是“沿手末端局部 z 方向”的偏移。
  - 状态日志会打印 `offset_frame` 和 `offset_w`，其中 `offset_w` 是真正加到 `block_pos` 上的世界坐标偏移。
- 2026-07-27 根据实测“右臂先偏 x/y、随后乱甩/像被甩飞”做了保守化：
  - `--target-alpha` 默认从 `0.08` 降到 `0.04`
  - `--max-joint-step` 默认从 `0.012` 降到 `0.006`
  - `RightArmReachController` 内部 Cartesian 单步默认 `0.004m`
  - DLS damping 默认 `0.16`
  - 每次 reach 解的关节增量默认限制 `0.010rad`
  - 增加 `--reach-max-error`，TCP 到目标距离过大时停止推进并打印 warning
  - 增加 `--unstable-arm-threshold` 和 `--unstable-arm-velocity-threshold`，关节角/速度异常时重置右臂
  - 状态日志现在打印 `block`、`target_tcp`、`tcp`、`tcp_err`，用于判断坐标方向和目标是否合理
- 2026-07-27 用户日志显示 `tcp_err.x/z` 为正，但下一帧 TCP 的 x/z 反而减小。判断为控制链路里 Jacobian 速度坐标系和误差坐标系不一致：PhysX translational Jacobian 按 world frame 使用，但旧代码把目标误差转到了 base frame。已改为 world-frame TCP/wrist 误差直接乘 PhysX Jacobian。
- 2026-07-27 用户继续复测发现：无论 `--offset-frame world` 还是 `--offset-frame wrist`，无论给 x/y/z 哪个方向的 offset，手都会先向下运动并碰桌，随后右臂抖动/乱甩。这说明问题已经不是单纯的 offset 坐标系语义，而更可能是 Jacobian body row、Jacobian 符号、关节列映射或 PhysX body index 约定不匹配。
- 已给 `RightArmReachController` 增加 Jacobian 诊断和方向保护：
  - 启动参数新增 `--reach-jacobian-body-shift`，用于显式指定从 `right_wrist_yaw_link` 到 PhysX Jacobian body row 的偏移；默认继续使用 IsaacLab fixed-base 约定。
  - 启动参数新增 `--reach-jacobian-sign`，可用 `-1` 翻转 translational Jacobian 符号。
  - 启动参数新增 `--reach-adaptive-direction-sign/--no-reach-adaptive-direction-sign`，当前默认关闭；如果实测 TCP 连续背离目标，可临时开启做诊断。
  - 启动参数新增 `--reach-min-tcp-below-block`，默认 `0.04m`；在 `reach-block` 调试模式下，如果 TCP 已低于物块中心太多，会 hold 右臂，避免继续把手压进桌子。
  - 状态日志新增 `step_w`、`pred_w`、`jac_row`、`jac_sign`、`dir_sign`、`progress`。
  - `step_w` 是本轮希望 TCP 在世界系走的小步。
  - `pred_w` 是当前 Jacobian 预测这组关节增量会造成的世界系 TCP 位移。
  - `progress` 是上一轮真实 TCP 位移在上一轮目标误差方向上的投影；负数表示真实运动背离目标。
  - 判断方法：如果 `step_w.z > 0`、`pred_w.z > 0`，但下一轮 `tcp.z` 仍持续下降，优先怀疑 PhysX Jacobian body row 或实际 TCP/body 不是同一个点；如果 `pred_w` 本身就和 `step_w` 反向，优先试 `--reach-jacobian-sign -1`。
- 2026-07-27 用户新日志显示：`step_w` 和 `pred_w` 都预测 TCP 应该沿 x/z 正方向接近目标，但实际 `tcp.x/tcp.z` 仍整体下降；`dir_sign` 自动翻转也没有解决。这进一步排除了“单纯世界/手腕 offset 坐标系错”和“单纯 Jacobian 整体符号错”。
- 已修正右臂 reach 的核心 Jacobian：旧代码用 `right_wrist_yaw_link` body 原点的 translational Jacobian 控制估算 TCP，但实际 TCP 是 wrist 原点沿 wrist 局部 `-0.10m` 偏移后的点。手腕姿态变化会通过 `omega x r` 显著移动 TCP，导致“wrist 原点预测向上，TCP 实际向下”。现在改为 TCP 点 Jacobian：

```text
J_tcp_linear = J_wrist_linear + cross(J_wrist_angular, tcp_offset_world)
```

- 同时把 IK 位置误差改为直接使用 `target_tcp - current_tcp`，不再先换算成 wrist origin 误差。
- `--reach-adaptive-direction-sign` 默认改为关闭，避免在根因未解决时来回翻转 `dir_sign` 引入额外抖动；保留该参数只作为后续诊断开关。
- 2026-07-27 用户继续复测后，日志出现更关键的执行链路异常：`right_arm_cmd_lag=1.089`。这表示 IK 算出的 `reach_q_target` 和实际平滑后送入 `set_joint_position_target` 的 `commanded_action` 差了 1 rad 以上。也就是说即使 Jacobian 预测方向正确，执行目标也会被旧 action/默认姿态拉偏。
- 已修正执行目标同步：
  - 启动和 `reset-scene` 后，26D `action/commanded_action/hold_action` 不再直接用手写 `bimanual_default_action()`，而是从 `reset_scene()` 返回的 robot-order full target 中按 `robot.joint_names` 提取。
  - 收到 `reach-block` 命令时，先从当前仿真 `robot.data.joint_pos` 提取 26D 控制态，同步 `action/commanded_action/hold_action`，再开始 IK。
  - reach 模式下 `desired_action` 从当前 `commanded_action` 复制，而不是从 `/tmp/s4_joint_command.json` 的旧 action 复制，避免外部默认控制文件持续把非目标关节或右臂目标拉回旧姿态。
  - 修复后 `right_arm_cmd_lag` 应该保持在 `max_joint_step` 同量级，正常约 `0.01rad` 以内；如果仍出现 `>0.1rad`，优先查平滑/状态同步，而不是继续调 Jacobian。
- 2026-07-27 用户复测后 `right_arm_cmd_lag` 已降到 `0.011~0.015rad`，说明 IK 输出到执行目标的同步问题已经排除。但 `pred_w` 仍预测正向、真实 TCP 仍反向，`progress` 持续为负，说明当前 PhysX Jacobian 对本机导入机器人和位置目标执行之间存在整体方向不一致或 body row 对应问题。
- 处理策略更新：
  - 曾短暂把 `--reach-jacobian-sign` 默认从 `1.0` 改为 `-1.0` 做诊断，但用户后续要求改用官方 IK 后，默认已恢复为 `1.0`。
  - 状态日志新增 `actual_d=(dx,dy,dz)`，表示上一报告周期真实 TCP 世界坐标位移，用于直接和 `pred_w` 对比。
  - 创建 reach controller 时打印 `right_wrist_body`、`jac_row`、`right_joint_ids`、`right_joint_names`。如果 `-1` 后仍不收敛，下一步优先查 `jac_row` 是否应为 `right_wrist_body_id` 而不是 fixed-base 的 `body_id - 1`。
- 2026-07-27 用户明确要求不要继续维护手写 IK，改用现成包。已把 `RightArmReachController` 内部求解从自写 DLS 伪逆切换为 IsaacLab 官方 `DifferentialIKController`：
  - `DifferentialIKControllerCfg(command_type="position", use_relative_mode=False, ik_method="dls")`
  - 当前 TCP pose 和目标 TCP pose 按 IsaacLab 官方测试/`TaskSpaceAction` 做法转到 robot root/base frame 后传入 controller。
  - Jacobian 使用 PhysX geometric Jacobian，并按官方做法从 world frame 转 root/base frame。
  - TCP offset 采用官方 `TaskSpaceAction._compute_frame_jacobian()` 同类公式处理：`J_tcp_linear += -skew(tcp_offset) @ J_angular`。
  - 由于已改为官方 root-frame IK，`--reach-jacobian-sign` 默认恢复为 `1.0`，只保留 `-1` 作为诊断开关。
  - 启动日志改为 `IsaacLab DifferentialIKController, root-frame TCP target, PhysX geometric Jacobian`。
- 2026-07-27 用户继续反馈现象仍是“无论 world/wrist、无论 x/y/z 偏移，手都往下走并撞桌”。当前判断：这已经不是 `reach-block --z-offset` 的坐标系解释问题。`--offset-frame world` 时，`--z-offset` 明确表示世界坐标 Z；`--offset-frame wrist` 时才表示手腕局部坐标。现在需要验证的是控制执行链路：
  - 是否机器人在 hold 目标时就因为重力/PD/effort limit 往下塌。
  - 是否 URDF 导入后的 PhysX Jacobian body row 和 `right_wrist_yaw_link` 不一致。
  - 是否 TCP offset/Jacobian offset 和实际可视化 TCP 不是同一个点。
  - 是否 `set_joint_position_target` 的正向目标没有被 articulation drive 正向跟随。
- 已新增运行中诊断命令 `bash run.sh control diagnose-right-arm --eps 0.01 --hold-steps 120 --drive-steps 40`。该命令会打印右臂关节当前值/目标值、stiffness/damping、effort limit、hold 漂移、有限差分 Jacobian 对比，以及逐关节正向位置目标响应。后续不要再只看 `reach-block` 的长日志猜原因，先看 `[DIAG]`。
- 2026-07-27 用户提供 `diagnose-right-arm` 日志后的结论：
  - `hold_drift delta=(0,0,0)`，说明当前右臂在目标姿态下不会被重力持续拉下去，不能再把首要原因归到重力补偿。
  - `row25` 和直接写关节状态的有限差分 `cos≈0.985~1.000`，说明 fixed-base 下 `right_wrist_yaw_link` 对应的 Jacobian row `25` 是正确的，URDF 关节轴/PhysX Jacobian row 不是主要问题。
  - `row26` 全 0，说明不能用 body id 本身，必须用 fixed-base 约定的 `body_id - 1`。
  - 右臂 wrist effort limit 是 `18`，肩肘是 `66`，目前 hold 稳定，但真实抓取/碰撞时 wrist 仍可能力矩不足，后续接触阶段再评估。
  - 原 `drive+` 诊断混入了状态/目标重新同步漂移，已进一步修成 settle 后隔离测试：先以当前 `q_start` 作为全关节目标短暂 settle，再只给单个关节 `q_start+eps`。
  - `drive+` 现在额外打印 `all_right_dq=(...)`，用于确认是否只有被测关节在动，还是其它右臂关节也被隐式拉动。
  - reach 状态日志新增 `dq=(...)` 和 `cmd_delta=(...)`，顺序均为 `right_shoulder_pitch,right_shoulder_roll,right_shoulder_yaw,right_elbow,right_wrist_roll,right_wrist_pitch,right_wrist_yaw`。`dq` 是 IK 本轮期望增量，`cmd_delta` 是平滑后真正送给右臂 position target 的增量。
- 2026-07-27 用户再次提供 reset 后诊断日志，根因基本确认：
  - reset 后强制写入 nominal 姿态时，`q` 几乎等于 `q_target`。
  - 但在同一个 nominal position target 下 `hold_drift` 120 步后 TCP 下沉约 `2.3cm`，右臂肩/肘出现 `0.02~0.03rad` 级静态误差。
  - `drive+` 中所有测试关节都出现共同的 `all_right_dq≈(+0.026,+0.018,-0.005,+0.024,...)`，说明这不是单关节运动学，而是机器人从强制写入姿态向重力/PD 稳态 settle。
  - 这表示当前 implicit position drive 没有显式重力补偿。为了保持实际关节角 `q_actual`，drive target 不能简单设为 `q_actual`，而需要保留 `q_target - q_actual` 这个静态保持偏置。
- 已修正 reach 执行层：
  - reset/start 后仍使用 nominal target 做 settle，不再把 settled actual joint state 直接当成 drive target。
  - 新增 `action_target_bias = actuator_target_action - actual_action`。
  - IK 继续在实际关节角上计算 `actual_desired = actual_q + dq`。
  - 写入 PhysX position drive 时，右臂目标改为 `actual_desired + action_target_bias`，用于保留静态重力保持偏置。
  - reach 日志新增 `drive_delta=(...)`，表示真正送入 position drive 的右臂目标相对当前关节角的增量。
  - `drive+` 诊断改为围绕当前 `full_command_target` 加 `eps`，其它关节继续保持有重力偏置的 target。
- 2026-07-27 重要复盘，禁止后续重复浪费时间：
  - “手总往下走”的根因不是 `--z-offset` 坐标系、不是手写/官方 IK、不是 PhysX Jacobian row，也不是 URDF 关节轴方向。
  - 真正根因是 IsaacLab implicit position drive 没有显式重力补偿，reset 时直接 `write_joint_state_to_sim()` 把机器人放到 nominal 姿态后，机器人会在同一个 position target 下向重力/PD 稳态 settle。这个 settle 漂移大约造成 TCP 下沉 `2~3cm`，并在 reach 开始时被误判成“IK 往下走”。
  - 排查这类问题的正确顺序必须是：`hold_drift` 先判定执行层是否自己漂移；`fd` 对比 Jacobian row；`drive+ all_right_dq` 判定 position drive 是否按目标执行；最后才看 IK 的 `dq/pred_w/actual_d`。以后不要先猜坐标系或反复改 Jacobian 符号。
  - 对无显式重力补偿的 position drive，控制器内部的“期望实际关节角”和“写给 PhysX 的 actuator target”不是同一个量。后者必须包含静态保持偏置：`drive_target = desired_actual_q + (hold_target - settled_actual_q)`。
  - 当前已用 `action_target_bias` 记录这个偏置。后续左臂、双臂、VR retarget、数据回放都必须保留这个设计，否则同样会在开始运动时出现假下沉/假方向错误。
- 2026-07-27 当前新问题：手不再下沉，但手末端坐标系没有和物块上方的目标坐标系重合。
  - 当前 `RightArmReachController` 使用 `DifferentialIKControllerCfg(command_type="position")`，只控制 TCP 位置，不控制 TCP 姿态。因此两个坐标系的朝向不重合是当前实现的预期结果。
  - `/World/Visuals/TargetBlockTCP` 当前只是“目标 TCP 位置 marker”，其 orientation 被固定为 identity quaternion，并不是期望抓取姿态。它的坐标轴朝向不能拿来和手末端坐标轴比较。
  - 判断 position reach 是否成功，应看日志里的 `tcp_err`、`right_tcp_dist`、`actual_d` 是否收敛到接近 0；不要用两个 frame 朝向是否一致判断。
  - 若需要“手掌坐标系和目标抓取坐标系重合”，下一步必须从 position IK 升级为 pose IK：定义目标抓取姿态 `target_tcp_quat`，把 `command_type` 改为 `pose`，并传入 6D pose error 的 Jacobian。还需要明确手掌哪个轴作为 approach axis、哪个轴朝向桌面/物块。
  - 真实抓取状态机不能只靠 position-only reach。至少需要 `approach pose -> lower pose -> close hand -> lift -> place`，并且 approach/lower 阶段要约束手掌姿态。
- 2026-07-27 用户运行 `bash run.sh control reach-block --block blue --z-offset 0.10 --offset-frame world` 后仍看到慢速下移：
  - 这个命令本身可能要求 TCP 向下运动。当前物块高度约 `block_z=1.019`，`--z-offset 0.10` 的目标 TCP 高度是 `1.119`；reset/settle 后右手 TCP 常在 `1.16~1.19` 左右，因此 `target_tcp.z - tcp.z` 可能是负数。
  - 结论：不能只看“手往下走”判断错误，必须先比较 `target_tcp.z` 和当前 `tcp.z`。若目标低于当前 TCP，下移是符合命令的。
  - 已在收到 `reach-block` 命令时打印 preview：`block`、`target_tcp`、当前 `tcp`、`target_minus_tcp`。若 `target_minus_tcp.z < 0` 会警告该命令会先向下运动。
  - `control_arm.py` 的 `reach-block` 默认 `--z-offset` 已从 `0.14` 改为 `0.20`，减少默认目标低于当前 TCP 的概率。调“物块上方 approach”优先用 `--z-offset 0.20` 或 `0.25`；调“下降抓取 lower”才用 `0.10` 或更小。
- 2026-07-27 用户用 `--z-offset 0.20` 复测后，preview 显示目标确实在当前 TCP 上方：`target_minus_tcp=(+0.202,+0.103,+0.051)`，但 TCP 只少量向 x/y 接近后 z 又下降，`right_tcp_dist` 卡在约 `0.20m`。
  - 关键日志：`cmd_delta` 是小步 IK 期望实际关节增量，但 `drive_delta` 叠加了很大的静态偏置，例如 shoulder/roll/elbow 方向被固定 bias 主导。
  - 结论：上一版 `action_target_bias` 虽然解释了 reset settle，但不是正确控制方案。固定偏置会在小步 IK 阶段抵消甚至反向实际 drive target，导致 IK 预测和 PhysX 执行脱节。
  - 修正：仿真第一版不再用固定 `action_target_bias` 叠加 reach 命令；改为增强 implicit position drive 本身。
  - 新默认 drive 参数：`--joint-stiffness 600`、`--joint-damping 80`、`--joint-effort-limit 300`。`s4_robot/simulation.py` 已把 `joint_effort_limit` 写入 `ImplicitActuatorCfg(effort_limit_sim=...)`，覆盖 URDF 中肩肘 `66`、腕部 `18` 的仿真力矩限制。
  - 当前 `control_action_bias_from_target()` 返回零，reach 写给 PhysX 的右臂目标直接是 `commanded_action`。日志中 `drive_delta` 应和 `cmd_delta` 一致；若不一致，说明还有其它执行层目标混入。
  - 后续如果需要真实重力补偿，应使用动力学计算/力矩前馈或 Operational Space Controller，而不是对 position target 加固定静态偏置。
- 2026-07-27 用户要求安装 Pinocchio 并做重力补偿以提高位置控制精度：
  - 检查发现 `env_isaaclab` 里已经有 `pin==2.7.0`，但默认 `import pinocchio` 报 `No module named 'pinocchio.pinocchio_pywrap_default'`，原因是 `cmeel.prefix` 下的 Python 模块/动态库路径没有进入运行环境。
  - 已在 `my_isaaclab_project/run.sh` 中加入：
    - `PYTHONPATH=/home/zfy/miniconda3/envs/env_isaaclab/lib/python3.11/site-packages/cmeel.prefix/lib/python3.11/site-packages:$PYTHONPATH`
    - `LD_LIBRARY_PATH=/home/zfy/miniconda3/envs/env_isaaclab/lib/python3.11/site-packages/cmeel.prefix/lib:$LD_LIBRARY_PATH`
  - 已验证在 `env_isaaclab` 中 `import pinocchio as pin` 成功，版本 `2.7.0`；`import hppfcl` 也成功。因此当前不需要重新下载安装，只需要通过 `run.sh` 启动以带上路径。
  - 当前控制链路优先使用 IsaacLab/PhysX 自带的 `robot.root_physx_view.get_gravity_compensation_forces()` 做重力补偿前馈，而不是手动 Pinocchio 计算。原因：它和 IsaacSim 导入后的 articulation/joint order 完全一致，少了 URDF mimic/merge-fixed-joints/关节顺序映射风险；IsaacLab 自带 `task_space_actions.py` 和 `pink_task_space_actions.py` 也使用这个接口。
  - 新增运行参数：
    - `--gravity-compensation/--no-gravity-compensation`，默认开启。
    - `--gravity-comp-scale`，默认 `1.0`。
  - 每个 simulation step 会调用 `get_gravity_compensation_forces()`，取 `ALL_DRIVE_JOINTS` 对应的关节力矩，通过 `robot.set_joint_effort_target()` 写入 feed-forward effort，再 `write_data_to_sim()`。
  - 日志新增 `gravity_comp=max:<...>/mean:<...>`，用于确认重力补偿前馈确实在输出。
  - 后续如果要用 Pinocchio 独立算重力项，必须先建立 Pinocchio joint order 与 IsaacLab `robot.joint_names` 的映射，并验证 Pinocchio `computeGeneralizedGravity()` 和 PhysX `get_gravity_compensation_forces()` 数值/符号一致，否则不要替换当前 PhysX 前馈。
- 2026-07-27 重力补偿后用户反馈位置精度改善，但速度偏慢；已把 reach 默认速度从保守调试档提高：
  - `--target-alpha`: `0.04 -> 0.12`
  - `--max-joint-step`: `0.006 -> 0.018`
  - `--reach-max-cart-step`: `0.004 -> 0.012`
  - `--reach-max-joint-delta`: `0.010 -> 0.030`
  - 这四个参数必须一起看：`reach-max-cart-step/reach-max-joint-delta` 限制 IK 本轮期望，`target-alpha/max-joint-step` 限制真正写入 position target 的平滑速度。只调其中一个经常不会变快。
  - 如果出现抖动或越过目标，先退回：`--target-alpha 0.08 --max-joint-step 0.012 --reach-max-cart-step 0.008 --reach-max-joint-delta 0.02`。
- 2026-07-27 用户最新日志显示，开启 PhysX gravity compensation 且提高默认速度后，右手能从约 `(0.356,-0.308,1.192)` 移动到约 `(0.505,-0.202,1.249)`，相对目标 `(0.550,-0.200,1.219)` 最终误差约 `5cm`：
  - `cmd_delta` 和 `drive_delta` 已一致，说明固定偏置残留已清除，IK 输出到 position target 的执行链路现在是连贯的。
  - 剩余误差主要表现为 `x` 方向还差约 `4.5cm`、`z` 方向高约 `3cm`。这不再像之前的“执行层往下塌/坐标系错”，更像 position-only IK 在当前姿态、关节限位、手掌姿态未约束下的局部收敛问题。
  - 这可以作为继续调抓取 smoke test 的基础，但还不能作为正式专家控制器。正式抓取仍需要 pose IK 或明确的 grasp frame。
- 2026-07-27 修复 `bash run.sh control hand open/close` 让右臂回原始位置的问题：
  - 根因：旧 `hand` 命令把 `arm_mode` 设为 `idle`。主循环在 `idle` 时会用 `default_target.copy()` 重建全身 target，因此右臂必然回 reset/default 姿态。
  - 修复：`hand` 命令现在切到 `hold` 模式，先从当前仿真关节状态提取 26D action，同步 `action/commanded_action/hold_action`，然后只替换右手 6D target。这样可以只打开/闭合右手，保持当前右臂姿态。
- 2026-07-27 新增 `grasp-block` 右手抓取 smoke test 命令：
  - 命令入口：`bash run.sh control grasp-block --block blue`
  - 状态机：`approach -> lower -> close -> lift`
  - 默认参数：`approach_z=0.20`、`grasp_z=0.08`、`lift_z=0.22`、`tolerance=0.06`、`close_steps=80`
  - 每个阶段仍复用当前 right-arm position-only `DifferentialIKController`，并在 `close/lift` 阶段把右手设为 close。
  - 这是接触/手部闭合/抬起链路的 smoke test，不保证能稳定抓起物块。如果 lower 阶段手掌姿态不对或手指从侧面错过物块，下一步必须实现 pose IK，而不是继续只调 z-offset。
- 2026-07-27 根据当前右手稳定 reach 位置，把默认任务物体整体向机器人身体方向移动：
  - `scripts/03_record_physics_dataset.py`: `--task-x 0.55 -> 0.50`，`--plate-x 0.55 -> 0.50`
  - `s4_robot/simulation.py`: `TaskLayout.block_x 0.55 -> 0.50`，`TaskLayout.plate_x 0.96 -> 0.50`
  - 这样 reset 后红/蓝物块和盘子默认在 `x=0.50`，更接近当前右手能稳定到达的 `x≈0.505`。如果当前 IsaacSim 进程已经启动，需要重启仿真才会使用新的 argparse 默认值；运行中 `reset-scene` 只能按当前进程启动时的 cfg 重置。
- 2026-07-27 用户反馈方块抓不稳，已把红/蓝动态任务物体从 `0.05m` 立方体改成更容易包络抓取的竖直圆柱：
  - 圆柱半径 `0.035m`，高度 `0.06m`，质量仍为 `0.05kg`。
  - prim 名称暂时保持 `/World/RecordTask/RedBlock`、`/World/RecordTask/BlueBlock`，避免破坏现有 `reach-block/grasp-block --block red|blue` 控制接口。
  - 圆柱中心高度改为 `table_top_z + 0.03`，确保圆柱底面仍贴桌面。
  - 几何类型变化需要重启 IsaacSim 重新 spawn；运行中的 `reset-scene` 只能重置 pose，不能把已创建的方块变成圆柱。
- 2026-07-27 用户反馈“手指一夹圆柱，圆柱就飞了”，已做第一轮接触稳定化：
  - 圆柱高度 `0.06m -> 0.09m`，半径保持 `0.035m`。
  - 圆柱质量 `0.05kg -> 0.12kg`，减少被手指小穿透顶飞的速度响应。
  - 圆柱/桌面接触材质提高到 `static_friction=2.0`、`dynamic_friction=1.6`、`restitution=0.0`。
  - 动态圆柱刚体改为 `solver_position_iteration_count=24`、`solver_velocity_iteration_count=4`、`max_depenetration_velocity=0.25`、`linear_damping=0.25`、`angular_damping=0.35`。
  - contact 参数改为 `contact_offset=0.002`、`rest_offset=0.0005`，减少过早/过深接触解算带来的弹射。
  - 右手 close 默认目标从四指 `1.05rad` 降到 `0.85rad`，thumb pitch 从 `0.48` 降到 `0.42`，避免一开始就强行深夹圆柱。
  - 修复手部命令执行层：旧代码在 `smooth_command()` 后又用 `hand_target` 直接覆盖右手目标，导致手指开合是一步跳变。现在右手目标也走同一套平滑，所以 open/close 会更慢、更可控。
  - 圆柱被夹飞的首要原因通常不是“摩擦不够”，而是 position-controlled 手指闭合太快/太深造成穿透，PhysX 解穿透时产生很大的物体速度。后续如果仍飞，优先继续减小 close 目标、降低手部 `max_joint_step` 或实现 contact-stop，而不是只继续增大摩擦。
- 2026-07-27 用户指出抓取过程不应使用物块的实时相对位置，否则物块一被碰动，后续 lower/lift 目标也会跟着变。已修正：
  - `grasp-block` 收到命令时锁定圆柱当时的位置，作为固定 world/base frame anchor。
  - `approach/lower/close/lift` 阶段都用这个 anchor 加 offset 计算目标，不再每步用圆柱当前 pose 追踪目标。
  - 日志会打印 `[ARM] grasp anchor locked in fixed world/base frame: (...)`。
  - `reach-block` 仍然使用物块当前 pose，适合作为单步调试；`grasp-block` 使用锁定 anchor，适合流程测试。
- 2026-07-27 第二轮防弹飞修改：
  - 圆柱高度 `0.09m -> 0.12m`，质量 `0.12kg -> 0.18kg`。
  - 新增 `--hand-max-joint-step`，默认 `0.004rad/step`，单独限制手指目标速度；手臂仍使用 `--max-joint-step`。
  - `grasp-block --close-steps` 默认 `80 -> 160`，给更慢的手指闭合留出时间。
  - 若仍把圆柱打飞，下一步应实现 contact-stop：检测手指接触圆柱后停止继续闭合，而不是继续靠 position target 往里挤。
- 2026-07-27 新增最小 pose IK 抓取姿态调试：
  - `RightArmReachController` 内部保留 position IK controller，同时新增 `DifferentialIKControllerCfg(command_type="pose", use_relative_mode=False, ik_method="dls")` 的 pose IK controller。
  - `reach-block` 默认仍为 position-only，不影响原有位置调试。
  - `grasp-block --grasp-pose current` 会在命令开始时锁定当前右手 TCP 姿态，然后在 `approach/lower/close/lift` 全阶段保持这个姿态；目标姿态和目标位置一样都是固定 world/base anchor，不跟随被碰动的圆柱。
  - `--grasp-roll/--grasp-pitch/--grasp-yaw` 会在锁定姿态上叠加局部姿态偏移，便于小步调手掌朝向。
  - `/World/Visuals/TargetBlockTCP` marker 现在会显示目标姿态，不再只是 identity orientation 的位置 marker。
  - 状态日志新增 `rot_err=(rx,ry,rz)`，为 root/base frame 下的 axis-angle 姿态误差。调姿态时先让 `right_tcp_dist` 小，再看 `rot_err` 是否下降。
  - 第一版姿态模板故意只做 `current + RPY offset`，不做自动侧向模板。原因是当前还没准确定义 S4 手掌 TCP frame 的“掌心法向/手指方向/拇指方向”，先用可视化 frame 和 RPY 微调把手掌姿态调出来，确认坐标轴后再固化为 `side_grasp` 模板。
- 2026-07-27 用户反馈“圆柱抓不起来”和“reset/reload 后第一次在物块上方空抓，第二次才下降到接近物块高度”：
  - 圆柱质量从 `0.18kg -> 0.08kg`。几何仍为半径 `0.035m`、高度 `0.12m` 的竖直圆柱，摩擦/阻尼/contact/solver 参数保持上一版保守设置。
  - 空抓根因确认在抓取状态机：旧逻辑是 `lower` 阶段“到达 tolerance 或超过 lower_steps 都进入 close”。reset 后右臂刚从上方开始，若 `lower_steps` 先超时，即使 TCP 还没下降到抓取高度，也会闭合手，所以第一次空抓；第二次由于手臂已经更低，才可能下降到接近圆柱高度。
  - 已修复为：`lower -> close` 只能由 `phase_dist <= tolerance` 触发，`lower_steps` 只作为等待告警阈值。若没到位，会每约 1 秒打印 `[ARM] waiting at lower target before closing: dist=... tol=...`，并保持手打开继续向 lower 目标移动。
  - 后续如果一直卡在 lower，不要再把它误判为“状态机坏了”。先看日志中的 `dist/tol/right_tcp_dist/tcp_err/rot_err`：如果距离收不进去，调 `--grasp-z`、`--x-offset/--y-offset`、`--tolerance` 或姿态；如果物体被碰飞，继续降低手部闭合深度/速度或实现 contact-stop。
- 2026-07-27 用户判断圆柱太低导致抓不到，已在圆柱和盘子下面新增任务垫板：
  - 新增 `/World/RecordTask/TaskPlatform`，几何最初为 `0.48m x 0.60m x 0.10m`，后因和桌面 `container_h20` 嵌入，改为 `0.48m x 0.60m x 0.05m` 的 kinematic cuboid，有碰撞和高摩擦材质。
  - 新增 `TaskLayout.task_surface_z(table_top_z) = table_top_z + platform_height`。红/蓝圆柱和盘子都基于这个新 surface 高度计算位置，因此 reset 后也会保持在垫板上。
  - `format_layout()` 现在打印 `task_surface_z` 和 `platform` 位置/尺寸，后续看日志时不要再只看旧的 `table_top_z`。
  - 用户最终决定不在代码中删除桌面上的筐子。`container_h20` 仍作为 PackingTable 视觉资产的一部分存在；后续不再维护 `--remove-table-clutter/--no-remove-table-clutter` 参数，也不再自动改桌子 USD prim active 状态。
  - 用户看到的 `CCD is not supported on GPU, ignoring request to enable it` 是 IsaacSim/PhysX warning，不是致命启动错误。若启动失败，必须继续看后面的 Python traceback 或 Kit error；不要把这行当根因。
- 2026-07-27 用户反馈垫高后右手末端可能被垫块挡住，已继续修正：
  - 废弃单块大垫板 `/World/RecordTask/TaskPlatform`，改为三个独立小垫块：`/World/RecordTask/RedPlatform`、`/World/RecordTask/BluePlatform`、`/World/RecordTask/PlatePlatform`。
  - 红/蓝圆柱小垫块尺寸为 `0.11m x 0.11m x 0.05m`，只支撑圆柱底部，减少手从侧面接近时被大板边缘挡住的概率。
  - 盘子垫块尺寸为 `0.30m x 0.30m x 0.05m`。
  - `grasp-block --grasp-z` 默认从 `-0.04m` 改为 `+0.02m`，让 lower TCP 目标在圆柱中上部，而不是离垫块表面只有约 `2cm`。如果需要更低抓取，再显式传 `--grasp-z 0.00` 或负值，但要注意手指/手掌可能先碰到垫块。
  - 用户 15:10 的 `/tmp/isaaclab/logs/isaaclab_2026-07-27_15-10-15.log` 是空文件；只出现 `CCD is not supported on GPU` 仍不能说明启动失败根因。
- 2026-07-27 用户已验证当前默认配置可用：
  - 可用启动命令曾是 `bash run.sh sim --print-layout --show-tcp-frames --no-remove-table-clutter`，现已固化为 `bash run.sh sim` 默认行为：自动 print layout、显示 TCP frames、且不再删除桌面筐子。
  - 可用抓取命令曾是 `bash run.sh control grasp-block --block blue --grasp-pose current --grasp-pitch 0.1`，现已固化为 `bash run.sh control grasp-block` 默认行为：`block=blue`、`grasp_pose=current`、`grasp_pitch=0.1`。
  - 当前右手可以把蓝色圆柱抓起来，这是进入后续放置/采集数据前的最新稳定基线。
- 2026-07-27 关于“张开时无名指比其他指头慢”的初步判断：
  - URDF 中 `rh_index_mcp_pitch/rh_middle_mcp_pitch/rh_ring_mcp_pitch/rh_pinky_mcp_pitch` 的 limit/effort/velocity 均为 `lower=0`、`upper=1.60`、`effort=100`、`velocity=1`，`rh_ring_mcp_pitch` 本身没有更慢的驱动配置。
  - 右手 policy/control 顺序为 `thumb_yaw, thumb_pitch, index, middle, ring, pinky`，open/close 对四指给的是相同目标。
  - 因此无名指张开慢更可能来自接触/几何卡滞、残余穿透、mimic distal 关节与物体或相邻手指接触，而不是当前 6D command 映射故意让无名指慢。
  - 若稳定化后仍明显慢，需要新增手指 joint state 日志，分别打印四指 `q/q_target/q_err`，再判断是驱动跟随慢还是被接触约束卡住。
- 新增运行中复位命令：`bash run.sh control reset-scene`，别名 `reload-scene`。该命令会重置机器人关节、红蓝块、盘子、相机和控制状态，避免每次控制失败后都重启 IsaacSim。

这套控制适合调试“靠近物块”，还不是完整抓取示教器。

## 已完成工作

已完成：

1. 梳理出 S4 的上身/手部控制空间，确定第一版策略 action 为 26D。
2. 建立 `my_isaaclab_project` 的最小 IsaacLab 调试项目。
3. 完成 S4 URDF 导入、固定 base、驱动关节分组、默认姿态和限位解析。
4. 建立红/蓝物块、盘子、桌面/背景的最小任务场景。
5. 实现 `run.sh` 统一入口。
6. 实现 `/tmp/s4_arm_control.json` 和 `/tmp/s4_joint_command.json` 控制文件链路。
7. 实现 26D action 到仿真 joint target 的映射，并记录手部 mimic 关系。
8. 实现右臂小步 Cartesian reach 调试控制。
9. 实现右手开合目标。
10. 加入 TCP frame 可视化、关节限位、命令平滑和右臂失稳保护。
11. 调研并记录 BenchHub 的 S4 SmolVLA 数据/训练/评估工作流。
12. 参考 BenchHub 框架重构了本项目目录，但没有改动 BenchHub 仓库。
13. 新增 `s4_pipeline/` 作为本项目配置和路径层。
14. 新增 `tasks/bimanual_red_blue_plate.py` 作为任务元数据和 success threshold 预留层。
15. 新增 `data/hdf5_schema.py`、`data/dataset_writer.py`、`data/lerobot_conversion.py`，为后续 HDF5 采集和 LeRobotDataset 转换预留本地实现。
16. 新增 `configs/smolvla_s4_bimanual.yaml` 和 `scripts/train_smolvla_local.sh`，训练入口归本项目所有。
17. 新增 `scripts/00_inspect_project.py`，并在 `run.sh` 增加 `inspect-config`。
18. 在 `run.sh` 增加 `record-hdf5`、`convert-lerobot`、`train-smolvla`、`eval-smolvla` 入口。
19. 数据配置已改为 BenchHub 兼容方向：`observation.state` 预留 50D full/padded state，`observation.active_state` 保留 26D 控制态，`action` 保持 26D。
20. 右臂 reach 控制增加了更保守的默认参数、TCP 误差诊断和失稳保护，降低测试时手臂被甩飞的概率。
21. 修正右臂 reach 的 Jacobian 控制误差坐标系：从 base-frame error 改为 world-frame error，与 PhysX translational Jacobian 对齐。
22. 新增运行中 `reset-scene`/`reload-scene` 控制命令，用于重置机器人、任务物体、相机和控制状态。
23. 为右臂 reach 增加 Jacobian body row/sign 可调参数、预测位移日志、实测背离目标的自适应方向保护，以及 TCP 低于物块时的安全 hold。
24. 根据用户日志确认 wrist 原点 Jacobian 不能直接控制偏移 TCP 点，已改为 TCP point Jacobian：`J_tcp = J_wrist_linear + J_wrist_angular x tcp_offset_world`，并默认关闭自动方向翻转。
25. 根据 `right_arm_cmd_lag=1.089` 诊断出 IK 输出到执行目标之间没有同步当前仿真状态，已改为启动/reset/reach 切入时从 robot-order 关节状态提取 26D action，并让 reach 从当前 `commanded_action` 连续推进。
26. 根据最新日志确认执行同步已正常但真实 TCP 仍和 `pred_w` 反向，增加 `actual_d`、wrist body id、Jacobian row、右臂 joint ids 诊断。
27. 废弃手写 DLS IK 求解，改用 IsaacLab 官方 `DifferentialIKController`；当前/目标 TCP 和 Jacobian 全部按官方 root/base frame 接口输入，`--reach-jacobian-sign` 默认恢复为 raw PhysX sign `1.0`。
28. 新增 `diagnose-right-arm` 控制命令和仿真内诊断逻辑，专门拆解“手总往下走”的根因：hold 漂移、Jacobian 有限差分、逐关节 drive 正向响应、关节 effort/gain。
29. 根据用户诊断日志确认：hold 稳定、Jacobian row25 正确、row26 不可用；已修正 drive 诊断为 settle 后单关节隔离测试，并在 reach 日志中新增 7D `dq` 和 `cmd_delta`。
30. 根据 reset 后诊断确认当前主要问题是 implicit position drive 在重力下存在静态误差；曾尝试 `action_target_bias`，但后续 reach 日志证明固定偏置会抵消小步 IK 命令。当前已废弃固定偏置方案，改为提高 implicit drive 刚度、阻尼和仿真 effort limit。
31. 明确当前 `TargetBlockTCP` 只是位置 marker，orientation 为 identity；当前 reach 是 position-only IK，不会让手末端坐标系和目标坐标系姿态重合。后续抓取必须实现 pose IK 和明确的 grasp frame。
32. 为 `reach-block` 增加目标预览和“目标低于当前 TCP”警告；同时把命令行默认 `--z-offset` 从 `0.14` 改为 `0.20`。以后判断是否掉落前先看 `target_minus_tcp.z`。
33. 新增 `--joint-effort-limit`，默认 `300`，并把 `--joint-stiffness/--joint-damping` 默认提高到 `600/80`；reach 执行层不再叠加固定 `action_target_bias`。
34. 修复 `env_isaaclab` 中 Pinocchio/cmeel 动态库路径；通过 `run.sh` 启动时 `import pinocchio` 和 `import hppfcl` 可用。新增默认开启的 PhysX joint-space gravity compensation 前馈，写入 `set_joint_effort_target()`。
35. 重力补偿后将 reach 默认速度提高到中速档：`target-alpha=0.12`、`max-joint-step=0.018`、`reach-max-cart-step=0.012`、`reach-max-joint-delta=0.030`。
36. 修复 `hand open/close` 回原始姿态的问题：手部命令现在进入 `hold` 模式，保持当前右臂关节状态，只改变右手 6D target。
37. 新增 `control grasp-block` 右手抓取 smoke test，预留 `approach/lower/close/lift` 阶段、阶段超时、TCP tolerance、手部闭合和抬起参数。
38. 默认任务物体位置向机器人方向移动：红/蓝物块和盘子默认 `x=0.50`，用于降低当前右臂 position-only reach 的末端误差。
39. 红/蓝动态任务物体从方块改为竖直圆柱，半径 `0.035m`、当前高度 `0.12m`，用于提高当前手指闭合包络抓取稳定性。
40. 圆柱和手部抓取做第一轮稳定化：圆柱高度/质量调整，摩擦/阻尼/solver/contact 参数更保守，右手 close 目标降低，并修复手部目标绕过平滑导致瞬时闭合的问题。
41. 修复 `grasp-block` 目标参考系：抓取命令开始时锁定圆柱初始位置作为固定 world/base anchor，后续 lower/lift 不再跟随被碰动的圆柱当前位置。
42. 新增手部单独速度限制 `--hand-max-joint-step=0.004`，并把 `grasp-block --close-steps` 默认提高到 `160`，降低 position-controlled 手指夹飞圆柱的概率。
43. 新增 `grasp-block --grasp-pose current` 姿态锁定和 pose IK：抓取流程可保持命令开始时的 TCP 姿态，并可通过 `--grasp-roll/--grasp-pitch/--grasp-yaw` 微调。日志新增 `rot_err`，目标 TCP marker 显示目标姿态。
44. 修复 `grasp-block` 第一次空抓问题：`lower` 阶段不再按 `lower_steps` 超时自动闭合，必须 TCP 进入 tolerance 后才进入 `close`。同时圆柱质量降到 `0.08kg`，提高当前手指夹持后抬起的可能性。
45. 新增任务垫块，当前高度 `0.05m`；单块大垫板已拆成 `RedPlatform/BluePlatform/PlatePlatform` 三个小垫块，红/蓝圆柱和盘子整体抬高到对应垫块表面。删除桌面筐子的逻辑和参数已移除，`container_h20` 不再由代码自动隐藏。
46. 为避免垫高后手末端被垫块挡住，`grasp-block --grasp-z` 默认改为 `+0.02m`，默认抓圆柱中上部；低位抓取必须显式调参并观察是否撞垫块。
47. 固化当前可用默认入口：`bash run.sh sim` 默认等价于带 `--print-layout --show-tcp-frames`，`bash run.sh control grasp-block` 默认等价于右手抓蓝色圆柱并使用 `grasp-pose=current, grasp-pitch=0.1`。

## 未完成工作

高优先级未完成：

1. 双臂控制还没有接通。当前自动 reach 只控制右臂，左臂还没有 `LeftArmReachController` 或统一 bimanual controller。
2. 已有右手 `grasp-block` smoke test 状态机，但还不是稳定真实抓取专家。当前只覆盖 `approach -> lower -> close -> lift`，还没有 place/release；已有 `--grasp-pose current` pose IK 调试，但还没有固化的侧抓/包络抓姿态模板。
3. 当前物块还没有被稳定真实接触抓起并放入盘子。不能用它生成训练数据。
4. 右臂 reach 已切换到 IsaacLab 官方 `DifferentialIKController`，并加了 PhysX gravity compensation；现在执行链路已明显改善，但仍有约 `5cm` 收敛误差。下一步优先测试 `grasp-block`，判断误差是否足以闭合抓住物块；若不够，升级 pose IK/grasp frame。
5. HDF5 writer 和 schema 已经落到本项目，但还没有接入运行中的 IsaacLab scene；`record-hdf5` 目前是 scaffold。
6. LeRobotDataset 转换脚本已落到本项目，但还没有真实 HDF5 样本验证。
7. 策略训练配置和入口已落到本项目，但还没有数据集，不能开始有效训练。
8. 策略回放/评估入口只预留 scaffold，还没接入当前自建场景。
9. 还没有 VR 数据采集接入当前场景。
10. 还没有明确 success checker。
11. 当前自建 `task_sence.usd` 没有被当前 `simulation.py` 默认使用，需要重新接入或明确放弃。

中优先级未完成：

1. 左右手掌朝向控制。只控 wrist/TCP 位置不足以稳定抓块。
2. 手指闭合需要接触/防穿透策略。用户给过 MuJoCo C++ 的 contact-stop 思路，IsaacLab 里尚未实现。
3. 需要检查桌子/场景 collision。如果物块悬浮、掉穿或抖，先查 `table_top_z` 和桌面 collision。
4. state 维度已按“50D full/padded state + 26D active_state/action”方向配置；真正录制时还需要确认当前 IsaacLab 导入后的 full joint state 实际维度是否小于等于 50。
5. 需要选择数据中图像相机：一开始用胸前单相机，后续可加左右腕相机。

## 当前缺陷和风险

1. `my_isaaclab_project/README.md` 仍然写“唯一调试记录”，但全局路线图现在以本文件为主。后续如果两者冲突，以本文件为准，再更新 README。
2. `configs/s4_bimanual_dataset.json` 仍写旧默认 scene/table 路径，和用户自建 `task_sence.usd` 不一致。
3. `run.sh` 已有新入口；`record-physics`、`check-dataset`、`bimanual` 仍然不是当前子命令，后续不要再调用旧命令。
4. `03_record_physics_dataset.py` 还没录数据，命名可能误导。可以后续重命名为 `03_debug_physics_scene.py`，再新增真正的 recorder。
5. 当前 scene 只 spawn 一个视觉桌子，任务物体依赖 `table_top_z` 手动放到桌面高度。桌子实际碰撞形状和 `table_top_z` 可能不一致。
6. BenchHub 脚本使用 `/opt/anaconda3`、`lw_benchhub3`、`/home/ubuntu/.cache/...`，不能直接在本机运行。
7. BenchHub 的 `eval_smolvla_policy.py` 对 S4 关节 index 有硬编码。我们本项目更应按关节名映射，避免 URDF 导入顺序变化导致错位。
8. 如果直接用脚本把物块 pose 写到手上生成 demo，训练出的策略会学到不可物理复现的轨迹。只有数据链路 smoke test 可以这么做，正式数据必须来自真实接触或人工/VR 控制。
9. 手末端坐标系和物块坐标系方向不一致对当前 position-only reach 没有直接影响，因为当前只用世界坐标位置误差，不用目标姿态。但后续真实抓取必须显式控制手掌朝向，否则接近姿态会不稳定。
10. 当前 S4 导入配置 `self_collision=False` 且 articulation root `enabled_self_collisions=False`，所以“右臂甩飞”优先按控制器发散/目标不可达/PD 过硬处理，不应先假设是机器人自身碰撞。后续如果打开 self collision，需要单独做 collision filter。

## 推荐架构

推荐把后续代码整理为四层：

```text
Simulation Layer
  - S4 URDF/USD 加载
  - 用户自建 scene 或官方 scene 加载
  - 桌子、红/蓝物块、盘子
  - 相机、reset、success、collision 检查

Control Layer
  - 26D 双臂双手 action/state
  - 6D hand input -> mimic/full joint targets
  - 左右臂 reach / grasp / place 状态机
  - 后续 VR retarget 或 IK 控制都输出同一个 26D action

Data Layer
  - IsaacLab episode HDF5/staging writer
  - HDF5 字段兼容 BenchHub convert 脚本
  - HDF5 -> LeRobotDataset
  - dataset review / replay / quality filter

Training/Eval Layer
  - SmolVLA train YAML
  - checkpoint 管理
  - policy rollout 回当前 IsaacLab 场景
  - 成功率、视频、失败样例记录
```

## State/Action 维度决策

动作维度保持 26D，这是稳定决策：

```text
action = left_arm_7 + left_hand_6 + right_arm_7 + right_hand_6
```

state 有两个方案：

方案 A：26D state + 26D action

- 优点：简单，和我们 `control_mapping.py` 一致。
- 优点：SmolVLA 默认 `max_state_dim=32` 就够。
- 缺点：和 BenchHub 已跑通数据集不完全一致。
- 适合：第一版最小自建数据闭环。

方案 B：50D/full state + 26D action

- 优点：和 BenchHub `smolvla_s4.yaml`、`S4-Hand.yaml`、`eval_smolvla_policy.py` 一致。
- 优点：保留更多机器人状态，后续评估可复用 BenchHub 的抽取逻辑。
- 缺点：需要明确当前导入机器人 full joint order，不能随便硬编码 index。
- 适合：想最大化复用 BenchHub 数据和评估工具。

当前推荐：短期 HDF5 同时保存 full joint state 和 26D active state；转 LeRobotDataset 第一版先用 26D state，等要复用 BenchHub 训练/评估脚本时再切 50D state。不要只保存 26D 后丢掉 full state。

## HDF5 字段建议

为了兼容 BenchHub 的转换脚本，后续 recorder 输出建议采用：

```text
data/demo_0/
  processed_actions                         float32[T, 26]
  states/articulation/robot/joint_position  float32[T, N_full]
  obs/s4_active_joint_pos                   float32[T, 26]
  obs/chest_front_rgb                       uint8[T, H, W, 3]
  obs/left_arm_eef_pose                     float32[T, 7]
  obs/right_arm_eef_pose                    float32[T, 7]
  states/rigid_object/red_block/root_pose   float32[T, 7]
  states/rigid_object/blue_block/root_pose  float32[T, 7]
  states/rigid_object/plate/root_pose       float32[T, 7]
```

episode attrs 建议保存：

```text
env_args:
  task_name
  robot_name
  scene_usd
  table_top_z
  fps
  action_dim
  state_dim
  joint_names
  action_names
```

如果直接复用 BenchHub `convert_hdf5_to_lerobot_dataset.py`，最低要求是：

- `data/demo_*`
- `processed_actions`
- `states/articulation/robot/joint_position` 或 `obs/real/joint_pos`
- 至少一个相机路径，例如 `obs/chest_front_rgb`

## LeRobotDataset 目标 schema

第一版建议：

```text
fps = 20 或 30，必须和采集 fps 一致
robot_type = S4-Bimanual 或 S4-Hand
task = "Use the left hand to put the red block into the tray and the right hand to put the blue block into the tray."

observation.images.chest_front: video uint8 [480, 640, 3]
observation.state: float32 [26] 或 [N_full]
action: float32 [26]
```

如果用 50D state，训练配置必须设置：

```yaml
max_state_dim: 50
max_action_dim: 32
```

如果用 26D state，可以设置：

```yaml
max_state_dim: 32
max_action_dim: 32
```

## 下一阶段实施顺序

### 阶段 1：把当前仿真物理确认稳定

目标：物块在桌上稳定，机器人不抖，右臂 reach 不炸。

建议测试：

```bash
cd /home/zfy/smolVLA/my_isaaclab_project
bash run.sh sim --print-layout --show-tcp-frames
```

检查：

- 桌子和物块在同一高度。
- 红/蓝物块不是悬浮，也不掉穿桌子。
- 机器人双臂 idle 不乱甩。
- 右手 TCP frame 位置合理。

如果物块悬浮或穿桌：

- 先调 `--table-top-z`。
- 再查桌子 USD 是否有 collision。
- 不要先改控制器。

### 阶段 2：接左臂并统一双臂控制器

实现：

- 把 `RightArmReachController` 泛化成 `ArmReachController(side="left"|"right")`。
- 左臂 wrist body：需要从实际 `robot.body_names` 打印确认。
- 左臂关节：`LEFT_ARM_JOINTS`。
- 左手开合：新增 `OPEN_LEFT_HAND`、`CLOSE_LEFT_HAND`。
- 控制文件支持：
  - 左手抓红块
  - 右手抓蓝块
  - 双臂同时或分阶段执行。

验收：

- 左右 TCP 都能稳定接近各自物块上方。
- 两臂同时移动时不互相打架。

### 阶段 3：做真实接触抓取状态机

状态机建议：

```text
reset
approach_left/right
lower_left/right
close_hands
lift_blocks
move_to_plate
release
success_check
```

第一版可以左右臂同步，也可以先右后左。为了调试简单，建议先右臂单块真实抓起，再复制到左臂，再做双臂同步。

验收：

- 物块不是 kinematic 跟手，而是通过手指/碰撞被带起。
- lift 后物块高度明显超过桌面。
- place 后物块中心落到 plate 半径内。

### 阶段 4：实现 HDF5 recorder

新增建议文件：

```text
my_isaaclab_project/scripts/04_record_bimanual_hdf5.py
my_isaaclab_project/s4_robot/dataset_writer.py
```

短期可以先不接 LeRobot，先录 BenchHub 兼容 HDF5。

验收：

- 录 3 条 demo。
- HDF5 能用 `h5py` 打开。
- 每条 demo 的 `processed_actions` shape 是 `[T, 26]`。
- full joint state 和 26D active state 都存在。
- 图像能读出且不是黑图。

### 阶段 5：转换 LeRobotDataset

可以二选一：

1. 直接复制/适配 BenchHub `convert_hdf5_to_lerobot_dataset.py` 到 `my_isaaclab_project/scripts/05_convert_hdf5_to_lerobot.py`。
2. 直接在 `qi-studio-benchhub` 里运行转换脚本，输入 root_path 指向我们的 HDF5。

推荐先复制适配，避免依赖 BenchHub 的环境路径。

验收：

- 生成 `datasets/lerobot_data/s4_bimanual_red_blue_plate_v0`。
- LeRobotDataset 能加载。
- `meta/info.json`、`data/`、`videos/` 存在。
- 随机读取一帧，能看到图像、state、action、task。

### 阶段 6：SmolVLA 训练配置

建议新增：

```text
my_isaaclab_project/configs/smolvla_s4_bimanual.yaml
my_isaaclab_project/scripts/train_smolvla_local.sh
```

配置从 BenchHub `configs/policy/smolvla_s4.yaml` 改：

- `dataset: s4_bimanual_red_blue_plate_v0`
- `dataset_root: /home/zfy/smolVLA/datasets/lerobot_data`
- `output_dir: /home/zfy/smolVLA/outputs/train/smolvla_s4_bimanual_v0`
- `max_state_dim`: 按数据集 state 选 32 或 50。
- `max_action_dim: 32`
- `chunk_size`: 第一版可以小于 100，例如 20 或 50，取决于 episode 长度和显存。
- `vlm_model_name`: 改成本机实际 SmolVLM2 路径，不能保留 `/home/ubuntu/...`。

第一轮训练只做 smoke test：

- 5-10 条 demo。
- 训练 1000-3000 steps。
- 目标是确认能开始训练、loss 不 NaN、checkpoint 能保存。

### 阶段 7：策略评估

短期要写自己的评估入口，而不是直接用 BenchHub `eval_smolvla_policy.py`，因为当前环境不是 BenchHub 的 Robocasa task。

建议新增：

```text
my_isaaclab_project/scripts/06_eval_smolvla_in_isaaclab.py
```

功能：

- 加载 SmolVLA checkpoint。
- 从当前仿真相机和 state 构造 batch。
- 调 `policy.select_action(batch)`。
- 通过 `control_mapping.py` 写入 26D action。
- 记录视频、success、失败原因。

可以参考 BenchHub：

- 如何加载 `SmolVLAPolicy.from_pretrained`
- 如何构造 language tokens
- 如何处理 `observation.images.*`
- 如何调用 `policy.reset()` 和 `policy.select_action()`

不要照抄硬编码 50D index，除非当前数据集明确采用 BenchHub 50D order。

## 用户自建场景策略

用户曾经创建并保存：

```text
/home/zfy/smolVLA/task_sence.usd
```

历史注意点：

- 这个 USD 之前没有 `defaultPrim`，普通 reference 可能报 `Unresolved reference prim path ... <defaultPrim>`。
- 旧脚本曾经用显式引用 `</World>` 到 `/World/OfficialScene` 解决。
- 后来为避免重复，曾经改为“只使用保存好的 Robot/RedBlock/BlueBlock/Plate，不再额外 spawn”。
- 当前 `simulation.py` 已经不包含这套路由。

后续如果要恢复用户自建场景，推荐重新实现为清晰开关：

```bash
bash run.sh sim --scene-usd /home/zfy/smolVLA/task_sence.usd --table-usd none
```

实现要求：

- 支持 `--table-usd none`，避免额外生成桌子。
- 如果 USD 没有 defaultPrim，用 USD API 显式 reference `</World>`。
- 明确当前 scene 是否已经包含 Robot/RedBlock/BlueBlock/Plate。
- 如果 scene 已包含这些 prim，就不要再次 spawn，避免两套机器人/物块/盘子。
- 如果只包含环境和桌子，则继续 spawn robot/task objects 到 `/World/Robot` 和 `/World/RecordTask/*`。

## 手部映射必须保留

用户明确提醒：一只手只有 6 个控制关节，但实际关节数不只 6，控制输入变成关节角时需要映射。

当前映射在 `my_isaaclab_project/s4_robot/control_mapping.py`，以后不要让策略直接输出 11 个手指物理关节。

O6 hand 参考关系：

```text
cmd[0] -> thumb_cmc_yaw
cmd[1] -> thumb_cmc_pitch
cmd[2] -> thumb_ip 或由 thumb_cmc_pitch 派生，当前项目按 mimic 处理
cmd[3] -> index_mcp_pitch, index_dip = index_mcp_pitch * 0.89
cmd[4] -> middle_mcp_pitch, middle_dip = middle_mcp_pitch * 0.89
cmd[5] -> ring_mcp_pitch, ring_dip = ring_mcp_pitch * 0.89
cmd[6] -> pinky_mcp_pitch, pinky_dip = pinky_mcp_pitch * 0.89
```

注意：用户提供的 C++ DDS 命令数组是 `kO6CmdMotors=7`，但当前 Python policy 空间按“每手 6 active joints”实现，没有单独输出 thumb_ip。后续如果真机 DDS 接口必须 7 维，需要在部署层做 6D policy hand -> 7D DDS command 的适配，不能改变训练数据的动作语义。

## 近期建议执行清单

下一次继续开发建议按这个顺序：

1. 先解决右臂 reach 控制方向问题。启动：

```bash
cd /home/zfy/smolVLA/my_isaaclab_project
bash run.sh sim --print-layout --show-tcp-frames
```

然后另一个终端发送：

```bash
bash run.sh control reset-scene
bash run.sh control diagnose-right-arm --eps 0.01 --hold-steps 120 --drive-steps 40
bash run.sh control reach-block --block blue --z-offset 0.20 --offset-frame world
```

先看诊断日志：

- 如果 `hold_drift.z` 在 120 steps 内明显为负，说明即使没有 IK，手也被重力/驱动保持能力拉下去。用户 2026-07-27 的诊断显示当前 `hold_drift` 为 0，因此短期不要再把首要原因归到重力补偿。
- 如果 `fd` 的有限差分和某个 `row` 的 cos 接近 `+1`，该 row 才是可用 Jacobian row；若默认 row 不匹配，启动仿真时显式设置 `--reach-jacobian-body-shift`。
- 如果 `drive+` 的 `all_right_dq` 显示多个非测试关节一起明显运动，说明测试前状态/目标仍未同步好，先修同步；如果只有被测关节运动，再用 `tcp_delta` 和 `fd` 对比。
- 如果 `drive+` 的 `q_delta` 和 `target_delta` 反向或很小，说明位置目标执行层异常；这时 IK 算得再对也会被执行成错误方向。
- 如果 hold 在 reset 后先下沉、随后稳定，说明是 position drive 静态误差。不要再用固定 `action_target_bias` 硬补 position target；它会抵消小步 IK。优先提高仿真 drive stiffness/damping/effort limit，后续再实现真正动力学重力补偿或 OSC。
- 如果 hold 稳、fd 匹配、drive+ 正常，但 reach 仍下降，再检查官方 IK 输入的 TCP offset/姿态和 `right_tcp_position()` 可视化是否是同一个 frame。
- 如果手末端 frame 和 `TargetBlockTCP` frame 朝向不一致，这不是 position reach 的失败条件。当前 target marker 姿态固定为 identity，position IK 不控制姿态。需要姿态重合时，先定义目标抓取 quaternion，再切 pose IK。
- 如果 `--z-offset` 设得太小，比如 `0.10`，目标 TCP 可能低于当前手 TCP；这时下移是正确行为。先看新日志 `target_minus_tcp.z`，不要把目标在下方导致的下移误判为控制器掉落。
- 重力补偿默认开启。若 reach 精度仍差，先确认日志有 `gravity_comp=max/mean` 且非零；若为零，说明 PhysX gravity compensation forces 没有正确接入。不要再回到固定 `action_target_bias` 方案。

再看 reach 日志中的 `right_arm_cmd_lag`、`step_w`、`pred_w`、`actual_d`、`tcp`、`progress`。当前代码已经切换到 IsaacLab `DifferentialIKController`，并在 reach 切入时同步当前仿真关节状态，默认 Jacobian 符号是 raw PhysX sign `1.0`：

- 如果 `right_arm_cmd_lag > 0.1rad`，先查 action/commanded_action/full_command_target 同步，不要继续调 Jacobian。
- 如果 `actual_d` 开始和 `tcp_err/step_w` 同向，说明官方 IK 链路修复了方向问题。
- 如果 `step_w.z/pred_w.z` 都为正，但 `actual_d.z` 仍持续为负，记录日志并优先测试重启仿真时加 `--reach-jacobian-body-shift 0`。
- 如果 `pred_w` 和 `step_w` 明显反向，重启仿真时先试 `--reach-jacobian-sign -1`。
- `--reach-adaptive-direction-sign` 当前默认关闭；只有在确认 Jacobian body row 正确但整体运动仍反向时，再临时打开它做诊断。

2. 打印并记录 `robot.joint_names`、`robot.body_names`，确认左/右 wrist body 名称和 PhysX Jacobian row 的对应关系。
3. 把 `RightArmReachController` 泛化为左右臂通用控制器。
4. 加一个最小双臂 reach 命令：左到红块上方，右到蓝块上方。
5. 做右臂单块真实抓取状态机。
6. 成功后复制到左臂，再做双臂双块放盘。
7. 任务稳定后再写 HDF5 recorder。
8. 用 BenchHub 转换脚本结构生成 LeRobotDataset。
9. 改本机 SmolVLA 训练 YAML，先跑 1000 steps smoke test。
10. 写当前 IsaacLab 环境自己的 SmolVLA rollout 评估脚本。

## 当前不要做的事

- 不要再调用 `bash run.sh bimanual --mode scripted_demo`，入口已经不存在。
- 不要用旧 MuJoCo 教程的旧版 `lerobot.common.*` API 作为训练依据。
- 不要在物理抓取没成功前采正式训练数据。
- 不要把腿部放进 action。
- 不要让策略直接输出所有手部 mimic joints。
- 不要直接运行 BenchHub 脚本而不改环境名和 `/home/ubuntu` 路径。
- 不要用硬编码关节 index 替代关节名映射，除非已经确认当前数据集就是 BenchHub 的 50D 顺序。
