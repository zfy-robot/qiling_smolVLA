# 数据采集

环境：`env_isaaclab`，由 `run.sh` 自动选择。

```bash
bash run.sh sim
bash run.sh record --episodes 10
bash run.sh record --episodes 200 --headless
```

物理/控制为 120 Hz，每 6 步采一帧，HDF5 为 20 Hz。`--headless` 关闭 GUI，
但 camera sensor 仍渲染三路 RGB；它不是“无相机”。每次 reset 后按 scripted
配置等待场景稳定。超时或 success criteria 失败的 episode 不写入文件，直到
达到请求的成功轮数。

主任务默认使用可复现的分层网格内随机：罐子 XY 的连续范围被划分为 `5 x 5`
网格，每一轮以随机顺序访问全部 25 个格子，并在当前格子内部均匀采样精确位置。
失败或超时后会在同一格内换一个精确位置；三个点都失败时记录并跳过该格，避免
采集停滞。抓住罐子后，只有 `right_can_lift` 的 XYZ 目标会分别在
`±2 cm` 内随机；抓取、放置、关抽屉和回零轨迹不变。参数位于
`configs/tasks/drawer_insert_close.scripted.yaml` 的 `randomization`。

抽屉任务进入 `record` 模式时，还会生成 Master Chef 罐、芥末瓶和漂白剂瓶三个
不同的 YCB 干扰物。每轮会随机打乱它们所在的三个柜面安全区并在区内连续采样，
与主抓取罐及彼此保持最小中心距；控制器、成功判定和
主罐的分层网格均不变。普通 `sim`、`teleop` 默认不启用；rollout 根据转换数据集的
`meta/s4_contract.json` 自动匹配，可用 `--distractor-cans`/`--no-distractor-cans` 覆盖。

场景光照是固定的，不参与随机化。预览、采集和 rollout 将任务区附近的仓库灯缩放
到原始强度的 18%，远处背景灯设为 55%，并共用低强度环境光、前侧柔光与 RTX
质量设置。这样可以提高环境亮度，同时避免白色机器人和桌面过曝，并保留颜色、
粗糙度和纹理细节。

默认输出：`${S4_DATA_ROOT}/staging/<dataset>/<task>_scripted.hdf5`。中断时已
flush 的完整 `demo_N` 通常可用，但必须运行：

采集中断后可在同一个 HDF5 上续采。`--episodes` 表示文件最终需要达到的成功
条数，而不是额外追加条数；已有 episode、随机数状态、网格游标、当前格内点和
已跳过格子都会恢复。每个格子最多尝试三个不同点，每点失败一次即换点，三点均
失败则跳过该格，避免采集永久停滞。示例：

```bash
bash run.sh record --output datasets/staging/s4_drawer_insert_close_v0/run.hdf5 \
  --episodes 20 --resume
```

```bash
bash run.sh dataset-check --hdf5
```

多进程采集使用 `bash run.sh record-parallel --num-episodes 100 --workers 2`。
每个 worker 是独立 Isaac Sim 进程；先从 2 个开始评估显存。

只执行“采集、校验、转换、再校验”而不训练：

```bash
bash run.sh collect-convert --episodes 200 --headless --overwrite
```

该命令不会调用训练脚本。默认把本轮 HDF5 写入带时间戳的独立目录；`--overwrite`
只用于替换目标 LeRobotDataset，不会删除刚采集的 HDF5。

并行采集时，每个 worker 使用“基础随机种子 + worker id”，避免多个 HDF5 文件
重复同一套随机序列。单进程自动流程可以用 `--random-seed 42` 明确设置种子。
