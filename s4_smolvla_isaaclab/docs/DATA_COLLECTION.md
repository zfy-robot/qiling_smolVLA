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

默认输出：`${S4_DATA_ROOT}/staging/<dataset>/<task>_scripted.hdf5`。中断时已
flush 的完整 `demo_N` 通常可用，但必须运行：

```bash
bash run.sh dataset-check --hdf5
```

多进程采集使用 `bash run.sh record-parallel --num-episodes 100 --workers 2`。
每个 worker 是独立 Isaac Sim 进程；先从 2 个开始评估显存。
