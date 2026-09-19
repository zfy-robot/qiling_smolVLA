# Docker 环境架构

本项目只维护模块化 Docker 方案。旧的单体 full 镜像已经退役，其 Dockerfile、Compose 和运行
脚本均已删除，不再构建、发布或提供兼容入口。

## 环境职责

| 服务 | Dockerfile | 内容 | 不包含 |
|---|---|---|---|
| `sim` | `docker/sim/Dockerfile` | Isaac Sim 5.1、IsaacLab、仿真与本地 policy 推理环境 | 源码、模型、数据、项目/NVIDIA 资产、宿主驱动 |
| `policy` | `docker/policy/Dockerfile` | PyTorch、LeRobot/SmolVLA、训练和 policy server | 源码、模型、数据、ROS、宿主驱动 |
| `robot` | `docker/robot/Dockerfile` | ROS 2 Humble、qi、Pink/QP、RealSense | Torch、Isaac Sim、模型、宿主设备配置 |
| `artifacts` | `docker/artifacts/Dockerfile` | ModelScope 下载和 SHA256 校验工具 | 运行环境和发布制品 |

根目录 `compose.yaml` 是唯一 Compose 文件，根目录 `./s4` 是唯一面向用户的环境入口。
环境镜像可从固定 digest 拉取，也可由维护者从 Dockerfile 重建：

```bash
./s4 pull sim       # 也可选择 policy、robot 或 all
./s4 build sim      # 也可选择 artifacts、policy、robot 或 all
```

普通用户优先使用 `pull`；修改依赖或制作下一版本时才使用 `build`。正式镜像身份记录在
`release/manifest.yaml`，不使用 `latest`。

## 挂载边界

- 仓库源码只读挂载到 `/workspace/smolVLA`；
- ModelScope 制品下载到宿主 `.s4/artifacts/`，只读挂载到 `/artifacts`；
- 评估、训练和采集输出写到宿主 `.s4/outputs/`；
- 缓存写到宿主 `.s4/cache/`；
- NVIDIA Isaac 资产从官方来源取得，位于 `.s4/isaac-assets/5.1/`；
- `.env`、相机序列号、ROS/DDS 网卡和现场配置只保留在部署机器。

不再使用 Docker named volume 隐藏数据，也不从镜像初始化数据集/checkpoint。删除容器不会删除
宿主制品和输出；是否删除 `.s4/` 由用户自行决定。

## 驱动和硬件边界

镜像只提供 CUDA/Isaac/PyTorch 用户态依赖。Linux 内核、NVIDIA 内核驱动、`/dev/nvidia*`、
`/dev/dri/*` 和驱动实现库由宿主与 NVIDIA Container Toolkit 在运行时注入，绝不 bake 进镜像。

仿真/训练宿主先执行：

```bash
./s4 preflight
```

当前公开支持线与已验证硬件记录在 `release/manifest.yaml`。真机端不要求 NVIDIA GPU，但要求
ROS/DDS 网络、RealSense USB 和安全急停满足现场门禁。

## 获取运行制品

```bash
./s4 build artifacts
./s4 setup sim_rollout
./s4 setup sim_training
./s4 setup real_full
./s4 setup tutorial_all
```

下载固定到 ModelScope 不可变 revision 并逐文件校验。NVIDIA 官方资产与 Kit extensions 不在
ModelScope/GHCR 中：

```bash
./s4 setup-isaac-assets
./s4 setup-kit-extensions --accept-nvidia-license
```

用户也可以把 `setup-isaac-assets` 指向已取得的官方 Isaac Sim 5.1 Local Assets Pack。许可参数
表示用户已自行阅读并接受 NVIDIA 条款，项目不能代替用户接受。

## 验证与运行

```bash
./s4 verify sim
./s4 rollout sim-smoke-offline
./s4 rollout sim-offline
# 本地 X11/XWayland 桌面可选：./s4 rollout sim-gui

./s4 verify policy
./s4 train policy-smoke

./s4 verify real-policy
./s4 verify real-server
./s4 verify robot
```

`verify robot` 不创建 publisher、不驱动机器人。实体相机、feedback、shadow 和 live motion 必须
连接硬件后按 `real_vla_stack/docs/real_robot_rollout.md` 的安全门逐级执行。

## 发布维护

三个镜像推送到 GHCR，项目制品推送到 ModelScope。正式发布步骤、digest 和验证证据见
`release/README.md`、`release/manifest.yaml` 与 `docs/PROJECT_STATUS.md`。大文件上传失败可幂等
重试，registry 会复用已存在的内容寻址 layer。
