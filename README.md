# S4 SmolVLA

S4 双臂机器人从仿真/真机数据采集、LeRobot 数据转换、SmolVLA 训练到 rollout 的可复现教程工程。
项目把发布物拆成四层：GitHub 源码、三个职责独立的 OCI 环境镜像、ModelScope 大文件，以及
宿主机上的私有运行数据。镜像不包含项目源码、数据集、模型、NVIDIA 驱动或主机专用配置。

## 架构

| 组件 | 内容 | 运行位置 |
|---|---|---|
| `sim` | Python 3.11、Isaac Sim 5.1、IsaacLab 2.3.2、仿真依赖 | NVIDIA RTX 工作站 |
| `policy` | Python 3.12、PyTorch、LeRobot/SmolVLA、训练与推理服务 | NVIDIA GPU 服务器 |
| `robot` | Ubuntu 22.04、ROS 2 Humble、qi、Pink/QP、RealSense | 机器人控制/边缘电脑 |
| `artifacts` | ModelScope 下载与 SHA256 校验工具 | 任意 Docker 主机 |

源码在运行时只读挂载，ModelScope 制品挂载到 `/artifacts`，输出和缓存写入 `.s4/`。宿主机
NVIDIA 驱动由 NVIDIA Container Toolkit 在容器启动时注入，Dockerfile 不安装内核驱动。

真机推荐使用两台机器：机器人电脑运行 `robot` 容器；GPU 服务器运行 `policy-server`，两者
通过可信局域网 TCP 5555 通信。同机部署时 `S4_POLICY_SERVER_HOST=127.0.0.1`。

## 支持条件

- Linux x86_64；推荐 Ubuntu 22.04、64GB RAM、200GB 可用 NVMe；
- 仿真/训练需要 NVIDIA RTX GPU，最低建议 16GB VRAM，已验证 RTX 4090 24GB；
- Linux NVIDIA driver `580.65.06` 或更新版本；当前验证版本为 `580.159.03`；
- Docker Engine、Compose plugin、NVIDIA Container Toolkit；
- 真机端需要 ROS/DDS 可达、USB RealSense、机器人 SDK 与现场急停。

CUDA/Isaac 用户态库固定在镜像中，主机只需满足驱动下限。非 NVIDIA GPU、macOS、Windows、
ARM64 和无 RT Core 的 GPU 不在当前支持范围内。先运行：

```bash
./s4 preflight
```

## 获取源码

```bash
git clone --recurse-submodules https://github.com/zfy-robot/qiling_smolVLA.git
cd qiling_smolVLA
cp .env.example .env
```

如果已经 clone：

```bash
git submodule sync --recursive
git submodule update --init --recursive
```

IsaacLab 固定到 `zfy-robot/IsaacLab` 的兼容分支；LeRobot 也固定到经过验证的 commit。不要在
复现时自动追踪两个上游仓库的最新分支。

## 使用预构建环境镜像

推荐教程用户直接拉取经过验证的 GHCR 镜像。`./s4 pull` 从 `release/manifest.yaml` 读取不可变
digest，并自动标记为 Compose 使用的本地镜像；不使用会漂移的 `latest`：

```bash
./s4 pull sim       # 仿真采集与 rollout
./s4 pull policy    # 训练与 GPU policy server
./s4 pull robot     # ROS、遥操采集与真机 client
# 或一次拉取三个环境：./s4 pull all
```

只想使用项目时执行 `pull`，需要修改底层依赖或重新制作镜像时才执行 `build`。ModelScope 制品、
NVIDIA 官方资产和项目源码仍按下文挂载，不包含在这些环境镜像中。

## 仿真 rollout

第一次安装需要下载 ModelScope 运行制品、约 500MB 的 NVIDIA 官方 Isaac 资产子集，以及两个
Kit extension。执行 NVIDIA 下载前请先阅读并接受其许可证；这些文件不会上传到 GitHub、
ModelScope 或项目镜像。

```bash
./s4 build artifacts
./s4 setup sim_rollout
./s4 setup-isaac-assets
./s4 setup-kit-extensions --accept-nvidia-license
./s4 pull sim
./s4 verify sim
./s4 rollout sim-smoke-offline
./s4 rollout sim-offline
```

如果已有官方 Isaac Sim 5.1 Local Assets Pack，可避免逐文件下载：

```bash
./s4 setup-isaac-assets /path/to/Assets/Isaac/5.1
```

`--accept-nvidia-license` 表示用户已经阅读并接受 NVIDIA 对相应 Kit extension 的许可条款；
脚本不会代替用户接受条款，缺少该参数时会拒绝下载。

输出写入 `.s4/outputs/eval/`。发布的仿真 checkpoint 是 350K；环境验收通过不代表该策略必然
成功完成任务，成功率应以 rollout 的 `summary.json` 为准。

## 训练环境

```bash
./s4 setup sim_training
./s4 pull policy
./s4 verify policy
./s4 train policy-smoke
```

短测试只训练一步并写入独立目录，不覆盖发布 checkpoint。正式训练入口和参数见
[`s4_smolvla_isaaclab/run.sh`](s4_smolvla_isaaclab/run.sh) 及任务配置目录。

## 真机部署

先在 GPU 服务器和机器人电脑分别 clone 同一 tag/commit，并在两台机器执行：

```bash
cp .env.example .env
./s4 build artifacts
./s4 setup real_full
```

GPU 服务器：

```bash
./s4 pull policy
./s4 verify real-policy
./s4 verify real-server
docker compose --profile real up policy-server
```

机器人电脑：

```bash
./s4 pull robot
./s4 verify robot
```

在机器人电脑的 `.env` 中设置 `S4_POLICY_SERVER_HOST`、`ROS_DOMAIN_ID`、
`HW_TELEOP_NETWORK_INTERFACE` 和三台 RealSense 的 `S4_CAMERA_*_SERIAL`。相机序列号也可写入
被忽略的 `s4_smolvla_isaaclab/real_vla/config/cameras.yaml`；公共模板是
`cameras.example.yaml`。

`./s4 verify robot` 不创建 ROS publisher，也不驱动机器人。连接硬件后必须按以下门禁逐级验收：

1. 只读枚举相机和 ROS feedback；
2. shadow rollout，确认相机顺序、8D state/action、网络时延与安全日志；
3. 现场人员确认急停、关节方向、限位、工作区和 publisher 唯一性；
4. 仅在以上全部通过后做 5 秒低风险 live motion，再决定是否延长。

完整命令和安全语义见
[`real_robot_rollout.md`](s4_smolvla_isaaclab/real_vla_stack/docs/real_robot_rollout.md)。当前 ZMQ
协议没有身份认证或加密，跨机使用时必须在可信隔离局域网内，并用防火墙只允许机器人电脑访问
GPU 服务器 TCP 5555，禁止暴露到公网。

## 大文件与本地文件归属

- ModelScope `zfy2qiling/qiling_smolvla`：基础模型、两个发布数据集、350K/300K checkpoint、
  S4 机器人和项目场景资产；消费端固定不可变 revision；
- `.s4/artifacts/`：下载后的本地制品，不进 Git；
- `.s4/outputs/`：采集、训练、评估输出，不进 Git；
- `s4_smolvla_isaaclab/local_assets/`：NVIDIA 官方资产缓存，不进 Git/ModelScope；
- `.env`、`ros_env.sh`、`cameras.yaml`：机器专用配置，不进 Git；
- `training_state/`：不随教程发布；如需续训，单独使用私有归档。

版本、SHA256、镜像 digest、已完成验收和剩余硬件门禁记录在
[`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md)。制品目录和锁定信息见 `release/`。

## 常见网络问题

构建时访问 PyPI/GitHub 较慢，可在本地 `.env` 设置代理。Linux 上构建使用 host network，
所以构建阶段可访问宿主 `127.0.0.1:7890`。运行容器若未使用 host network，则不能把容器内
`127.0.0.1` 当作宿主代理。ModelScope 在国内通常应加入 `NO_PROXY`。

所有下载和构建均可重复执行；已校验的缓存会复用。不要把代理凭据、ModelScope token、相机
序列号、证书私钥或局域网地址提交到仓库。

## 许可证

项目代码使用 Apache-2.0，见 [`LICENSE`](LICENSE) 和 [`NOTICE`](NOTICE)。第三方源码、模型、
数据与资产仍适用各自许可证。NVIDIA Isaac Sim、官方资产和 Kit extensions 不随本项目再分发，
用户须自行接受 NVIDIA 条款并从官方来源获取。
