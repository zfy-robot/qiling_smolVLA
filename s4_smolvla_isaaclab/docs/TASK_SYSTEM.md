# 任务系统

一个任务由五部分组成：

1. `TaskModuleSpec`：ID、描述、数据维度、builder/controller import path。
2. scene builder：只构建该任务的 USD、刚体、相机和机器人。
3. scripted controller：阶段、anchor、IK target、hand target 和完成条件。
4. `<task>.dataset.json` 与 `<task>.scripted.yaml`。
5. `<task>.smolvla.yaml`。

查看和选择任务：

```bash
bash run.sh list-tasks
bash run.sh activate-task drawer_insert_close
```

选择结果写到 `.local/active_task`，可用 `S4_TASK=<id>` 临时覆盖。默认任务在
`configs/active_task.default`。active task 不再通过复制配置实现。

`drawer_insert_close` 是当前 26D 三相机基准任务。旧 cylinder task 仍可用于
兼容，但它有独立的 13D conversion contract，不应与 drawer checkpoint 混用。
当前在线 rollout adapter 明确注册为 `drawer_insert_close`；新任务在 scene 和
scripted collection 验证后，还需要提供该任务自己的 reset/gating/success adapter，
不得让公共 rollout 猜测 drawer/can 语义。
