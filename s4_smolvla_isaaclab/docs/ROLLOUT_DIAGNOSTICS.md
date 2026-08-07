# SmolVLA Rollout 诊断手册

本文档说明当前抽屉任务的在线推理控制链路、平滑机制、阶段门控以及如何区分策略抖动和底层执行问题。所有实现都在本项目中，未修改 `/home/zfy/smolVLA/lerobot`。

## 当前控制链路

```text
IsaacLab 当前 26D joint state + 三路 680x480 RGB + 当前阶段文本
-> 项目侧 JSON-lines policy server
-> LeRobot preprocessor
-> SmolVLAPolicy.predict_action_chunk()，输出 50x26
-> LeRobot postprocessor，恢复为实际关节角单位
-> 数据集 min/max 限幅
-> 相邻两条 chunk 交叉融合
-> 阶段切换新旧命令融合
-> 20 Hz 目标关节角
-> 6 个物理步线性插值为 120 Hz 命令
-> 26D 控制量展开到机器人 active/mimic joints
-> IsaacLab position target
```

代码位置：

- `scripts/09_smolvla_policy_server.py`：调用 LeRobot 预处理、`predict_action_chunk()` 和后处理。
- `scripts/06_eval_smolvla_in_isaaclab.py`：chunk 融合、阶段过渡、状态门控、插值、关节控制、视频和诊断输出。
- `s4_robot/control_mapping.py`：26D 策略动作到机器人关节的映射。
- `configs/tasks/drawer_insert_close.scripted.yaml`：阶段文本、手部目标和抽屉状态条件。

## 本次改动

### 1. 动作诊断记录

每个 20 Hz policy frame 记录：

```text
raw       当前最新 chunk 对该时刻的原始预测
ensemble  相邻 chunk 融合并完成阶段过渡后的目标
command   经过关节步长限制后的 20 Hz 终点命令
actual    command 经 6 个 120 Hz 插值步执行后读取的实际 26D joint state
```

同时记录 `policy_frame`、`sim_step`、`phase_index`、`phase_frame`、`chunk_count` 和 `drawer_open_m`。

### 2. 固定时间基准

- 物理和关节控制：120 Hz。
- 数据集与策略时间轴：20 Hz。
- 每个策略目标在 6 个物理步内做严格线性插值。
- 旧参数 `--target-alpha` 仅为命令兼容而保留，在线 rollout 不再执行逐物理步指数平滑。

### 3. 有限 chunk 重叠融合

SmolVLA 的 flow-matching 输出带采样性，不能像确定性 ACT 一样长期平均很多条 chunk。当前默认：

```text
--chunk-replan-frames 25
--chunk-overlap-blend-frames 5
```

即每 1.25 秒获取一条新 50 帧 chunk，只保留上一条和最新一条，并在 0.25 秒内交叉融合。不会同时平均三条以上轨迹。

### 4. 阶段状态门控

阶段首先执行数据集统计出的中位持续时间。时间到达后，再检查：

- 左右臂命令与实际关节角误差。
- 张手是否到达 open target。
- 闭手是否至少产生 10% 闭合进度。
- YAML 中配置的抽屉最小/最大开度。
- 关闭阶段的最终抽屉阈值。

闭手不要求到达自由空间完全闭合角，因为手指应被把手或罐子接触阻挡。门控最多延长 20 个策略帧，之后强制进入下一阶段，避免无限等待。

### 5. 阶段切换融合

默认使用：

```text
--phase-transition-blend-frames 8
```

阶段文本变化时，在 0.4 秒内从旧命令过渡到新 chunk。阶段总时长仍采用训练数据的中位数，不额外改变训练时序。

### 6. 底层执行器保持不变

本轮没有通过 stiffness/damping 掩盖策略接口问题。默认仍为：

```text
joint_stiffness=600
joint_damping=80
joint_effort_limit=300
```

只有确认 `command` 平滑但 `actual` 仍高频抖动后，才应调整这些参数。

## 标准诊断命令

先关闭任务随机性，建立可重复基线：

```bash
conda activate env_isaaclab
cd /home/zfy/smolVLA/s4_smolvla_isaaclab

bash run.sh eval-smolvla \
  --checkpoint outputs/train/smolvla_drawer_insert_close_v0/checkpoints/360000/pretrained_model \
  --steps 0 \
  --policy-device cuda \
  --no-randomize-task \
  --output-video outputs/eval/smolvla_drawer_rollout_diagnostic.avi
```

无界面运行时加 `--headless`。注意，无界面仍会渲染三路策略相机和诊断视频。

一次运行会生成：

```text
outputs/eval/smolvla_drawer_rollout_diagnostic.avi
outputs/eval/smolvla_drawer_rollout_diagnostic_actions.csv
outputs/eval/smolvla_drawer_rollout_diagnostic_actions.png
```

结束时终端还会直接打印四组数值摘要：

```text
[DIAG] LA raw_jump(mean/p95)=... fused_jump=... tracking=...rad
[DIAG] LH raw_jump(mean/p95)=... fused_jump=... tracking=...rad
[DIAG] RA raw_jump(mean/p95)=... fused_jump=... tracking=...rad
[DIAG] RH raw_jump(mean/p95)=... fused_jump=... tracking=...rad
```

先比较 `raw_jump` 和 `fused_jump`：后者明显更低说明融合减少了策略跳变。再看 `tracking`：如果它仍然很大，问题位于 command 之后的执行链路或物理接触。

## 如何阅读诊断图

图中分组：

```text
LA = left arm，7D
LH = left hand，6D
RA = right arm，7D
RH = right hand，6D
```

第一幅 `raw jump [rad]`：相邻 20 Hz 原始策略输出的最大关节跳变。

- 大量尖峰说明策略采样或阶段文本切换产生不连续输出。
- 尖峰只出现在阶段边界时，优先调整阶段融合帧数。
- 阶段内部持续尖峰时，优先检查模型、观测对齐和 chunk 重规划频率。

第二幅 `smoothing correction [rad]`：`abs(raw - ensemble)` 的分组最大值。

- 在 chunk 重规划或阶段切换附近短暂升高是预期行为。
- 长时间保持很大说明新旧 chunk 模式差异过大，不应继续增加同时融合的 chunk 数量。
- correction 为零但 raw jump 很大，说明融合功能被关闭或没有重叠 chunk。

第三幅 `tracking error [rad]`：`abs(command[k] - actual_after_execution[k])`
的分组最大值。`command[k]` 是这一 20 Hz 控制周期希望到达的终点，
`actual_after_execution[k]` 是完成对应 6 个物理步后读取的实际关节角，
两者已经按控制周期对齐。

- `raw` 抖但 `command` 平滑：抖动来自策略，融合正在生效。
- `command` 平滑且手臂 `actual` 仍抖：检查 actuator、重力补偿、碰撞和关节映射。
- 机械臂误差持续大于约 0.08 rad：控制跟踪或动作可达性存在问题。
- 灵巧手在抓取接触期间出现 0.3 到 0.7 rad 误差不一定是故障，需结合视频判断手指是否被物体正常阻挡。
- 张手后误差仍长期很大，则更可能是 mimic mapping、碰撞卡住或执行器配置问题。

## CSV 字段

标量字段：

```text
policy_frame, sim_step, phase_index, phase_frame, chunk_count, drawer_open_m
```

向量字段按 26D action layout 展开：

```text
raw.<joint_name>
ensemble.<joint_name>
command.<joint_name>
actual.<joint_name>
```

例如右臂第一个关节可以直接查看：

```text
raw.right_shoulder_pitch_joint
ensemble.right_shoulder_pitch_joint
command.right_shoulder_pitch_joint
actual.right_shoulder_pitch_joint
```

`command` 不是 LeRobot 的直接输出。它依次经过 action 反归一化、数据集
范围裁剪、chunk/阶段融合和最大关节步长限制，然后作为当前 20 Hz 周期的
控制终点。120 Hz 中间插值点不会逐个写入 CSV。

26D 顺序固定为：

```text
0:7    left_arm
7:13   left_hand
13:20  right_arm
20:26  right_hand
```

`chunk_count` 正常只能为 1 或 2。若出现大于 2，说明 rollout 又开始同时融合多条随机轨迹，应先修复接口再评估策略。

## A/B 排查顺序

每组测试使用不同输出文件名，并固定 `--no-randomize-task --seed 42`。

### A. 当前推荐配置

```bash
bash run.sh eval-smolvla \
  --checkpoint outputs/train/smolvla_drawer_insert_close_v0/checkpoints/360000/pretrained_model \
  --policy-device cuda --no-randomize-task \
  --output-video outputs/eval/ab_current.avi
```

### B. 关闭 chunk 交叉融合

```bash
bash run.sh eval-smolvla \
  --checkpoint outputs/train/smolvla_drawer_insert_close_v0/checkpoints/360000/pretrained_model \
  --policy-device cuda --no-randomize-task \
  --chunk-overlap-blend-frames 0 \
  --output-video outputs/eval/ab_no_chunk_blend.avi
```

比较两张 actions PNG 的 `raw jump`、`smoothing correction` 和视频中的瞬时甩动。

### C. 关闭阶段融合

```bash
bash run.sh eval-smolvla \
  --checkpoint outputs/train/smolvla_drawer_insert_close_v0/checkpoints/360000/pretrained_model \
  --policy-device cuda --no-randomize-task \
  --phase-transition-blend-frames 0 \
  --output-video outputs/eval/ab_no_phase_blend.avi
```

若只在阶段边界明显变差，说明阶段融合有效。

### D. 关闭状态门控

```bash
bash run.sh eval-smolvla \
  --checkpoint outputs/train/smolvla_drawer_insert_close_v0/checkpoints/360000/pretrained_model \
  --policy-device cuda --no-randomize-task \
  --no-phase-state-gating \
  --output-video outputs/eval/ab_no_state_gate.avi
```

若动作更快但抓取、张手或抽屉状态更容易失败，说明门控应保留；不要仅靠增加固定阶段时间解决。

### E. 完全关闭项目侧过渡，用作接口基线

```bash
bash run.sh eval-smolvla \
  --checkpoint outputs/train/smolvla_drawer_insert_close_v0/checkpoints/360000/pretrained_model \
  --policy-device cuda --no-randomize-task \
  --chunk-replan-frames 50 \
  --chunk-overlap-blend-frames 0 \
  --phase-transition-blend-frames 0 \
  --no-phase-state-gating \
  --output-video outputs/eval/ab_minimal_postprocess.avi
```

120 Hz 线性插值始终保留，因为它是 20 Hz policy 与 120 Hz physics 的时间基准适配，不属于可选滤波。

## 判断问题来自哪里

| 现象 | 优先结论 | 下一步 |
|---|---|---|
| `raw` 高频跳变，`command` 明显更平滑 | 策略/chunk 采样抖动 | 调大重规划间隔，保留短交叉融合 |
| 只在语言阶段边界出现大跳变 | 新旧阶段命令不连续 | 调整 `--phase-transition-blend-frames`，通常 5 到 10 |
| `command` 平滑，机械臂 `actual` 抖动 | 底层跟踪问题 | 检查 gravity compensation、碰撞、stiffness/damping |
| 手在空中也有很大跟踪误差 | 手部映射/执行器问题 | 检查 6D 到 mimic joints 映射和 joint limits |
| 只在夹住物体时手部误差大 | 正常接触或摩擦 | 结合视频判断，不要要求完全闭合 |
| `chunk_count > 2` | 融合了过多随机轨迹 | 修复 chunk 缓存逻辑 |
| 阶段频繁打印 `[GATE] forced` | 阈值不合理或动作未完成 | 根据日志中的 arm/hand/drawer 原因单独调阈值 |

## 当前验证基线

360K checkpoint、固定场景、当前默认参数的验证结果：

```text
complete=True
success=True
sim=23.6s
drawer=0.003m
can_z=1.023m
video=2040x480, 20 fps, 471 frames
```

该结果只能证明接口和一次固定场景 rollout 可工作。评估策略泛化性时应恢复随机化，运行多次 episode，并统计任务成功率，而不是只看单次视频。
