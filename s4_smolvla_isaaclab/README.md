# S4 IsaacLab + LeRobot + SmolVLA

这是一个可复用的双臂操作教程工程：IsaacLab 负责场景、控制和采集，LeRobot
负责数据集与 SmolVLA 训练，项目侧负责数据契约、转换、在线 rollout 和诊断。
外部 LeRobot 源码不会被修改。

## 五分钟开始

```bash
git clone <project-url>
cd s4_smolvla_isaaclab
cp .env.example .env          # 修改外部路径
bash run.sh doctor
bash run.sh list-tasks
bash run.sh activate-task drawer_insert_close
bash run.sh sim
```

完整链路：

```bash
bash run.sh record --episodes 10 --headless
bash run.sh convert --overwrite
bash run.sh dataset-check
bash run.sh train
bash run.sh preview --num-frames 20 --device cuda
bash run.sh rollout --deterministic --policy-device cuda
```

## 命令流程简介
1. 查看 CLI

  cd /home/zfy/smolVLA/s4_smolvla_isaaclab

  bash run.sh --help
  bash run.sh record --help
  bash run.sh convert --help
  bash run.sh train --help
  bash run.sh rollout --help

  总入口实现位于 s4_smolvla_isaaclab/run.sh。

2. 配置本机路径

  cp .env.example .env
  vim .env

  重点检查：

  S4_PROJECT_ROOT
  ISAACLAB_ROOT
  ISAAC_ASSET_ROOT
  LEROBOT_ROOT
  SMOLVLA_MODEL_ROOT
  S4_DATA_ROOT
  S4_OUTPUT_ROOT

  然后运行：

  bash run.sh doctor --strict

  每一项都应显示 [OK]。路径解析见 s4_smolvla_isaaclab/s4_pipeline/paths.py，配置解析见 s4_smolvla_isaaclab/s4_pipeline/config.py。

3. 检查并选择任务

  bash run.sh list-tasks
  bash run.sh activate-task drawer_insert_close
  bash run.sh doctor

  确认 active task：

  cat .local/active_task

  任务定义在 s4_smolvla_isaaclab/tasks/drawer_insert_close.py。

  配置分工如下：

  - 场景、dataset、schema：s4_smolvla_isaaclab/configs/tasks/drawer_insert_close.dataset.json
  - 轨迹、随机化、成功条件：s4_smolvla_isaaclab/configs/tasks/drawer_insert_close.scripted.yaml
  - 训练参数：s4_smolvla_isaaclab/configs/tasks/drawer_insert_close.smolvla.yaml

4. 场景审查

  先用 GUI：

  conda activate env_isaaclab
  bash run.sh sim

  重点检查：

  - 抽屉、罐子和机器人位置
  - 三路相机视角
  - 手臂初始状态
  - 抽屉是否可移动
  - TCP 和腕部相机是否跟随机器人

  然后做单轮采集：

  bash run.sh record --episodes 1

  无界面测试：

  bash run.sh record --episodes 1 --headless

  采集入口是 s4_smolvla_isaaclab/scripts/record_dataset.py，任务状态机是 s4_smolvla_isaaclab/tasks/drawer_insert_close_controller.py。

5. 转换和验证

  conda activate smolvla

  bash run.sh convert --overwrite
  bash run.sh dataset-check

  同时验证 checkpoint：

  bash run.sh dataset-check \
    --checkpoint outputs/train/smolvla_drawer_insert_close_v0/checkpoints/360000/pretrained_model

  这会检查：

  - 26D state/action
  - NaN/Inf
  - 20 Hz FPS
  - 时间戳和 frame index
  - 三路视频及尺寸
  - checkpoint feature contract

  实现位于 s4_smolvla_isaaclab/scripts/dataset_check.py。

6. 训练审查

  先检查最终配置，不立即训练：

  cat configs/tasks/drawer_insert_close.smolvla.yaml
  bash run.sh train --help

  开始训练：

  conda activate smolvla
  bash run.sh train

  继续训练：

  bash run.sh train --resume

  先用较小步数测试链路：

  bash run.sh train \
    --steps 100 \
    --save-freq 100 \
    --overwrite-output

  注意：这会使用配置中的正式输出目录，建议调试时先修改任务训练配置中的 output_dir，避免覆盖正式模型。

7. 离线和在线评估

  离线预览：

  conda activate smolvla
  bash run.sh preview \
    --checkpoint outputs/train/smolvla_drawer_insert_close_v0/checkpoints/360000/pretrained_model \
    --num-frames 20 \
    --device cuda

  确定性 rollout：

  conda activate env_isaaclab
  bash run.sh rollout \
    --headless \
    --deterministic \
    --checkpoint outputs/train/smolvla_drawer_insert_close_v0/checkpoints/360000/pretrained_model \
    --policy-device cuda

  诊断输出：

  bash run.sh diagnose outputs/eval/<文件名>_actions.csv

  重点看：

  - raw_jump：策略原始动作跳变
  - fused_jump：融合后动作跳变
  - tracking：下发动作与实际关节位置误差
  - 最终 complete、success、drawer 和 can_z

8. 审查命令实际执行内容

  使用 shell trace：

  bash -x run.sh doctor
  bash -x run.sh train --help

  只追踪关键调用：

  bash -x run.sh rollout --help 2>&1 | less

  搜索命令映射：

  rg -n 'doctor|record|convert|train|rollout|diagnose' run.sh

  检查 Python 入口：

  rg -n 'scripts/.*\\.py' run.sh

9. 代码质量检查

  python3 -m compileall -q s4_pipeline s4_robot tasks data scripts tests
  bash -n run.sh scripts/*.sh environment/*.sh
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
    conda run -n env_isaaclab python -m pytest -q tests
  git diff --check

  确认没有修改 LeRobot：

  git -C /home/zfy/smolVLA/lerobot status --short
  git -C /home/zfy/smolVLA/lerobot rev-parse HEAD

  第一条应无输出。

10. 安全审查

  清理命令默认只预览：

  bash run.sh clean --dry-run

  执行前检查列表，不要直接删除正式数据。完整教程入口是 s4_smolvla_isaaclab/docs/QUICKSTART.md，配置和命令职责见 s4_smolvla_isaaclab/docs/CONFIGURATION.md。

环境安装、外部资源、数据 schema、新任务开发和故障排查见
[文档索引](docs/README.md)。项目不会提交 `datasets/`、`models/`、`outputs/`
或 Isaac assets；clone 后必须按文档单独准备。
