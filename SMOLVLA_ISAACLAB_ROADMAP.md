# S4 Humanoid 双臂 SmolVLA + IsaacLab 路线

本文档记录当前项目的迁移框架和开始顺序。目标是：用自己的 S4 人形机器人，在 IsaacLab 中搭双臂操作任务，采集 LeRobotDataset，再用 SmolVLA 训练和回放策略。

> 当前约束更新（2026-07-17）：旧 `scripts/02_bimanual_plate_scene.py` 和 `bash run.sh bimanual --mode scripted_demo` 已删除/废弃。后续数据集工作分两步：`env_isaaclab` 用 `my_isaaclab_project/scripts/03_record_physics_dataset.py` / `bash run.sh record-physics` 录制 staging episodes；`smolvla` 环境用 `my_isaaclab_project/scripts/05_convert_staging_to_lerobot.py` 调 LeRobot 官方 writer 生成最终 LeRobotDataset。任何 LeRobot/SmolVLA 数据格式、训练参数、record/rollout 接口必须先查 `lerobot/src/lerobot` 源码，不再按旧 demo 或旧教程自行推断。

## 现有项目分工

当前顶层目录建议按下面理解：

```text
smolVLA/
├── lerobot/                    # 上游 LeRobot 主仓库：数据集、训练、SmolVLA、EnvHub
├── lerobot-mujoco-tutorial/    # MuJoCo 教程：参考数据格式、采集/训练流程，不直接迁移仿真代码
├── my_robot/                   # 自己的机器人资产：URDF、mesh、手部 URDF
└── my_isaaclab_project/        # 自己的 IsaacLab 仿真项目：机器人导入、场景、遥操作、EnvHub 入口
```

两份 GitHub 项目的价值不同：

- `lerobot/` 是长期依赖，后续应尽量按它当前版本的 CLI、数据集格式和 policy 接口走。
- `lerobot-mujoco-tutorial/` 只作为流程样例：如何定义 observation/action、如何采集 LeRobotDataset、如何训练 SmolVLA。它里面的 MuJoCo 环境和旧版 `lerobot.common.*` 训练脚本不建议直接照搬。

## 总体架构

推荐把系统拆成四层：

```text
IsaacLab Simulation Layer
  - 加载 S4 URDF
  - 搭桌面/物体/双臂任务
  - 物理、相机、碰撞、reset、success

Control Abstraction Layer
  - 只暴露双臂 + 双手控制输入
  - 腿部固定或维持默认姿态
  - 动作向量 <-> IsaacLab 关节目标映射
  - 手部 6 控制输入 -> 多个物理/联动关节映射

LeRobot Data/Env Layer
  - Gymnasium Env 或 EnvHub make_env()
  - observation: images + state
  - action: 双臂双手控制向量
  - record/replay/eval 与 LeRobot 对齐

SmolVLA Training Layer
  - 读取 LeRobotDataset
  - 离线训练 / finetune lerobot/smolvla_base
  - 导出 checkpoint
  - 回到 IsaacLab rollout
```

## 两个 Conda 环境的职责

不要一开始试图把 IsaacSim 和 SmolVLA 训练依赖塞到同一个环境里。建议先强制分离：

```text
env_isaaclab
  用途：IsaacSim/IsaacLab 仿真、遥操作、采集数据、仿真评估
  需要：isaacsim, isaaclab, gymnasium, numpy, 可导入当前 my_isaaclab_project

smolvla
  用途：LeRobotDataset 检查、SmolVLA 训练、checkpoint 管理
  需要：lerobot[smolvla,dataset] 或当前 lerobot editable install
  Python：你当前是 python 3.12，训练环境可以单独维护
```

两边的交换物只应该是：

- 本地数据集目录，例如 `datasets/s4_bimanual_pick_place/`
- 或 Hugging Face Hub dataset repo
- 训练后的 checkpoint，例如 `outputs/s4_smolvla/checkpoints/...`

## 第一阶段：先把机器人和任务接口定死

不要一开始就训练。第一阶段目标是把“一个 step 的数据长什么样”定死。

### 机器人自由度策略

当前 S4 URDF 解析结果应按这个逻辑使用：

- 腿部：不作为 policy 动作输出，保持默认站姿或固定底座。
- 双臂：每只 7 个控制关节，共 14 维。
- 双手：每只手 6 个控制输入，共 12 维。
- 初期双臂双手动作：`14 + 12 = 26` 维。

建议第一版 action 定义：

```text
action = [
  left_arm_7,
  left_hand_ctrl_6,
  right_arm_7,
  right_hand_ctrl_6,
]
shape = (26,)
```

状态 `observation.state` 第一版建议也用同样的受控关节空间：

```text
observation.state = [
  left_arm_7 current qpos,
  left_hand_ctrl_6 current command/state,
  right_arm_7 current qpos,
  right_hand_ctrl_6 current command/state,
]
shape = (26,)
```

这样有三个好处：

- SmolVLA 默认 `max_state_dim=32`、`max_action_dim=32`，26 维不用改模型配置。
- 数据集的 state/action 语义一致，便于模仿学习。
- 后续如果要加腕部末端 pose、物体 state 或全身状态，可以单独扩展，而不是一开始把 38/48 个物理关节都塞进去。

### 必须记住的手部映射问题

你的每只手只有 6 个控制输入，但 URDF/IsaacLab 中实际关节数不只 6 个，且有 mimic/联动关节。这个问题建议放在 `Control Abstraction Layer`，不要让 SmolVLA 直接输出物理全关节。

后续应实现一个明确模块：

```text
hand_control_6 -> physical_hand_joint_targets
physical_hand_joint_state -> hand_control_6_state
```

建议文件位置：

```text
my_isaaclab_project/s4_robot/control_mapping.py
```

里面放：

- 双臂/双手 action 名称和顺序。
- 手部 6 维控制输入到 IsaacLab 关节 target 的映射。
- mimic 关节、DIP 关节或其它从动关节的处理。
- clip 到 URDF joint limits。

这点现在可以先用最简单的“一一对应 6 个主动关节，mimic 交给 URDF/导入器处理”，但接口要先留好。

## 第二阶段：IsaacLab 环境先跑通，不接 SmolVLA

目标：在 `env_isaaclab` 中跑通下面三件事：

1. 加载 S4 机器人，确认双臂/双手关节顺序和 limits。
2. 搭一个最小双臂任务场景，例如桌面双臂搬块、开盒、双手扶持物体。
3. 用随机 action 或键盘遥操作跑完整 episode，能 reset、step、render、判断 success。

建议先保留并整理当前目录：

```text
my_isaaclab_project/
├── README.md
├── env.py
├── s4_robot/
│   ├── s4_robot_cfg.py          # URDF、关节分组、默认姿态、limits
│   ├── control_mapping.py       # 新增：26维 policy action/state 映射
│   ├── s4_bimanual_env.py       # 新增或替代：双臂任务 DirectRLEnv
│   └── wrappers.py              # 新增：IsaacLab tensor -> Gym/LeRobot numpy wrapper
├── tasks/
│   └── bimanual_pick_place.py   # 可选：任务参数、物体、奖励、success
├── teleop/
│   └── keyboard_bimanual.py     # 双臂遥操作采集
└── scripts/
    ├── 01_test_load_robot.py
    ├── 02_test_bimanual_env.py
    ├── 03_teleop_bimanual.py
    └── 04_smoke_envhub.py
```

当前代码里已经有单臂抓取雏形，但要改成双臂时建议直接把接口重命名为 `bimanual`，避免后面右臂单臂逻辑混进数据集。

## 第三阶段：做 LeRobot/Gym wrapper

LeRobot 侧最稳的输入格式是：

```python
obs = {
    "pixels": {
        "front": np.ndarray(uint8, shape=(H, W, 3)),
        "wrist_left": np.ndarray(uint8, shape=(H, W, 3)),
        "wrist_right": np.ndarray(uint8, shape=(H, W, 3)),
    },
    "agent_pos": np.ndarray(float32, shape=(26,)),
}
action = np.ndarray(float32, shape=(26,))
```

LeRobot 会把它们转换成：

```text
pixels.front      -> observation.images.front
pixels.wrist_left -> observation.images.wrist_left
agent_pos         -> observation.state
action            -> action
```

注意：IsaacLab `DirectRLEnv` 往往返回 torch tensor，但 LeRobot 通用预处理更适合 numpy。建议 wrapper 负责：

- torch tensor 转 numpy
- 图像转 `uint8`
- 图像保持 HWC
- batch/vector env 维度处理
- IsaacLab action clipping
- `info["is_success"]` 统一输出，方便评估

## 第四阶段：先手动采集小数据集

第一版不要追求任务复杂，先采 20-50 条短 episode，验证数据链路。

推荐任务从简单到难：

1. 单物体双手靠近并夹持
2. 双臂把物体抬起
3. 双臂搬到目标区域
4. 加语言条件：`"Pick up the red block and place it in the green bin."`

数据集第一版建议：

```text
datasets/
└── s4_bimanual_pick_place_v0/
    ├── data/
    ├── meta/
    └── videos/
```

特征建议：

```text
fps = 20
observation.images.front:      uint8, (H, W, 3)
observation.images.wrist_left: uint8, (H, W, 3)   # 如果暂时没有腕部相机，可以先不加
observation.images.wrist_right:uint8, (H, W, 3)
observation.state:             float32, (26,)
action:                        float32, (26,)
task:                          string / task index
```

SmolVLA 可以吃语言任务，所以每条 episode 要有 task 文本。先统一一个任务文本也可以。

## 第五阶段：训练 SmolVLA

训练只在 `smolvla` 环境做。

建议优先使用当前 `lerobot/` 的官方 CLI，而不是 `lerobot-mujoco-tutorial/train_model.py`，因为教程脚本使用的是旧版 `lerobot.common.*` API，和当前仓库结构不完全一致。

训练配置方向：

```bash
conda activate smolvla
cd /home/zfy/smolVLA/lerobot

lerobot-train \
  --dataset.repo_id=/home/zfy/smolVLA/datasets/s4_bimanual_red_blue_plate_v0 \
  --policy.type=smolvla \
  --policy.path=lerobot/smolvla_base \
  --policy.chunk_size=10 \
  --policy.n_action_steps=10 \
  --output_dir=/home/zfy/smolVLA/outputs/s4_smolvla_bimanual_v0 \
  --batch_size=8 \
  --steps=20000
```

具体参数要以当前 LeRobot CLI 实际支持为准。开始时建议：

- `chunk_size=5` 或 `10`
- `n_action_steps=5` 或 `10`
- `batch_size=4/8/16` 根据显存调整
- 先训练到能 overfit 小数据集，再扩大数据

## 第六阶段：回到 IsaacLab rollout

训练后在 `env_isaaclab` 中加载 checkpoint 做闭环评估：

```text
IsaacLab reset
  -> wrapper 输出 LeRobot obs
  -> SmolVLA select_action
  -> control_mapping 映射到双臂/双手关节目标
  -> IsaacLab step
```

这里可能有两种做法：

1. 在 `env_isaaclab` 环境也安装最小 LeRobot + SmolVLA 推理依赖，直接仿真推理。
2. 训练环境起 inference server，IsaacLab 环境通过进程/HTTP/gRPC 请求 action。

第一版建议先用方案 1，简单直观；如果依赖冲突，再拆成 server。

## 推荐开始顺序

按下面顺序推进，每一步都应该有一个可运行脚本验证。

1. 修正当前文档和常量：38 DOF、单手 6 控制输入、右臂单臂 13 维、双臂双手 26 维。
2. 新建 `control_mapping.py`，统一动作/state 的名称、顺序、limits、手部映射接口。
3. 把当前单臂 `S4GraspingEnv` 改或复制成 `S4BimanualEnv`，先只返回 `agent_pos`，不急着加所有相机。
4. 加一个 LeRobot/Gym wrapper，确保 reset/step 返回 numpy 格式。
5. 写 `scripts/02_test_bimanual_env.py`：随机 26 维 action 可以跑 100 step。
6. 写 `scripts/03_teleop_bimanual.py`：键盘或 3D mouse 采集少量 episode。
7. 写数据集生成脚本，把 episode 保存为 LeRobotDataset。
8. 在 `smolvla` 环境训练小数据集，先检查 loss 能下降和 action 维度正确。
9. 回到 IsaacLab 做 rollout，观察动作尺度、频率、延迟和手部映射问题。
10. 再扩展任务复杂度、相机数量、数据量和语言条件。

## 当前实施任务：S4 双臂红蓝物块放盘子

本阶段目标是先在 IsaacSim/IsaacLab 中跑通仿真链路，暂不训练 SmolVLA。

任务定义：

- 桌面上有红色、蓝色两个物块和中间盘子/目标区。
- 左手抓红色物块并放到中间盘子里。
- 右手抓蓝色物块并放到中间盘子里。
- 两个物块都进入盘子区域后 episode 成功结束。
- 相机第一版只放一个胸前俯视相机，看清桌面、红蓝物块和盘子。

第一版控制策略：

- IsaacLab 中加载 S4 机器人，固定底座，腿部保持默认姿态。
- 双臂和双手都接入 action/state 接口。
- 暂时用脚本化 IK/轨迹控制生成演示数据，后续替换为 VR、键盘或真机采集。
- 先让控制链路、场景、相机、success 判断跑通，再处理高质量抓取物理和数据集保存。

重要修正：

- 早期版本默认启用了 scripted attach，把物块直接写到手腕附近。这会让物块和手一起在空中运动，看起来像“乱飞”，不适合作为物理仿真验证。
- 从当前版本开始，默认 `--mode stability` 不再把物块绑到手上。物块保持真实物理状态放在桌面上，双臂只移动到预抓取/盘子上方位置并执行手部开合。
- `--mode scripted_demo` 只用于后续验证数据链路或演示轨迹，不代表真实抓取物理成功。

O6 手部映射约束：

- 底层控制代码每只手存在 11 个 finger joints，命名概念为 `thumb_cmc_yaw, thumb_cmc_pitch, thumb_ip, index_mcp, index_dip, middle_mcp, middle_dip, ring_mcp, ring_dip, pinky_mcp, pinky_dip`。
- URDF 中实际 joint 名称是小写前缀：`lh_*` / `rh_*`。
- 当前 policy/action 接口保持每手 6 维主动控制：`thumb_cmc_yaw, thumb_cmc_pitch, index_mcp_pitch, middle_mcp_pitch, ring_mcp_pitch, pinky_mcp_pitch`。
- DIP/mimic 关节按 URDF mimic 或映射层处理，其中四指 DIP multiplier 为 `0.89`；thumb IP 在 URDF 中分别 mimic thumb pitch，左手 multiplier `2.29`，右手 multiplier `1.86`。
- 未来如果要对齐底层 DDS 的 7 维 `O6HandCommand`，需要在映射层增加兼容模式；当前先以 URDF 的 6 个主动关节为准。

本轮代码目标：

- 新增 `my_isaaclab_project/s4_robot/control_mapping.py`，统一 26 维双臂双手控制接口和手部 mimic 映射。
- 新增 `my_isaaclab_project/scripts/02_bimanual_plate_scene.py`，在 IsaacLab 中搭桌面、红蓝块、盘子、胸前相机和 S4 机器人，并用脚本化动作跑通双臂双手控制。
- 更新 `my_isaaclab_project/run.sh`，增加 `bimanual` 快捷入口。

本轮完成状态：

- 已新增 `my_isaaclab_project/s4_robot/control_mapping.py`。
- 已新增 `my_isaaclab_project/scripts/02_bimanual_plate_scene.py`。
- 已更新 `my_isaaclab_project/run.sh`，新增：

```bash
bash run.sh bimanual --steps 900
bash run.sh bimanual --headless --steps 900
```

实现细节：

- `control_mapping.py` 固定 26 维 action/state 顺序：
  - `[0:7]` 左臂 7 关节
  - `[7:13]` 左手 6 主动关节
  - `[13:20]` 右臂 7 关节
  - `[20:26]` 右手 6 主动关节
- 手部映射已参考底层 O6 控制代码：
  - 四指 DIP mimic multiplier `0.89`
  - 左拇指 IP mimic `lh_thumb_cmc_pitch * 2.29`
  - 右拇指 IP mimic `rh_thumb_cmc_pitch * 1.86`
- `02_bimanual_plate_scene.py` 目前是 smoke-test/demo 脚本，不是最终训练环境：
  - 用 IsaacLab `DifferentialIKController` 控制左右腕。
  - 用手部 6 维主动关节开合。
  - 默认 `--mode stability`：红/蓝物块保持物理自由，不随手腕移动。
  - 可选 `--mode scripted_demo`：红/蓝物块被脚本写位姿跟随手腕，仅用于数据链路实验。
  - 后续再替换为真实接触抓取、VR 采集、LeRobotDataset 保存。

场景更新：

- 已接入本地官方 Isaac Sim 资产根目录：

```text
/home/zfy/isaacsim_assets/Assets/Isaac/5.1/Isaac
```

- 本机完整资产包根目录实际是：

```text
/home/zfy/isaacsim_assets/Assets/Isaac/5.1
```

  其中包含 `Isaac/` 和 `NVIDIA/` 两个常用子目录。当前脚本使用 `/home/zfy/isaacsim_assets/Assets/Isaac/5.1/Isaac` 是为了加载 Isaac 官方示例环境、Props、Robots 等资产；这部分路径在本机存在，不应该走云端。只有 `--table willow_usd` 使用 `https://omniverse-content-production.../Willow.usd`，这个一定依赖网络或 Isaac Sim 缓存。后续如果接入 `NVIDIA/Assets` 或 `NVIDIA/Materials` 下的资产，应以 `/home/zfy/isaacsim_assets/Assets/Isaac/5.1` 为共同根目录。

- `02_bimanual_plate_scene.py` 支持官方背景：
  - `--scene qiling_scene`：默认，用户自建仓库+桌子场景，项目内路径 `/home/zfy/smolVLA/task_sence.usd`。
  - `--scene clean_room`：脚本生成的简单室内房间，只有地面和墙，不自带家具，保留为调试 fallback。
  - `--scene simple_room`：官方简单室内房间背景，可能自带家具，主要用于对比。
  - `--scene office`：办公室背景。
  - `--scene warehouse`：工业仓库背景。
  - `--scene warehouse_forklifts`：带叉车的仓库背景。
  - `--scene none`：只保留最小任务场景。
- 任务桌面支持多种官方视觉模型：
  - `--table none`：默认，不再生成额外桌子；用于 `qiling_scene` 这种已经包含桌子的场景。
  - `--table willow_table`：fallback，程序化生成的一张可见木质任务桌，带碰撞。
  - `--table willow_usd`：远程 Willow USD，URL 为 `https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/ArchVis/Commercial/Tables/Willow.usd`，仅用于后续单独调资产尺度/原点。
  - `--table room_low_table`：Simple Room 自带矮桌，更适合本地离线调试。
  - `--table textured_table`：通用带纹理任务台/实验台。
  - `--table mount_table`：Isaac Mounts 里的简单桌。
  - `--table thor_table`：更像工业安装台。
  - `--table packing_table`：工业/物流操作台。
  - `--table office_desk`：办公室桌子。
  - `--table lab_table`：实验室桌子。
  - `--table plain`：只用最小碰撞桌面。
- `--table willow_table` 不额外生成 `/World/TableCollision`，可见桌面本身承担碰撞；其它导入式 USD 桌子会搭配不可见 `/World/TableCollision`，用于稳定接触。当前默认 `--table none` 不生成任何额外桌面或碰撞面。
- 本轮根据实际观感反馈，把默认从 `office + packing_table` 改成 `simple_room + room_low_table`。原因是：第一阶段测试重点是双臂、手、物块和相机能不能稳定、清楚地工作，不需要一个太重或比例难对齐的复杂工业桌模型干扰判断。
- 历史记录：远程 Willow USD 虽然能进入加载流程，但可能因为 URL、原点、尺度或材质问题导致画面不可见；远程资产保留为 `--table willow_usd`，后续单独调试。
- 当前场景稳定基线：
  - 默认加载 `/home/zfy/smolVLA/task_sence.usd`，该 USD 已包含仓库和桌子。
  - `task_sence.usd` 没有设置 `defaultPrim`。不能用普通 `UsdFileCfg` 默认引用方式加载，否则会出现 `Unresolved reference prim path ... <defaultPrim>`，画面中没有场景。当前脚本对 `qiling_scene` 使用 USD API 显式引用 `task_sence.usd` 的 `</World>` 到 `/World/OfficialScene`。
  - 当前策略改为“使用保存好的任务 prim”：脚本不再额外生成 `/World/Robot`、`RedBlock`、`BlueBlock`、`Plate`。加载后直接绑定 `/World/OfficialScene/Robot`、`/World/OfficialScene/RedBlock`、`/World/OfficialScene/BlueBlock`、`/World/OfficialScene/Plate`。
  - 如果保存场景里存在 `/World/OfficialScene/ChestCamera`，脚本也会绑定该相机；否则只跳过 camera sensor。
  - 保存场景里的红蓝块/托盘可能保留了上次保存时的悬空位姿。当前脚本在每次 `sim.reset()` 后都会把 `RedBlock`、`BlueBlock`、`Plate` 写回任务初始位置，避免启动后物体悬浮。
  - 默认 `--table none`，不再额外生成 clean room、程序化桌子或隐藏碰撞桌。
  - 这解决了“画面里有两套机器人、物块、托盘”的问题；后续场景编辑时要确保保存的 USD 内只保留一套任务对象。
  - 任务物体高度由 `--table-top-z` 控制，默认 `0.725m`。如果新 USD 桌面高度不同，优先调这个参数，而不是改物块代码。
  - 历史外部路径 `/home/zfy/qiling_sence.usd` 已不再作为默认路径；后续以项目内 `task_sence.usd` 为准，方便版本管理和迁移。

数据集与训练准备：

- 已新增 `my_isaaclab_project/configs/s4_bimanual_dataset.json`，作为第一版数据集/训练配置源：
  - dataset root：`/home/zfy/smolVLA/datasets/s4_bimanual_red_blue_plate_v0`
  - fps：`20`
  - task 文本：`Use the left hand to put the red block into the tray and the right hand to put the blue block into the tray.`
  - `observation.state`：`float32[26]`
  - `action`：`float32[26]`
  - `observation.images.front`：`uint8[480, 640, 3]`
  - training output：`/home/zfy/smolVLA/outputs/s4_smolvla_bimanual_v0`
- 已新增 `my_isaaclab_project/scripts/04_check_dataset_setup.py`：
  - 检查 `task_sence.usd` 是否存在。
  - 检查 state/action 维度是否仍为 26。
  - 创建 dataset/output 目录。
  - 打印当前 26 维 action layout。
- 已新增快捷入口：

```bash
cd /home/zfy/smolVLA/my_isaaclab_project
bash run.sh check-dataset
```

数据集第一版策略：

- 第一阶段先不要直接训练，先录 20 条以内小样本 episode，验证 LeRobotDataset 能读、视频能看、state/action shape 正确。
- 采集来源按优先级推进：
  1. 现有 scripted IK 轨迹，用于验证数据链路，不作为最终高质量示教。`scripted_demo` 会在 attach 阶段运动学写物块位姿，看起来像物体悬浮/跟手走，这是预期行为，不代表真实抓取物理。
  2. 键盘/鼠标/3D 输入设备采集，用于快速调动作尺度和 episode 结构。
  3. VR 设备采集，用于正式双臂示教。
- 每条 episode 固定一个 task 文本；后续多任务再扩展 task vocabulary。
- 第一版只保存胸前/front 相机，腕部相机等系统稳定后再加。

训练准备：

- 本地 `lerobot/pyproject.toml` 确认训练 CLI 入口为 `lerobot-train`。
- 训练在 `smolvla` conda 环境中执行，不在 `env_isaaclab` 中训练。
- 第一版训练命令在数据集真正录制完成后再运行，方向如下：

```bash
conda activate smolvla
cd /home/zfy/smolVLA/lerobot

lerobot-train \
  --dataset.repo_id=/home/zfy/smolVLA/datasets/s4_bimanual_red_blue_plate_v0 \
  --policy.type=smolvla \
  --policy.path=lerobot/smolvla_base \
  --output_dir=/home/zfy/smolVLA/outputs/s4_smolvla_bimanual_v0 \
  --batch_size=8 \
  --steps=20000
```

- 上面参数名需要在正式训练前用当前 `lerobot-train --help` 最后确认；当前阶段先固定 dataset/action/image 规格和录制链路。

双臂抖动处理：

- 当前默认 IK 改成 `--ik-command-type position`，只控制左右腕位置，不再强制固定腕部姿态。原因是当前 smoke test 只需要手腕平稳靠近物体；过早锁定末端姿态可能让 7 轴手臂在奇异位形附近来回抖。
- 保留 `--ik-command-type pose` 作为后续真实抓取/姿态对齐测试选项。
- 默认每 `--ik-update-period=4` 个仿真步才重算一次 IK，其余时间保持上一帧 IK 解，减少每步解算噪声。
- phase 插值从线性改成 smoothstep，阶段起止速度更平滑。
- 降低默认隐式执行器 PD：`--joint-stiffness=45`，`--joint-damping=8`。
- 对 26 维控制目标增加更慢低通：`--target-alpha=0.08`。
- 对每步关节目标变化限幅：`--max-joint-step=0.012`。
- 这些参数用于先压住 IK 和高刚度位置控制带来的抖动。若手臂仍抖，优先继续降低 `--target-alpha`、`--max-joint-step` 或提高 `--ik-update-period`；若动作太慢，再逐步提高 `--target-alpha` 或 `--max-joint-step`。

当前脚本到底测试什么：

- 测试 S4 URDF 能否在 IsaacLab 中加载并保持稳定。
- 测试双臂 7+7 关节是否能通过 Differential IK 到达桌面附近目标。
- 测试 O6 手部 6+6 主动控制输入和 mimic 映射是否能稳定驱动手指开合。
- 测试红/蓝物块在桌面物理环境下是否稳定，不被机器人初始化或 IK 动作撞飞。
- 测试胸前相机/viewport 是否能看到桌面、两个物块、盘子和双手。
- 暂不测试真实抓取成功；真实抓取需要后续处理接触、摩擦、手部闭合策略、可能还要加 grasp helper 或更细致的 IK/轨迹。

验证记录：

- 已通过源码编译检查：

```bash
python -m py_compile my_isaaclab_project/s4_robot/control_mapping.py my_isaaclab_project/scripts/02_bimanual_plate_scene.py
bash -n my_isaaclab_project/run.sh
```

- 已通过纯 Python 映射检查：默认 action 为 `(26,)`，命名目标包含主动关节和 mimic 关节，能生成 full joint target。
- 在当前 Codex 执行沙箱中尝试启动 IsaacSim headless，已进入 `env_isaaclab` 并开始导入 URDF，但沙箱里 NVIDIA driver/GPU 不可见，日志出现 `No CUDA-capable device` / `GPU Foundation is not initialized`，随后进程卡住，已中断。因此完整 IsaacSim 运行需要在你的正常图形/GPU 会话中验证。

下一步优先级：

1. 在本机正常 IsaacSim/GPU 会话中运行：

```bash
cd /home/zfy/smolVLA/my_isaaclab_project
TERM=xterm bash run.sh bimanual --mode stability --steps 900
```

2. 如果要无界面验证：

```bash
cd /home/zfy/smolVLA/my_isaaclab_project
TERM=xterm bash run.sh bimanual --headless --mode stability --steps 900
```

如果新场景桌面高度和默认不同，运行时调：

```bash
TERM=xterm bash run.sh bimanual --mode stability --table-top-z 0.75 --steps 900
```

3. 如果要看工业背景：

```bash
TERM=xterm bash run.sh bimanual --mode stability --scene warehouse_forklifts --table thor_table --steps 900
```

4. 如果想看实验台/通用任务台：

```bash
TERM=xterm bash run.sh bimanual --mode stability --scene simple_room --table textured_table --steps 900
```

后续工作从当前稳定场景开始，不再继续堆 smoke-test 脚本。下一阶段要把能力拆成可复用模块：

- `tasks/bimanual_plate_task.py`：任务几何、物体位置、success 判断、reset 参数。
- `s4_robot/bimanual_controller.py`：IK 控制、手部开合、26 维 action/state 接口。
- `s4_robot/s4_bimanual_env.py`：IsaacLab/Gym 风格 reset/step/render。
- `scripts/03_record_bimanual_dataset.py`：先用脚本/键盘采集 LeRobotDataset 小样本，后续替换 VR。

5. 如果想看办公室桌子：

```bash
TERM=xterm bash run.sh bimanual --mode stability --scene office --table office_desk --steps 900
```

6. 如果手臂仍抖，优先测试更慢、更软的控制：

```bash
TERM=xterm bash run.sh bimanual --mode stability --scene simple_room --table room_low_table --joint-stiffness 35 --joint-damping 7 --target-alpha 0.05 --max-joint-step 0.008 --ik-update-period 6 --steps 900
```

7. 如果要确认是否是 position-only IK 带来的姿态问题，可单独测试 pose IK：

```bash
TERM=xterm bash run.sh bimanual --mode stability --scene simple_room --table room_low_table --ik-command-type pose --target-alpha 0.05 --max-joint-step 0.008 --steps 900
```

8. 只有当需要调试数据链路、暂时不关心真实接触抓取时，才运行：

```bash
TERM=xterm bash run.sh bimanual --mode scripted_demo --scene simple_room --steps 900
```

9. 根据首次真实运行报错修 IsaacLab API/机器人导入细节。
10. 运行稳定后，把该脚本拆成可复用的 scene/controller/env 三层，再接 LeRobotDataset 录制。

## 近期不要做的事

- 不要一开始训练全身 38 维动作；腿部先固定。
- 不要把 MuJoCo 环境代码迁移到 IsaacLab；只迁移数据接口和流程。
- 不要让 SmolVLA 输出 IsaacLab 全物理关节，尤其是手部 mimic/从动关节。
- 不要在数据格式未稳定时大量采集数据，否则后面重采成本很高。
- 不要先追求复杂任务奖励，模仿学习第一步更依赖稳定遥操作数据。

## 当前已知风险点

- 当前 `my_isaaclab_project` 里单臂环境的动作维度有不一致：代码分组是 13 维，但环境配置写过 14 维。
- README 中仍有 40 DOF/手 7 DOF 的旧描述，实际主动控制应按 38 DOF、单手 6 控制输入处理。
- IsaacLab namespace 需要统一：部分代码用 `isaaclab.*`，部分代码用 `omni.isaac.lab.*`。
- Camera 需要确认使用 IsaacLab sensor，而不是普通 `AssetBaseCfg`，否则不一定有 `.data.output["rgb"]`。
- LeRobot wrapper 需要把 IsaacLab 的 torch tensor 输出转换为 numpy/uint8/HWC。
