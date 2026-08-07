# 故障排查

## `doctor` 路径失败

复制 `.env.example` 到 `.env`，确认 assets 根目录包含 `Isaac/` 和 `NVIDIA/`。
不要把 `ISAAC_ASSET_ROOT` 配到其下层 `Isaac/`。

## Pinocchio/Pink 导入 ROS Python 3.10

必须通过 `bash run.sh sim/record/rollout` 启动。入口会优先设置当前
`env_isaaclab` 的 cmeel Python 和 library path。

## 转换后 MP4 视角错误

转换不渲染，只编码 HDF5。先用 `dataset-check --hdf5`，再重新采集；
`--headless` 仍启用 sensor render，不应改变 camera extrinsics/light 配置。

## policy server 超时或 feature mismatch

运行 `dataset-check --checkpoint <path>`。确认 checkpoint 目录最终包含
`pretrained_model/config.json`，且 dataset 是同一 26D 三相机任务。

## rollout 抖动

运行 `diagnose`，按 raw -> ensemble -> command -> actual 顺序定位。hand tracking
高时检查 6D-to-mimic mapping、碰撞和关节限制，不要先提高刚度。

## 数据/训练输出已存在

转换使用 `--overwrite`；训练使用 `--resume` 或新的 output_dir。先执行
`bash run.sh clean --dry-run`，不要手工删除未知 checkpoint。
