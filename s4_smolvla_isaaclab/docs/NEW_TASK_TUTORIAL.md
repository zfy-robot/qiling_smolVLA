# 创建新任务

## 1. 复制模板

参考 `tasks/templates/minimal_task/`，创建：

```text
tasks/my_task.py
tasks/my_task_scene.py
tasks/my_task_controller.py
configs/tasks/my_task.dataset.json
configs/tasks/my_task.scripted.yaml
configs/tasks/my_task.smolvla.yaml
```

在 `tasks/__init__.py` 导入 `TASK_SPEC` 并加入 `TASK_REGISTRY`。

## 2. 保持公共接口

- builder 接受公共 `SceneBuildCfg` 并返回 recorder 需要的 scene 对象。
- controller 提供 reset/step/phase metadata 和 success result。
- 任务文本必须在 HDF5 每帧写入，转换后成为 `task_index`。
- 若继续使用 S4 双臂，优先保持 26D；改变维度时创建 schema/dataset v2，
  不覆盖现有 dataset ID。

## 3. 验证

```bash
bash run.sh activate-task my_task
bash run.sh doctor
bash run.sh sim
bash run.sh record --episodes 1
bash run.sh dataset-check --hdf5
```

场景、任务随机化与 success criteria 验证后才能批量采集。转换和训练代码
不应因新任务而修改。
