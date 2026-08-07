# Rollout 诊断

```bash
bash run.sh rollout --deterministic \
  --diagnostics-csv outputs/eval/actions.csv \
  --diagnostics-plot outputs/eval/actions.png
bash run.sh diagnose outputs/eval/actions.csv
```

CSV 对每个 20 Hz policy frame 保存：

- `raw.*`：最新 chunk 的原始策略 action。
- `ensemble.*`：chunk overlap 和阶段过渡后的 action。
- `command.*`：发送给 120 Hz 插值器的 endpoint。
- `actual.*`：执行一个 policy interval 后读取的 joint position。

`raw_jump` 大表示策略/chunk 不连续；`raw` 大而 `fused` 小表示 temporal fusion
有效；`command-actual` tracking 大表示执行器、碰撞、关节限制或 hand mimic 跟踪
问题。分别查看 LA/LH/RA/RH，避免整体均值掩盖灵巧手。tracking 已按“上一条
command 对下一 policy boundary actual”对齐，不能与旧版同帧指标直接比较。

建议顺序：先确认 dataset/checkpoint contract，再看 raw jump，然后看 fused，最后
看 tracking 和实际视频。不要先调 stiffness/damping。
