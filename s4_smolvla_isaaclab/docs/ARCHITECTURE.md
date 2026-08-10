# 架构

## 模块边界

- `s4_pipeline/paths.py`：`.env`、active task 和所有根路径。
- `s4_pipeline/config.py`：JSON/YAML 插值及 typed project config。
- `s4_robot/`：URDF、关节顺序、6D hand 映射、IK 和 IsaacLab 公共构建。
- `tasks/`：TaskSpec、scene builder、scripted controller、success/randomization。
- `data/`：HDF5 schema/writer 和 LeRobotDataset 转换。
- `scripts/record_dataset.py`：通用 IsaacLab runtime/recorder。
- `scripts/policy_server.py`：唯一 LeRobot/SmolVLA 推理边界。
- `scripts/eval_policy.py`：在线 chunk 融合、插值、执行、视频和诊断。
- `run.sh`：唯一用户 CLI。
- `teleoperation/`：独立 Quest WebXR transport、clutch 映射和 IsaacLab 摇操 runtime。

`TaskModuleSpec` 还声明 `scripted_config` 与 `rollout_kind`。公共 recorder 通过
import path 加载 controller，不再直接 import drawer controller；在线 eval 对
尚未注册 adapter 的任务会明确拒绝，而不是套用错误的 drawer 判据。

## 进程边界

在线 rollout 中，Python 3.11 IsaacLab 进程通过 stdin/stdout JSON-lines 与
Python 3.12 policy server 通信。图片使用 uint8 base64，state/action 为 26D
float。server 调用 LeRobot 官方 preprocessor、`predict_action_chunk()` 和
postprocessor；项目不修改 LeRobot。

Quest 摇操不经过 policy server。Quest Browser 通过 HTTPS/WSS 向独立
`teleoperation/` runtime 发送最新原子 controller frame；runtime 调用公共
Pinocchio DLS IK 和 26D joint mapping。它不导入或修改数据转换、训练和 rollout。

## 配置优先级

CLI 参数 > `.env`/环境变量 > `.local/active_task` >
`configs/active_task.default` > active task JSON/YAML。任务 controller 的轨迹
和判据来自 `<task>.scripted.yaml`，不在 shell 中维护第二份默认值。
