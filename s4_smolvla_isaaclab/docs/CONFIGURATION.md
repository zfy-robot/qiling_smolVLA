# 配置

## 路径变量

从 `.env.example` 复制 `.env`。必须配置 `ISAACLAB_ROOT`、`LEROBOT_ROOT` 和
`SMOLVLA_MODEL_ROOT`。运行场景使用 `S4_SCENE_ASSET_ROOT`，默认指向项目内被 Git
忽略的 `local_assets/isaac/5.1`；`ISAAC_ASSET_ROOT` 只是在制作该资产包时指向完整
Isaac 资产库。dataset、output、cache 可放到其他磁盘。提交的配置只使用
`${VAR}`，不写用户绝对路径。

## Source of truth

| 内容 | 唯一来源 |
|---|---|
| active task | `.local/active_task` 或 `S4_TASK` |
| dataset/schema/scene | `configs/tasks/<task>.dataset.json` |
| scripted trajectory/randomization/success | `<task>.scripted.yaml` |
| SmolVLA hyperparameters/output | `<task>.smolvla.yaml` |
| Task randomization defaults | `<task>.scripted.yaml` → `randomization` |
| Rollout success-rate overrides | CLI: `--episodes`/`--success-rate`, `--can-*-range`, `--seed` |
| joint order/hand mimic mapping | `s4_robot/s4_robot_cfg.py`, `control_mapping.py` |
| CLI override | 当前命令行，仅覆盖本次执行 |

配置解析在 `s4_pipeline/config.py`。不要重新建立“active config copy”，也不要
在 Python 和 shell 中复制任务默认值。

`schema_version`、`action_semantics`、`fps` 和 `control_fps` 是数据兼容性的
机器可读声明。变更 state/action 顺序、维度、相机 key 或动作语义时必须升级
schema 版本；仅调整轨迹、随机化或训练超参数不升级 schema。
