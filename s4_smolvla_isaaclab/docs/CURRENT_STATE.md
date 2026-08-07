# 重构审计记录

审计基线：项目 Git `8a9745917aca78fcdf7ceee5c0badfdc717c8e1c`，日期
2026-08-07。审计时主仓库 clean；LeRobot `3f2179f3...` clean；IsaacLab
`37ddf626...` dirty，包含用户已有修改，本次未触碰。

## 原架构与数据流

原链路为 `run.sh` -> 语义 wrapper -> `00_` 至 `12_` 编号实现脚本。
场景/机器人在 `s4_robot/`，任务注册在 `tasks/`，drawer 状态机在独立
controller 中，旧 cylinder 状态机仍在通用 recorder。数据流为：

`IsaacLab 120Hz -> 每6步采样 -> HDF5 20Hz -> LeRobotDataset 20Hz ->
SmolVLA chunk=50 -> JSON-lines policy server -> 20Hz action -> 120Hz 插值`。

## 主要问题

- 编号脚本才是实现，语义脚本只是 `runpy` wrapper，入口关系反直觉。
- active task 通过复制 JSON/YAML 到公共文件实现，产生三个配置副本。
- `/home/zfy` 出现在 shell、Python、JSON、YAML 和文档中。
- preview/visualize 默认仍指向旧 13D 单臂任务。
- shell 与 Python 重复维护 Conda、asset、dataset 和 checkpoint 路径。
- 根 README 超过 900 行，混合多个历史任务，命令互相冲突。
- 没有统一 doctor、dataset/checkpoint contract validator 或自动测试。
- 数据、模型和输出约 59GB/7.4GB/35GB，必须保持原位且排除 Git。
- 系统 `ffmpeg` 不在 PATH；转换实际通过 PyAV/SVT-AV1 工作。
- `env_isaaclab` 可能受 ROS `PYTHONPATH` 中错误 Pinocchio 干扰。

## 外部依赖与风险

- Isaac Sim 5.1、IsaacLab、Isaac 5.1 assets、S4 URDF/mesh、LeRobot checkout、
  SmolVLM2 基础权重均不是可由本仓库独立提供的资源。
- 现有 checkpoint 保存了绝对 `vlm_model_name`，但加载 pretrained_model 时
  已含策略权重；项目仍保留相同 feature contract 以直接 rollout。
- drawer 任务依赖精确 prim path、相机 key、26D 顺序和 scripted phase text。

## 迁移顺序

1. 保持 26D 和任务行为，先统一路径解析与 active task。
2. 将编号实现移动到语义文件名，更新引用后删除 wrapper。
3. 增加 doctor、dataset-check、诊断和测试。
4. 整理双环境、manifest 和文档。
5. 最后执行静态检查、数据契约、policy server 和 rollout 回归。

迁移后的文件映射见 [MIGRATION.md](MIGRATION.md)。
