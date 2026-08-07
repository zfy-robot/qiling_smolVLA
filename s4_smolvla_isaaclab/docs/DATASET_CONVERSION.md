# 数据集转换

环境：`smolvla`。

```bash
bash run.sh convert
bash run.sh convert --root-path datasets/staging/s4_drawer_insert_close_v0 --overwrite
```

转换器读取 HDF5 `processed_actions`、active state、逐帧 task text 和三路 RGB，
调用外部 LeRobot `LeRobotDataset.create/add_frame/save_episode/finalize`。视频由
PyAV 编码；转换不会重新渲染相机，因此 MP4 视角完全来自 HDF5。

`--overwrite` 只针对目标 LeRobotDataset；它不会删除 HDF5。不同任务或 schema
必须使用不同 repo/dataset ID，避免覆盖训练所依赖的数据统计量。
