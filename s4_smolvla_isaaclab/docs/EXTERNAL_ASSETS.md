# 外部资产

本仓库不能独立提供以下内容：

- Isaac Sim 5.1 和外部 IsaacLab checkout。
- Isaac Sim 5.1 assets，默认 `${ISAAC_ASSET_ROOT}`。
- LeRobot checkout，默认 `${LEROBOT_ROOT}`。
- SmolVLM2-500M-Video-Instruct，默认 `${SMOLVLA_MODEL_ROOT}`。
- S4 robot URDF/mesh（若许可允许，当前位于 `assets/my_robot`）。
- 训练数据与 checkpoint。

机器可读清单在 `configs/external_assets.yaml`。路径通过 `.env` 配置；项目代码
不下载或复制这些资源。若资产发布方提供 checksum，应在部署清单中记录，但
不要把大文件加入 Git。
