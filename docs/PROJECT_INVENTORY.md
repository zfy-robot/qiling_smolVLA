# S4 SmolVLA 项目清单与职责边界

本文描述 v0.1.1 当前实现，不是迁移计划。不可变版本、digest 和验证结果以
`release/manifest.yaml` 为准，持续进度以 `PROJECT_STATUS.md` 为准。

## 发布物

| 载体 | 内容 | 版本依据 |
|---|---|---|
| GitHub `zfy-robot/qiling_smolVLA` | 项目源码、配置、文档、Docker/Compose、lock、manifest | Git tag/commit |
| Git submodule `IsaacLab` | IsaacLab 2.3.2 兼容源码分支 | 固定 commit |
| Git submodule `lerobot` | LeRobot/SmolVLA 源码 | 固定 commit |
| GHCR `sim` | Isaac Sim/IsaacLab 与仿真运行环境 | OCI digest |
| GHCR `policy` | LeRobot/SmolVLA 训练和推理环境 | OCI digest |
| GHCR `robot` | ROS 2/qi/Pink/QP/RealSense 环境 | OCI digest |
| ModelScope `zfy2qiling/qiling_smolvla` | 基础模型、数据集、选定 checkpoint、机器人/项目场景资产 | 固定 revision + tree SHA256 |
| NVIDIA 官方源 | Isaac 5.1 最小资产闭包、两个 Kit extensions | URL/大小/SHA256 lock |
| 部署主机 `.s4/` | 下载缓存、输出、训练/采集结果 | 本地备份策略 |

项目不再维护旧单体 full 镜像。不存在把代码、数据、模型、资产和两个环境一起 bake 的正式
入口；旧 Dockerfile、Compose、build/run 脚本已经删除。

## 运行环境

### sim

- Python 3.11、Isaac Sim 5.1.0.0、IsaacLab fork、PyTorch 2.7.0+cu128；
- 负责 Isaac 场景、仿真采集、相机、物理和仿真 rollout；
- 当前仿真 rollout 在同一容器中用独立 `smolvla` Python 子进程做推理，因此 sim 镜像含两个
  隔离的 Conda 环境；这不是旧单体发布物，镜像仍不含项目代码和制品；
- 需要 NVIDIA RTX、Vulkan、NVIDIA Container Toolkit。

### policy

- Python 3.12、PyTorch、LeRobot/SmolVLA、Transformers、Accelerate、PyAV；
- 负责仿真/真机数据转换、训练、离线推理，以及真机 LAN policy server；
- 不包含 Isaac Sim、ROS、数据集或 checkpoint；
- 训练和在线推理需要 NVIDIA GPU，纯转换可使用 CPU。

### robot

- Ubuntu 22.04、ROS 2 Humble、系统 Python 3.10、qi messages、Pink/QP、RealSense；
- 负责 Quest 遥操、真机采集、ROS/DDS feedback、shadow/live client；
- 不包含 Torch、LeRobot、Isaac Sim 或模型；通常部署在连接机器人和相机的边缘电脑；
- `verify robot` 为无动作检查，不创建 publisher。

## 两条业务链路

### 仿真

```text
Isaac 场景/机器人资产 + task contract
  -> 脚本专家或遥操采集 HDF5
  -> policy 环境转换 LeRobotDataset
  -> policy 环境训练
  -> 350K 发布 checkpoint
  -> sim 环境固定/随机 rollout
  -> video + actions.csv + diagnostics + summary.json
```

主要入口在 `s4_smolvla_isaaclab/run.sh`，容器用户通过根目录 `./s4` 调用。仿真数据契约为
`s4_bimanual_v1`，state/action 均 26D，数据 20Hz、控制 120Hz。

### 真机

```text
Quest + RealSense + ROS2/DDS feedback
  -> robot 环境遥操/采集 raw episode
  -> policy 环境转换 LeRobotDataset
  -> policy 环境训练
  -> GPU 服务器 policy-server（300K）
  -> robot 环境 shadow/live client
```

真机发布契约为 8D state/action。推荐机器人电脑运行 `robot`，GPU 服务器运行 `policy-server`，
通过可信隔离局域网 TCP 5555 通信。同机部署使用 `127.0.0.1`。协议目前没有认证/加密，禁止暴露
公网。

## 文件结构

```text
compose.yaml                       # 唯一 Compose 文件
s4                                 # 对外环境/制品/验证入口
docker/
  artifacts/Dockerfile
  sim/Dockerfile
  policy/Dockerfile
  robot/Dockerfile
release/
  manifest.yaml                    # v0.1.1 唯一映射
  artifacts.yaml                   # ModelScope 下载集合
  isaac_assets_5.1.lock.json
  isaac_extensions_5.1.lock.json
scripts/release/                    # 下载、校验、发布工具
s4_smolvla_isaaclab/               # 业务代码
IsaacLab/                           # submodule
lerobot/                            # submodule
.s4/                               # 本地制品/输出/缓存，不进 Git
```

## 大文件与写入位置

- `.s4/artifacts/`：从 ModelScope 下载，只读挂载给运行容器；
- `.s4/outputs/`：采集、转换、训练和评估输出；
- `.s4/cache/`：Kit、XDG、模型和运行缓存；
- `.s4/isaac-assets/5.1/`：用户从 NVIDIA 官方取得的资产，不再分发；
- `training_state/`：仅用于内部续训，不属于 v0.1.1 教程发布；
- `.env`、`ros_env.sh`、`cameras.yaml`：部署机器专用，不进 Git。

所有 runtime 数据使用 bind mount；不再用 Docker named volume 初始化或隐藏数据。

## 硬件边界

镜像负责 Ubuntu user space、Python、CUDA/Isaac/PyTorch 用户态库和 Vulkan loader。宿主负责
Linux 内核、NVIDIA 内核驱动、驱动实现库、GPU/USB/网卡设备、Docker 和 NVIDIA Container
Toolkit。主机驱动不会进入镜像。

公开支持线：Linux x86_64、Ubuntu 22.04 推荐、NVIDIA driver 580.65.06+、sim 最低建议
16GB VRAM、32GB RAM；已在 RTX 4090 24GB、driver 580.159.03 验证。其他设备尚未验收，不能
从本机成功推断为自动兼容。

## v0.1.1 验证边界

本机已完成三个镜像的构建、CUDA/Vulkan/Isaac RGB、严格离线仿真 episode、policy 单步训练、
真机 300K 离线/ZMQ 协议，以及 robot 无硬件 ROS/Pink/QP 检查。三个 GHCR 镜像均公开并通过
匿名 digest 验证。

暂缓项：其他物理设备复现，以及连接实体机器人后的相机、feedback、shadow、5 秒低风险动作。
这些结果将进入后续兼容性矩阵，不伪装成 v0.1.1 已完成项。
