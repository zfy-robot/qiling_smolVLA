# S4 SmolVLA 项目资产、环境与发布审计

> 审计基线：2026-09-09，Git commit
> `589d5d3f38081eb6fb39375482b948d881176106`。本文记录事实和迁移边界；旧的
> `docker/Dockerfile`、`docker/compose.yaml` 在模块化镜像验证完成前保留为 legacy
> 回退，不再作为新的公开发布方案。

## 1. 一句话结论

项目应按四类对象管理，不能再把它们做成一个发布物：

1. GitHub 管代码、配置、补丁、文档和不可变版本清单；
2. OCI Registry（建议 GHCR）管三个环境镜像；
3. ModelScope 管基础模型、数据集、场景资产和被选中的 checkpoint；
4. 宿主机数据目录管缓存、采集中的数据、训练过程和评估日志。

环境镜像不得包含 NVIDIA 内核驱动，也不得包含项目数据。GPU 设备、内核模块、
`libcuda`、NVML、EGL/OpenGL/Vulkan 驱动由宿主机和 NVIDIA Container Toolkit 注入。

## 2. 当前代码和两条链路

### 2.1 仿真链路

```text
任务 YAML/JSON + 机器人 USD/URDF/mesh + Isaac 场景资源
  -> Isaac Sim 5.1.0.0 二进制 Python 包
  -> IsaacLab 2.3.2 源码（Python package 0.54.2）
  -> 专家策略采集 HDF5
  -> smolvla 环境转换为 LeRobotDataset
  -> smolvla 环境训练
  -> policy checkpoint
  -> Policy Server + IsaacLab simulator rollout
  -> 视频、动作 CSV、诊断图和 summary
```

入口和模块：

| 目录/文件 | 职责 | 环境 |
|---|---|---|
| `s4_smolvla_isaaclab/run.sh` | 当前统一命令路由 | 按命令切换 |
| `configs/tasks/` | task、数据、语言、训练契约 | 通用 |
| `tasks/` | 场景、专家控制器、任务加载 | sim |
| `s4_robot/` | 机器人配置、关节映射、仿真控制 | sim |
| `s4_pipeline/` | 契约、随机化、失败重试、rollout 指标 | sim/policy |
| `scripts/record_dataset.py` | Isaac 专家采集 | sim |
| `scripts/convert_lerobot.py` | HDF5 -> LeRobotDataset | policy |
| `scripts/train_smolvla_local.sh` | 单卡/Accelerate DDP 训练 | policy |
| `scripts/policy_server.py` | 仿真 rollout 的 stdio policy 子进程 | policy |
| `scripts/eval_policy.py` | Isaac rollout 主进程 | sim |
| `teleoperation/` | Quest 仿真遥操；内含 Pink 源码 | sim |

当前仿真 rollout 通过 stdio 在同一容器启动 `smolvla` Python，因此 legacy 镜像必须同时
包含两个 Conda 环境。彻底拆分前，需要把它迁移到与真机一致的网络 Policy Server 协议。

### 2.2 真机链路

```text
Quest + RealSense + ROS2/DDS + SDK feedback
  -> Python 3.10 机器人端遥操/采集
  -> raw episode
  -> Python 3.12 host 转换为 LeRobotDataset
  -> Python 3.12 host 训练
  -> LAN Policy Server
  -> Python 3.10 robot shadow/live rollout
```

| 目录 | 职责 | 环境 |
|---|---|---|
| `hardware_teleop/` | Pink IK、ROS bridge、qi messages、真机安全门禁 | robot |
| `real_vla/` | 真机遥操采集、相机、raw episode 校验 | robot |
| `real_vla_stack/common/` | 协议、配置、contract hash；禁止依赖 Torch/ROS | 通用 |
| `real_vla_stack/host/` | 转换、训练、checkpoint、Policy Server | policy |
| `real_vla_stack/robot/` | observation、网络客户端、安全执行 | robot |

真机训练不依赖 Isaac Sim。它与仿真训练共用 `smolvla`/policy 环境，但数据契约分别是
26D 双臂仿真契约和 8D 单臂真机契约，不能混用 checkpoint。

推荐部署拓扑是两台主机、两个职责隔离的容器：

```text
机器人控制电脑 / 边缘电脑                     GPU 训练/推理服务器
robot image                                  policy image
ROS2/DDS + qi + RealSense + Quest            CUDA + LeRobot + 300K checkpoint
30Hz 安全控制 + ZMQ client    <--- LAN --->  ZMQ policy-server:5555
```

`robot` 镜像部署在物理连接真机、相机并能访问机器人 DDS 网络的电脑上，不需要 NVIDIA GPU；
`policy-server` 部署在具有 NVIDIA GPU 的服务器上，不直接访问 USB、ROS 或执行器。同机部署也
支持，此时两个容器使用 host network，`S4_POLICY_SERVER_HOST=127.0.0.1`。跨机部署必须把该值
改为 GPU 服务器的固定内网地址，并配置防火墙只允许机器人控制电脑访问 TCP 5555。

## 3. 必须固定的源码

| 源码 | 当前版本 | 新管理方式 |
|---|---|---|
| 本项目 | `589d5d3f...`，branch `main` | GitHub tag + commit |
| LeRobot | `3f2179f3...`，报告版本 0.6.1 | 保留 Git submodule |
| IsaacLab | upstream commit `37ddf626...`，repo VERSION 2.3.2 | Git submodule/构建时 checkout + 项目补丁 |
| Pink | `teleoperation/pink/` vendored 源码 | 固定 commit 来源和 LICENSE/NOTICE |
| qi ROS messages | `hardware_teleop/ros_ws/src/qi` | GitHub 源码；镜像内编译 |

`IsaacLab/` 已改为 Git submodule，固定到公开仓库
`zfy-robot/IsaacLab@f764c12a5ccf5cc6997de699653b4bb70e56a3f7`，分支为
`s4/isaaclab-2.3.2-isaacsim-5.1`。与 upstream 的兼容修改同时保留在
`patches/isaaclab/` 供审计；sim 镜像只安装这个固定源码，不再复制维护者机器上的 dirty
checkout 或无关 RL project。

## 4. 三个运行环境

### 4.1 `sim` 镜像

- OS user space：Ubuntu 22.04 x86_64；
- Python 3.11；
- Isaac Sim `5.1.0.0`，当前通过 `isaacsim[all,extscache]==5.1.0` 安装；
- IsaacLab upstream `37ddf626...` + 明确 patch；
- PyTorch `2.7.0+cu128`；
- NumPy 1.26、h5py 3.16、OpenCV 4.11、Pin/Pink；
- EGL/Vulkan loader，但不包含宿主 NVIDIA 图形驱动。

环境已从干净 Docker stage 重建，并完成 CUDA、Isaac import、Vulkan、Camera、官方资产
闭包、Kit extension 严格离线启动及完整 rollout 验证。依赖版本来自 Dockerfile 和 Conda
environment 文件，不使用受 ROS/PYTHONPATH 污染的宿主 `pip freeze`。

### 4.2 `policy` 镜像

- Ubuntu 22.04 x86_64；
- Python 3.12；
- PyTorch/TorchVision/TorchAudio `2.7.0+cu128/0.22.0+cu128/2.7.0+cu128`；
- LeRobot `3f2179f3...`；
- Transformers 5.5.4、Accelerate 1.14.0、Datasets 5.0.0；
- NumPy 2.2.6、PyArrow 25.0.0、pandas 3.0.5、PyAV 15.1.0；
- OpenCV headless 4.13、ZeroMQ 27.0.2、msgpack 1.1.2。

当前镜像内约 8.1GB，`pip check` 通过。转换可用 CPU；训练和 CUDA Policy Server 需要
NVIDIA GPU。新的 policy lock 应从已验证镜像导出，而不是从受 ROS/PYTHONPATH 污染的宿主
环境导出。

### 4.3 `robot` 镜像

- Ubuntu 22.04 x86_64；
- ROS2 Humble 与系统 Python 3.10 ABI；
- CycloneDDS/RMW、`rclpy`、项目内 qi messages；
- ROS Pinocchio 4.0.0（当前固定基础镜像和 apt 构建实测版本）；
- SciPy 1.15.2、qpsolvers 4.12.0、DAQP 0.8.7、quadprog 0.1.13；
- OpenCV headless 4.11、ZeroMQ 27.0.2、msgpack 1.1.2；
- librealsense/pyrealsense2；
- 不安装 Torch、LeRobot、Isaac Sim。

robot 发布镜像已设置 `PYTHONNOUSERSITE=1`，项目 Python 依赖隔离在
`/opt/s4/hardware_python`，ROS/Pinocchio 来自固定的 Humble 基础镜像，qi messages 在镜像内
构建。无硬件验证已覆盖 ROS、CycloneDDS、RealSense SDK、Pink/QP、FK 和配置加载，并确认不
创建 publisher；物理相机、feedback、shadow 和 live motion 仍只能在连接真机后验收。

## 5. 系统与驱动边界

### 5.1 镜像负责

- Ubuntu user space、glibc、Python；
- CUDA user-space runtime、cuDNN/NCCL（由 PyTorch/Isaac 包或明确系统包提供）；
- Isaac Sim 二进制包、IsaacLab 源码；
- Vulkan loader 和 ICD 配置文件；
- Python/ROS 应用依赖。

### 5.2 宿主机负责，禁止 bake 进镜像

- Linux 内核；
- NVIDIA 内核模块；
- 物理 GPU 和 `/dev/nvidia*`、`/dev/dri/renderD*`；
- NVIDIA driver 的 `libcuda`、NVML、EGL/OpenGL/Vulkan 实现；
- Docker Engine、Compose、NVIDIA Container Toolkit；
- 真机 USB、网卡、时钟同步、SDK 服务和急停。

当前项目没有复制真实宿主驱动文件，但 CUDA 基础镜像包含
`/usr/local/cuda-12.8/compat/libcuda.so.570.124.06`。它是 CUDA forward-compat user-space
库，不是内核驱动；为了让边界完全明确，新镜像改用固定 digest 的 Ubuntu/ROS 基座，并由
PyTorch/Isaac 包提供所需 CUDA user-space 库，不安装 `cuda-compat-*`。

### 5.3 对外支持矩阵

仿真/训练主机公开支持条件建议固定为：

| 项目 | 最低支持线 | 推荐/已验证线 |
|---|---|---|
| 架构 | Linux x86_64 | Ubuntu 22.04 |
| GPU | NVIDIA RTX、具有 RT Core | RTX 4090 24GB 或更高 |
| Driver | 发布时按 Isaac Sim 官方测试线门禁 | 新公开版采用 Linux 580.65.06+ |
| RAM | 32GB | 64GB+ |
| VRAM | 16GB | 24GB+；batch 按显存调整 |
| 磁盘 | 仅 rollout 约 80GB 可用 | 训练建议 200GB+ NVMe |
| 容器 | Docker + Compose plugin | 每个 release 记录实测版本 |
| GPU runtime | NVIDIA Container Toolkit | 1.19.1 已记录，允许更新 patch 后回归 |

CUDA 12.8 GA 本身的 Linux driver 下限是 570.26，但这不代表 Isaac 的 Vulkan/RTX 渲染也
通过。Isaac Sim 5.1 当前官方要求页列出的 Linux 测试 driver 是 580.65.06，因此公开支持
矩阵采用更严格值。项目历史上在 570.190/580.159.03 成功，仅记为 legacy 已验证组合，不把
它们扩展为对所有机器的保证。

Isaac Sim 5.1 已进入不再维护状态。当前项目先冻结 5.1，不在容器化过程中同时升级；未来将
Isaac 升级作为独立项目，必须重新验证 USD、URDF importer、相机、物理和 rollout。

## 6. 大文件现状与目标归属

### 6.1 当前工作区

| 类别 | 大小 | 处理方式 |
|---|---:|---|
| `models/` | 8.3GB | ModelScope；不进镜像/Git |
| 其中 SmolVLM2 `onnx/` | 5.5GB | 当前代码未使用，不进 runtime bundle |
| 仿真 LeRobotDataset | 2.2GB | ModelScope dataset repo |
| 仿真 train outputs | 5.0GB | 本地；只发布被选 checkpoint |
| 仿真 eval outputs | 966MB | 本地/可选 demo，不进 runtime bundle |
| Isaac 场景子集 | 501MB | 许可确认后 ModelScope asset repo |
| Git 中机器人/场景资产 | 103MB | 所有权确认；必要时移到 asset repo |
| Docker vendored Kit extensions | 194MB | 许可确认/可重建性处理，不进代码仓库 |
| IsaacLab 构建快照 | 437MB | 删除快照方式，改 upstream commit + patch |
| 其中 IsaacLab logs | 244MB | 生成物，不发布 |

当前 full 镜像在本机 `docker image ls` 显示约 85.2GB，主要层包括：

- Isaac Sim pip layer 约 17.2GB；
- sim Conda 基础约 2.22GB；
- IsaacLab install 约 6.69GB；
- policy 环境约 8.57GB；
- 整个项目资源 copy 约 17.3GB。

### 6.2 当前 ModelScope 状态

正式公共 dataset repo 是 `zfy2qiling/qiling_smolvla`，不可变 revision 为
`3686874898fdf908431db487468f21a527507988`。其中包含六组模型/数据制品和两组项目资产；
NVIDIA 资产与 Kit extension 明确排除。上传报告为 165 个文件、失败数 0，下载端按用途通过
`allow_patterns` 选择子集并校验 SHA256。

### 6.3 外部真机数据

| 路径 | 大小 | 建议 |
|---|---:|---|
| `${S4_RAW_ROOT}` | 818MB（盘点时） | 原始数据，本地归档；不作为教程依赖 |
| `${S4_REAL_DATASET_SOURCE}` | 858MB（盘点时） | 已选择并发布的真机 dataset 来源 |
| `${S4_OUTPUT_ROOT}` | 34GB（盘点时） | 训练过程输出，不整体上传 |
| 真机 300k deploy checkpoint | 865MB | 正式 model repo 候选 |
| 对应 training state | 394MB | 仅内部 resume bundle |

真机 300k checkpoint 记录的 contract SHA256 为
`792de8a5373a1eb284febeaade03b9ae21adf880065ab13d8281d966bda90f68`，训练代码 commit
为 `eb930b2ca1ca62996c0e446d1733137f4954714f`，该 commit 是当前 HEAD 的祖先。

## 7. ModelScope 正式仓库规划

项目所有者决定用单一公开 dataset repo `zfy2qiling/qiling_smolvla` 管理八组制品，通过稳定
目录和 `allow_patterns` 实现按需下载：

| 目录 | 内容 |
|---|---|
| `models/HuggingFaceTB/SmolVLM2-500M-Video-Instruct/` | VLM runtime，排除 ONNX |
| `models/lerobot/smolvla_base/` | SmolVLA base runtime |
| `datasets/lerobot_data/s4_drawer_insert_close_v4_12phase_serial_acquire/` | 仿真数据集 |
| `policies/sim/drawer_insert_close_v4/350000/pretrained_model/` | 仿真 350K 部署策略 |
| `datasets/lerobot_data/s4_real_drawer_right_v1/` | 真机数据集 |
| `policies/real/drawer_right_v1/300000/pretrained_model/` | 真机 300K 部署策略 |
| `assets/my_robot/` | S4 机器人 URDF/mesh 和 LinkerHand O6 资源 |
| `assets/scenes/` | 项目场景资源 |

仓库根目录包含 README、Apache-2.0、NOTICE、artifact manifest 和 `SHA256SUMS`。上传完成后，
部署配置必须固定到不可变 ModelScope revision，不使用 `master` 作为正式 release 身份。

2026-09-09 已通过 ModelScope CLI 确认仓库为 `public`。NVIDIA Isaac 场景资产不在公共制品
内，由用户从 NVIDIA 官方源取得；项目机器人和场景资源则作为独立目录发布。

## 8. 不应上传的内容

- 任意 Conda environment 目录；
- Docker build cache、Isaac logs、Kit cache；
- 全部 `outputs/`；
- 全部历史 optimizer state；
- `.env`、ModelScope/GitHub token、证书私钥；
- ROS `build/ install/ log/`；
- SmolVLM2 未使用的 ONNX 导出；
- 未审查隐私的真机原始视频；
- 未确认再分发权的 NVIDIA 场景资产、Kit extension 或机器人 CAD。

## 9. GitHub 发布前阻塞项

已解决：Apache-2.0 `LICENSE/NOTICE`、IsaacLab/LeRobot submodule、ModelScope 制品边界、
NVIDIA 不再分发策略、固定 CUDA/ROS 基础镜像、三个环境镜像和运行时验证、公开配置模板。

正式发布仍需：

1. 从 Git 当前版本取消跟踪 `docker/runtime/eval/` 的旧评估文件；
2. 从 Git 当前版本取消跟踪真实 `ros_env.sh` 和 `cameras.yaml`，仅保留 example；
3. 完成 CI 的 clean-tree、submodule、Compose、manifest 和大文件门禁；
4. 记录最终 sim/policy/robot digest，并在干净 clone 上复现教程；
5. 连接真机后完成人工安全门禁下的相机、feedback、shadow 和受控 live 验收。

## 10. 目标仓库结构

```text
smolVLA/
├── compose.yaml
├── compose.sim.yaml
├── compose.policy.yaml
├── compose.robot.yaml
├── docker/
│   ├── sim/Dockerfile
│   ├── policy/Dockerfile
│   ├── robot/Dockerfile
│   └── legacy/                 # 验证迁移完成后再移入旧 full 方案
├── patches/isaaclab/
├── release/
│   ├── manifest.example.yaml
│   └── README.md
├── scripts/release/            # sync、verify、bundle、preflight
├── s4                          # 对外唯一入口
├── s4_smolvla_isaaclab/        # 项目源码
└── lerobot/                    # pinned submodule
```

宿主数据默认统一在仓库外或 `.s4/` 下：

```text
S4_STORAGE_ROOT/
├── assets/
├── models/
├── datasets/sim/
├── datasets/real/
├── checkpoints/sim/
├── checkpoints/real/
├── outputs/
├── cache/
└── secrets/
```

Compose 对 models、发布 dataset/checkpoint 默认只读挂载；只有采集目录、训练输出、评估输出
和 cache 可写。使用 bind mount，避免数据隐藏在难备份的 Docker named volume 中。

## 11. 实施顺序

### 阶段 A：冻结和上传（需要项目所有者参与）

1. 确认项目发布名称、GitHub 可见性和项目 LICENSE；
2. 创建第 7 节的 ModelScope 仓库；
3. 选择仿真正式 checkpoint（当前文档验证较完整的是 350k；本地 latest 是 450k，需先
   rollout 后才能晋级）；
4. 确认真机正式 checkpoint 是否就是 300k；
5. 对 NVIDIA assets、Kit extensions、机器人 CAD 做许可确认；
6. 对真机 dataset/raw video 做隐私确认；
7. 上传批准的制品并把每个 revision 返回给维护脚本；
8. 给当前 Git commit 打一个 legacy baseline tag，保留现有 full 镜像 digest。

### 阶段 B：先减重，不改业务协议

1. 新建 combined-env legacy-compatible 镜像，但排除 models/datasets/outputs/assets；
2. 改用 bind mounts 和 ModelScope sync；
3. 清理 IsaacLab snapshot，只安装所需源码 package；
4. 修复 sim 依赖直到 `pip check` 和当前 full profile 都通过；
5. 形成第一个不可变 release manifest。

### 阶段 C：拆 sim 和 policy

1. 建立独立 policy 镜像并验证 convert/train/serve；
2. 复用 `real_vla_stack` 的契约和 ZeroMQ session 设计，为仿真提供网络 policy client；
3. 仿真 rollout 不再寻找另一个 Conda prefix；
4. 建立独立 sim 镜像并验证 scene/record/camera/rollout；
5. 对比迁移前后的固定种子 observation、动作和 rollout 指标。

### 阶段 D：真机容器

1. 从 ROS Humble Jammy 固定 digest 基座构建 robot 镜像；
2. 镜像内编译 qi messages；
3. 禁用用户 site，锁定 Pinocchio/QP/RealSense 来源；
4. Compose 只映射需要的 USB device、video/dialout group 和 host network，不默认
   `privileged: true`；
5. 依次通过 import doctor、camera、ROS feedback、policy network、shadow、5 秒 live；
6. live 验证必须有人工急停和现场清场，不由 CI 自动执行。

### 阶段 E：公开发布

1. GitHub Actions 做静态测试、CPU 单测、镜像构建、SBOM 和 provenance；
2. GPU/Isaac 构建和测试使用受控 self-hosted runner；
3. 镜像推送 GHCR，tag 同时包含语义版本和 Git SHA，部署使用 digest；
4. 发布页只暴露 `./s4 setup`、`./s4 doctor`、`./s4 sim ...`、`./s4 train ...`、
   `./s4 real ...`；
5. 新机器必须先通过 host preflight，再允许下载大制品或启动训练。

## 12. 每次 release 的硬门禁

- Git 和 submodule clean，所有 commit 与 manifest 一致；
- image base、最终 image 都有 digest；
- `pip check` 为零错误；
- `PYTHONNOUSERSITE=1`，import 路径全部在容器或 `/opt/ros/humble`；
- 没有 `/home/<user>`、固定 IP、token、私钥进入公开 artifact；
- ModelScope revision 和 SHA256 校验通过；
- dataset contract == checkpoint contract；
- policy：CPU import、CUDA、单步训练、DDP smoke；
- sim：Vulkan NVIDIA renderer、Isaac headless、Camera RGB、固定 rollout；
- robot：无运动 preflight 和 shadow；live 仅人工验收；
- 输出 SBOM、build provenance、支持矩阵和已知限制。
