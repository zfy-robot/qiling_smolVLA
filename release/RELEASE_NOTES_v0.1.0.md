# S4 SmolVLA v0.1.0

首个公开的模块化、可复现教程版本。本版本的正式状态是 **本机完整验证版**。

## 发布内容

- GitHub：项目源码、配置、教程、Docker/Compose、lock 与 manifest；
- IsaacLab：`zfy-robot/IsaacLab@f764c12a5ccf5cc6997de699653b4bb70e56a3f7`；
- LeRobot：`3f2179f3b69708b6ad009b2e7685dd9d05269ee1`；
- ModelScope：`zfy2qiling/qiling_smolvla@3686874898fdf908431db487468f21a527507988`；
- 仿真策略：350K；真机策略：300K；不发布 `training_state/`。

三个公开的 linux/amd64 环境镜像：

- `ghcr.io/zfy-robot/qiling-smolvla-sim@sha256:e0fb24a132c27ef271e20fd234fa215d34cf2e331296010f3f92d0ee55288c44`
- `ghcr.io/zfy-robot/qiling-smolvla-policy@sha256:9f2bced045e647c1ca210bc37a217f9ac43f3c8ad15e7764224af36fa266fedb`
- `ghcr.io/zfy-robot/qiling-smolvla-robot@sha256:6a36352a87939ec296a663343a8949c9685ef8fc0af0d3e2f63a599bf1d0b1b5`

镜像只维护环境。源码在运行时从 Git checkout 只读挂载；模型、数据集、checkpoint 与项目资产
从 ModelScope 下载后挂载；NVIDIA 官方资产与 Kit extensions 由用户接受许可后从官方源获取；
宿主 NVIDIA 驱动由 Container Toolkit 注入。

## 已验证

- RTX 4090 24GB、NVIDIA driver 580.159.03、Linux x86_64；
- Isaac Sim 5.1 headless Vulkan、相机 RGB、IsaacLab 场景与完整离线 episode；
- SmolVLA/LeRobot CUDA runtime、完整数据、单步训练与 checkpoint 写入；
- 真机 300K checkpoint 离线推理及双请求 ZMQ/RTC policy server 协议；
- robot 镜像 ROS 2 Humble、qi、Pink/QP、RealSense SDK 的无硬件只读验证；
- 三个 GHCR 镜像均完成匿名 digest 验证。

仿真完整 episode 的环境链路完成，但发布的 350K 策略未成功把罐子放入抽屉；这是公开基线
结果，不应被解读为策略成功率验收。

## 尚未验证

- 尚未在另一台设备上完成从 tag 开始的干净 clone 复现；
- 尚未进行真实双 GPU DDP；
- 尚未连接物理机器人完成相机、ROS feedback、shadow rollout 或 live motion。

这些项目因工期延期，不阻塞本机验证版发布，也不能被宣称为已通过。真机 live motion 必须遵守
文档中的人工急停、限位、方向、工作区和 publisher 唯一性门禁。

## 迁移说明

旧的单体大镜像构建与启动链路已删除且不兼容。请勿再使用旧 Dockerfile、旧 Compose 或旧
runtime 初始化方式。新用户从 `./s4 preflight`、`./s4 pull ...` 和 `./s4 setup ...` 开始，
完整步骤见根目录 README。

NVIDIA Isaac Sim、官方资产和 extensions 不随本项目二次分发；使用者必须自行阅读并接受
NVIDIA 许可条款。
