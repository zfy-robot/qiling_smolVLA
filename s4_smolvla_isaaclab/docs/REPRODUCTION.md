# 复现与部署

本文说明 v0.1.0 模块化发布方式。旧单体 Docker 镜像已经退役，不再支持从镜像内复制数据、
named volume 初始化或 `docker/run.sh` 启动。

## 1. 可复现对象

| 对象 | 管理位置 | 固定方式 |
|---|---|---|
| 主项目 | GitHub | tag + commit |
| IsaacLab、LeRobot | Git submodule | gitlink commit |
| sim/policy/robot 环境 | GHCR | OCI digest |
| 模型、数据、checkpoint、项目资产 | ModelScope | revision + SHA256 |
| NVIDIA Isaac 资产/Kit extensions | NVIDIA 官方源 | URL + size + SHA256 lock |
| 输出、缓存、机器配置 | 部署主机 | `.s4/`、`.env`，不进 Git |

唯一版本映射是根目录 `release/manifest.yaml`。镜像没有源码或制品，运行时通过根
`compose.yaml` 只读挂载；输出与缓存使用 bind mount 写回宿主。

## 2. 支持条件

- Linux x86_64，推荐 Ubuntu 22.04；
- Docker Engine、Compose v2；
- sim/policy GPU 工作负载需要 NVIDIA Container Toolkit；
- NVIDIA driver 580.65.06+，sim 建议 RTX 16GB+ VRAM；
- 建议 64GB RAM、200GB 可用 NVMe；
- robot 主机需要 ROS/DDS 网络与 USB RealSense，不要求 NVIDIA GPU。

已验证组合为 RTX 4090 24GB、driver 580.159.03。其他设备尚未完成兼容性验证，部署前必须
执行 preflight，不能把容器化理解为消除所有硬件/驱动要求。

## 3. 克隆与版本确认

```bash
git clone --recurse-submodules https://github.com/zfy-robot/qiling_smolVLA.git
cd qiling_smolVLA
git checkout v0.1.0
git submodule update --init --recursive
cp .env.example .env

git rev-parse HEAD
git submodule status
```

不要自动跟随 IsaacLab/LeRobot 最新分支。CI 会拒绝漂移的 gitlink。

## 4. 环境镜像

普通用户从 manifest 的不可变 digest 拉取：

```bash
./s4 pull sim
./s4 pull policy
./s4 pull robot
# 或 ./s4 pull all
```

`pull` 会把 digest 引用标记为 Compose 使用的本地 `:dev` 名称。只有修改环境依赖或制作下一
release 的维护者才执行：

```bash
./s4 build sim      # 也可选择 policy、robot 或 all
```

Dockerfile 分别位于 `docker/sim/`、`docker/policy/`、`docker/robot/`。宿主内核和 NVIDIA
驱动不进入镜像；Container Toolkit 在运行时注入设备和驱动实现库。

## 5. 项目制品

先构建小型下载工具，再按用途下载：

```bash
./s4 build artifacts
./s4 setup sim_rollout
./s4 setup sim_training
./s4 setup real_full
# 全教程：./s4 setup tutorial_all
```

下载目标为 `.s4/artifacts/`，固定 ModelScope revision 并校验文件。正式 release 不使用
`master`，不发布 optimizer/`training_state`。仿真采用 350K，真机采用 300K checkpoint。

## 6. NVIDIA 资产

项目不能二次分发 NVIDIA Isaac 资产或 Kit extensions。阅读相应条款后执行：

```bash
./s4 setup-isaac-assets
./s4 setup-kit-extensions --accept-nvidia-license
```

若已有官方 Isaac Sim 5.1 Local Assets Pack：

```bash
./s4 setup-isaac-assets /path/to/Assets/Isaac/5.1
```

锁文件分别为 `release/isaac_assets_5.1.lock.json` 和
`release/isaac_extensions_5.1.lock.json`。运行时可以禁网验证，不会静默补下载。

## 7. 仿真复现

```bash
./s4 preflight
./s4 setup sim_rollout
./s4 pull sim
./s4 verify sim
./s4 rollout sim-smoke-offline
./s4 rollout sim-offline
```

`verify sim` 检查 CUDA、NVIDIA Vulkan、两个 Python 环境、Isaac Sim、IsaacLab、资产、
checkpoint processor 和 RGB camera。完整 episode 输出在 `.s4/outputs/eval/`；环境通过不代表
350K 策略一定成功，成功率以 summary 为准。

## 8. 训练复现

```bash
./s4 setup sim_training
./s4 pull policy
./s4 verify policy
./s4 train policy-smoke
```

训练环境与 sim 环境独立。`policy-smoke` 只训练一步并写新目录，不覆盖发布 checkpoint。正式
训练、多 GPU 参数与契约检查见 [PIPELINE.md](PIPELINE.md)。并发训练必须使用不同输出目录和
master port。

## 9. 真机部署

推荐两台机器：GPU 服务器运行 policy，机器人电脑运行 robot。两台机器 clone 同一 tag，下载
所需制品。

GPU 服务器：

```bash
./s4 build artifacts
./s4 setup real_full
./s4 pull policy
./s4 verify real-policy
./s4 verify real-server
docker compose --profile real up policy-server
```

机器人电脑：

```bash
./s4 build artifacts
./s4 setup real_rollout
./s4 pull robot
./s4 verify robot
```

在机器人电脑 `.env` 设置 `S4_POLICY_SERVER_HOST`、`ROS_DOMAIN_ID`、
`HW_TELEOP_NETWORK_INTERFACE` 和相机序列号。跨机只允许可信隔离局域网和防火墙白名单 TCP
5555。完整现场门禁见 `real_vla_stack/docs/real_robot_rollout.md`。

## 10. 本地路径与备份

| 路径 | 内容 | 建议 |
|---|---|---|
| `.s4/artifacts/` | 可重下载发布制品 | 可清理后重建 |
| `.s4/outputs/` | 唯一实验/采集输出 | 必须备份 |
| `.s4/cache/` | Kit/XDG/运行缓存 | 可重建，离线运行前保留 |
| `local_assets/isaac/` | NVIDIA 官方资产 | 按许可本地保存 |
| `.env` | 机器配置 | 私密配置管理，不提交 |

不要执行来源不明的递归删除。清理前先确认 `.s4/outputs/` 已备份。

## 11. 常见错误

| 现象 | 检查 |
|---|---|
| submodule 目录为空 | `git submodule update --init --recursive` |
| GHCR 拉取 401 | package 是否 Public；应按 manifest digest 拉取 |
| ModelScope 下载失败 | revision、代理与 `.s4/modelscope/` 权限 |
| CUDA 通过但 Vulkan 失败 | host driver、graphics capability、DRM node、Container Toolkit |
| Kit 离线缺 extension | 执行带许可参数的 `setup-kit-extensions` |
| 场景材质/纹理缺失 | Isaac asset lock 是否完整 |
| dataset/checkpoint 被拒绝 | contract SHA256、相机键、state/action、LeRobot commit |
| 容器内写入失败 | `.s4/` UID/GID 和 bind mount 权限 |
| 真机无响应 | 先停在 feedback/shadow 门，检查 DDS 网卡、domain、publisher 冲突 |

## 12. 验收定义

v0.1.0 发布验收包括本机三个镜像的构建与运行、ModelScope/GHCR 公共可访问性和 digest、CI、
文档与旧单体入口移除。其他设备复现和实体机器人 live motion 当前明确暂缓，完成后另行记录
兼容性矩阵，不能回填为本次已验证事实。
