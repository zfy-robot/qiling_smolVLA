# 故障排查

## `doctor` 路径失败

复制 `.env.example` 到 `.env`，确认 `S4_SCENE_ASSET_ROOT` 下存在
`Isaac/Environments/Simple_Warehouse/warehouse.usd`。默认目录是项目内的
`local_assets/isaac/5.1`。制作资产包时，`ISAAC_ASSET_ROOT` 应指向其上层 `5.1`
目录，不要指到下层 `Isaac/`。

## 场景整体变红或 MDL 报错

如果日志出现 `OmniUe4Function`、`OmniUe4Base` 找不到，说明使用了旧版不完整的
`local_assets`。维护者重新执行 `bash run.sh prepare-assets --verify`；使用者需要
重新获取资产包。确认 `bash run.sh doctor` 中 `implicit render assets: complete`，然后
完全退出并重启 Isaac Sim，清除当前进程内已经编译失败的红色错误材质。

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
