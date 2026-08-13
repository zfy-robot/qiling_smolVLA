# 在线 Rollout

IsaacLab 主进程使用 `env_isaaclab`，policy server 使用 `smolvla`。

## 输出目录约定

每次 rollout **只写一个子文件夹**（多轮随机测试也全部放在同一文件夹内）：

```text
outputs/eval/rollout_<YYYYMMDD_HHMMSS>_<det|randN>_ckpt<step>/
  rollout.avi                 # 单轮
  rollout_actions.csv
  rollout_actions.png
  ep001.avi                   # 多轮（全部在同一目录）
  ep001_actions.csv
  ep001_actions.png
  ...
  summary.json
```

- 不传路径时自动按时间戳命名，避免互相覆盖、避免 `outputs/eval/` 根目录堆文件。
- `--output-dir outputs/eval/my_rand20`：自定义本次运行目录。
- `--output-video outputs/eval/foo.avi`：兼容写法，实际写入 `outputs/eval/foo/`。

## 固定场景回归

```bash
bash run.sh rollout \
  --headless \
  --deterministic \
  --checkpoint outputs/train/smolvla_drawer_insert_close_v0/checkpoints/360000/pretrained_model \
  --policy-device cuda
```

或指定目录：

```bash
bash run.sh rollout \
  --headless \
  --deterministic \
  --checkpoint outputs/train/smolvla_drawer_insert_close_v0/checkpoints/360000/pretrained_model \
  --policy-device cuda \
  --output-dir outputs/eval/det_360k
```

`--deterministic` 展开为 `--no-randomize-task --seed 42`。`--seed` 无论是否随机化都默认且保持为 **42**。

## 随机化成功率评估

任务随机化采样三项：

1. 罐子 XY 偏移（`can_xy`，按随机顺序遍历 5x5 网格并在格内均匀采样）
2. 抽屉初始开度（`drawer_initial_open`）
3. 三个不同 YCB 柜面干扰物的位置（与新采集数据的视觉分布一致）

rollout 默认读取数据集的 `meta/s4_contract.json`：新采集数据自动启用三个干扰物，
旧数据集没有该标记时保持旧的无干扰罐场景。可用 `--distractor-cans` 或
`--no-distractor-cans` 显式覆盖；`--deterministic` 会把所有启用的物体放在固定安全
位置，确保重复运行画面一致。

默认范围来自
[`drawer_insert_close.scripted.yaml`](../configs/tasks/drawer_insert_close.scripted.yaml)。
实验种子固定为 42；多轮共用同一 RNG 流，产物全部在同一 `output-dir`。

```bash
bash run.sh rollout \
  --headless \
  --success-rate 20 \
  --checkpoint outputs/train/smolvla_drawer_insert_close_v0/checkpoints/360000/pretrained_model \
  --policy-device cuda
```

自定义范围与目录：

```bash
bash run.sh rollout \
  --headless \
  --episodes 20 \
  --randomize-task \
  --seed 42 \
  --can-x-range -0.05 0.05 \
  --can-y-range -0.05 0.05 \
  --drawer-open-range 0.0 0.05 \
  --checkpoint outputs/train/smolvla_drawer_insert_close_v0/checkpoints/360000/pretrained_model \
  --policy-device cuda \
  --output-dir outputs/eval/rand20_360k
```

结束日志会打印 `output_dir=...` 和 `success=K/N`。可用
`--no-save-videos` / `--no-save-diagnostics` 只写 `summary.json`。

成功条件见 scripted YAML 的 `success`：`drawer_open_abs_max` 与 `can_world_z`。

## 控制与诊断

```bash
bash run.sh diagnose outputs/eval/<run_dir>/ep001_actions.csv
# 或单轮
bash run.sh diagnose outputs/eval/<run_dir>/rollout_actions.csv
```

当前固定场景回归基线（仅作接口参考）：
`complete=True success=True drawer≈0.003m can_z≈1.023m sim≈23.6s`。
