# S4 SmolVLA IsaacLab

本目录包含 S4 双臂机器人仿真学习与真机 VLA 业务代码。环境、制品和部署由仓库根目录的
`./s4`、`compose.yaml` 与 `release/manifest.yaml` 管理；不要在本目录重新创建独立部署方式。

## 当前链路

仿真：

```text
IsaacLab 专家/遥操 -> HDF5 -> LeRobotDataset -> SmolVLA 训练
-> 350K checkpoint -> Isaac Sim rollout -> 视频/动作/summary
```

真机：

```text
Quest + RealSense + ROS/DDS -> raw episode -> LeRobotDataset -> SmolVLA 训练
-> GPU policy-server（300K）-> robot shadow/live client
```

仿真主任务 `drawer_insert_close` 的契约为 `s4_bimanual_v1`，state/action 26D、数据 20Hz、
控制 120Hz、三路 RGB。真机发布契约为 8D state/action、两路相机。数据集与 checkpoint 必须
通过 contract SHA256 对齐，不能只按目录名或 tensor 维度判断兼容。

## 代码目录

| 路径 | 职责 | 环境 |
|---|---|---|
| `configs/tasks/` | 仿真任务、语言、数据与训练契约 | 通用 |
| `tasks/` | Isaac 场景和专家任务 | sim |
| `s4_robot/` | 仿真机器人配置、关节映射和控制 | sim |
| `s4_pipeline/` | 路径、契约、随机化和指标 | sim/policy |
| `scripts/record_dataset.py` | 仿真专家采集 | sim |
| `scripts/convert_lerobot.py` | HDF5 转 LeRobotDataset | policy |
| `scripts/train_smolvla_local.sh` | 单卡/Accelerate DDP 训练 | policy |
| `scripts/eval_policy.py` | 仿真 rollout 主进程 | sim |
| `hardware_teleop/` | Quest/Pink/ROS 真机遥操与安全门 | robot |
| `real_vla/` | 真机相机采集与 raw episode | robot |
| `real_vla_stack/host/` | 真机转换、训练和 policy server | policy |
| `real_vla_stack/robot/` | 真机 observation、client 和安全执行 | robot |

`run.sh` 是容器内业务命令路由。普通用户从仓库根目录调用 `./s4`，由 Compose 选择正确容器、
挂载和 Python 环境。

## 获取与验证

```bash
git clone --recurse-submodules https://github.com/zfy-robot/qiling_smolVLA.git
cd qiling_smolVLA
cp .env.example .env

./s4 build artifacts
./s4 setup sim_rollout
./s4 setup-isaac-assets
./s4 setup-kit-extensions --accept-nvidia-license
./s4 pull sim
./s4 verify sim
./s4 rollout sim-smoke-offline
```

训练：

```bash
./s4 setup sim_training
./s4 pull policy
./s4 verify policy
./s4 train policy-smoke
```

真机无硬件准备：

```bash
./s4 setup real_full
./s4 pull policy
./s4 pull robot
./s4 verify real-policy
./s4 verify real-server
./s4 verify robot
```

普通用户使用 GHCR 预构建镜像；维护者修改依赖时才运行 `./s4 build sim|policy|robot`。项目不再
维护把源码、模型、数据、资产和环境打进一起的单体镜像。

## 数据位置

- `.s4/artifacts/`：ModelScope 发布制品，只读挂载；
- `.s4/outputs/`：采集、转换、训练和评估输出；
- `.s4/cache/`：运行与 Kit 缓存；
- `local_assets/isaac/5.1/`：用户从 NVIDIA 官方取得的资产；
- `.env`、`hardware_teleop/config/ros_env.sh`、`real_vla/config/cameras.yaml`：本机配置。

上述本地数据均不进入 Git。正式发布只包含选定 checkpoint 的 `pretrained_model/`，不包含
`training_state/`。

## 业务命令

进入相应容器后，`bash run.sh help` 显示完整业务入口。常用命令包括：

```bash
bash run.sh doctor
bash run.sh list-tasks
bash run.sh record --help
bash run.sh collect-convert --help
bash run.sh dataset-check --help
bash run.sh train --help
bash run.sh rollout --help
```

完整采集/转换/训练参数见 [PIPELINE.md](docs/PIPELINE.md)，环境与交付见
[REPRODUCTION.md](docs/REPRODUCTION.md)，真机安全步骤见
[real_robot_rollout.md](real_vla_stack/docs/real_robot_rollout.md)。课程位于 [docs/course/](docs/course/)。

## 安全边界

- `--overwrite`、数据删除和输出覆盖必须由操作人员明确确认；
- state/action、相机键、FPS、动作语义或语言契约变化后必须重新转换、训练和 rollout；
- 仿真验证成功不等于 checkpoint 任务成功，策略表现以 `summary.json` 为准；
- `./s4 verify robot` 不创建 publisher、不驱动机器人；
- 实体机器人必须依次通过相机、feedback、shadow、急停/限位人工确认，再做 5 秒低风险动作；
- ZMQ 真机协议没有身份认证或加密，只能用于可信隔离局域网。

版本、镜像 digest、ModelScope revision、驱动支持线和实际完成的验证见根目录
`release/manifest.yaml` 与 `docs/PROJECT_STATUS.md`。
