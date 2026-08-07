# 可复现性

记录一次实验至少需要：项目 commit、LeRobot commit、IsaacLab commit/dirty、
两个环境版本、active task 三个配置、dataset ID/stats、checkpoint step、seed 和
完整命令。

```bash
bash environment/collect_versions.sh > outputs/eval/version_snapshot.txt
bash run.sh doctor --strict
bash run.sh dataset-check --checkpoint <checkpoint>
bash run.sh rollout --deterministic --checkpoint <checkpoint>
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 conda run -n env_isaaclab python -m pytest -q tests
```

确定性是“尽可能固定”的回归条件，GPU PhysX、渲染和模型算子仍可能存在细微
非确定性。应比较任务 success、drawer/can 最终状态、sim duration 和诊断分布，
而不是要求视频逐像素一致。

禁用 pytest plugin autoload 是为了避免系统 ROS Humble 的 Python 3.10
`launch_testing` 插件污染 Python 3.11 IsaacLab 测试进程。

现有 360K checkpoint 保持 26D/三相机/20Hz/chunk50 contract，可直接用于重构后
rollout，不需要重新训练。

本次重构后的实际 deterministic 回归结果：`complete=True`、`success=True`、
最终重构验收结果为 `complete=True`、`success=True`、`sim=23.2s`、
`drawer=0.001m`、`can_z=1.023m`。视频为三路相机横向拼接的
2040x480、20 fps、464 帧。固定场景结果与迁移前基线一致，无需重新训练。
