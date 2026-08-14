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
失败或超时后会在同一格内换一个精确位置；三个点都失败时立即停止并保留已采数据
和失败日志，不会跳格或用下一轮位置补足数量。当前网格是位于柜面安全区内的
`5 x 8 cm` 长方形；抓住罐子后的抬升
偏移固定，不再随机；抓取、放置、关抽屉和回零轨迹不变。参数位于
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
当前格子状态都会恢复。每个格子最多尝试三个不同点，每点失败一次即换点；三点均
失败则安全中止，避免采集永久停滞或生成缺格数据。修复问题后可续采同一文件。示例：

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
只用于替换目标 LeRobotDataset，不会删除刚采集的 HDF5。转换前会检查成功条数、
失败摘要和网格覆盖；默认只要存在跳过格子就停止，不会转换覆盖不完整的数据集。

每次失败会立即写入 HDF5 同目录下的 `*_failures.jsonl`，并在
`*_failure_summary.json` 中按阶段和原因汇总。包含罐子位置、网格编号、TCP 误差、
抽屉开度和手指状态，进程异常退出时已经落盘的失败记录仍保留。

执行带安全关卡的“采集、转换、检查、训练”完整流程：

```bash
bash run.sh collect-train --episodes 200 --headless \
  --overwrite-dataset --overwrite-training-output
```

任何采集未完成、失败报告不匹配、跳格、HDF5/LeRobot 契约错误都会在训练前停止。
两个自动流程默认使用 `--max-failed-attempts 0`：第一次失败就安全停止，确保能够
进入转换和训练的整轮数据既没有失败尝试，也没有跳格。需要诊断重试行为时才显式
提高该参数；失败尝试本身不会写入 HDF5。

并行采集时，每个 worker 使用“基础随机种子 + worker id”，避免多个 HDF5 文件
重复同一套随机序列。单进程自动流程可以用 `--random-seed 42` 明确设置种子。
