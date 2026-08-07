# 双环境

| 阶段 | 环境 | Python | 原因 |
|---|---|---:|---|
| 场景、控制、采集、rollout simulator | `env_isaaclab` | 3.11 | Isaac Sim ABI |
| 转换、数据读取、训练、policy server | `smolvla` | 3.12 | LeRobot/SmolVLA |

`run.sh` 根据命令切换 `PATH`，在线 rollout 由 IsaacLab 主进程启动独立
SmolVLA JSON-lines 子进程，因此不会把两套 Python 包混在一个解释器中。

```bash
bash environment/collect_versions.sh
bash run.sh doctor
```

不要在 shell 中保留 ROS 的 Python 3.10 Pinocchio 路径；`run.sh` 会把当前
IsaacLab 环境内的 cmeel 路径放到最前。完整版本见
[environment/versions.md](../environment/versions.md)。
