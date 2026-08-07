# 在线 Rollout

IsaacLab 主进程使用 `env_isaaclab`，policy server 使用 `smolvla`：

```bash
bash run.sh rollout \
  --checkpoint outputs/train/smolvla_drawer_insert_close_v0/checkpoints/360000/pretrained_model \
  --policy-device cuda --deterministic
```

`--deterministic` 固定 seed 并关闭任务随机化。server 从 dataset 恢复 phase text
和中位持续时间，输出 50-frame action chunk。默认每 25 policy frames 重规划，
重叠 5 帧融合，阶段切换 8 帧过渡；20 Hz command 在相邻点间线性插值成 120 Hz
关节 target。底层 stiffness/damping 不用于掩盖策略跳变。

成功条件由 active task scripted YAML 定义。当前固定场景回归基线：
`complete=True success=True drawer≈0.003m can_z≈1.023m sim≈23.6s`。
输出 AVI、CSV 和 PNG 位于 `${S4_OUTPUT_ROOT}/eval`。
