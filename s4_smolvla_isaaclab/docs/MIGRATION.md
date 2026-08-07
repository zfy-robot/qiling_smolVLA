# 迁移说明

## 脚本映射

| 旧文件 | 新 canonical 文件 |
|---|---|
| `00_inspect_project.py` | `inspect_project.py` |
| `03_record_physics_dataset.py` | `record_dataset.py` |
| `03_joint_debug.py` | `joint_debug.py` |
| `05_convert_hdf5_to_lerobot.py` | `convert_lerobot.py` |
| `06_eval_smolvla_in_isaaclab.py` | `eval_policy.py` |
| `07_preview_smolvla_policy.py` | `preview_policy.py` |
| `08_visualize_smolvla_policy.py` | `visualize_policy.py` |
| `09_smolvla_policy_server.py` | `policy_server.py` |
| `10_clean_generated.py` | `clean_generated.py` |
| `11_record_parallel_hdf5.py` | `record_parallel.py` |
| `12_collect_convert_train.sh` | `pipeline_collect_convert_train.sh` |

未使用的 `04_record_bimanual_hdf5.py` 和 `_legacy_entry.py` 已删除。数字脚本内容
移动而非重写。

## CLI 映射

`record-hdf5 -> record`、`convert-lerobot -> convert`、`train-smolvla -> train`、
`preview-smolvla -> preview`、`eval-smolvla -> rollout`。旧 CLI 名暂时作为同一
实现的 alias，不是第二套代码。

active task 不再复制到 `configs/s4_bimanual_dataset.json` 和
`smolvla_s4_bimanual.yaml`；这两个重复文件已删除。`activate-task` 现在写
`.local/active_task`。现有 dataset/output/checkpoint 目录未移动、未删除。
