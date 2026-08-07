# 项目结构

```text
.
|-- run.sh                    # 唯一 CLI
|-- pyproject.toml            # 项目元数据与测试工具配置
|-- .env.example
|-- configs/
|   |-- active_task.default
|   |-- external_assets.yaml
|   `-- tasks/               # 每个任务的 dataset/scripted/train 配置
|-- s4_pipeline/             # 路径与配置
|-- s4_robot/                # 机器人、映射、IK、仿真公共组件
|-- tasks/                   # 任务注册、场景、控制器、模板
|-- data/                    # HDF5 与转换
|-- scripts/                 # 语义化执行入口
|-- tests/                   # 无 GPU 单元测试
|-- environment/             # 双环境与版本快照
|-- docs/                    # 教程和接口文档
|-- assets/                  # 可提交的小型 S4 自有资产
|-- datasets/                # 生成物，不进 Git
|-- models/                  # 权重，不进 Git
`-- outputs/                 # checkpoint/eval，不进 Git
```

公共脚本不导入具体任务类；它们从 `tasks.TASK_REGISTRY` 获取 builder 和
controller。任务资产路径只允许在 task config/scene module 中出现。
