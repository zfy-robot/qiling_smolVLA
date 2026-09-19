# S4 SmolVLA v0.1.1

`v0.1.1` 是公开复现与本地可视化补丁版。模型、数据、checkpoint、submodule 和三个环境镜像
的内容均不改变；发布继续固定 v0.1.0 已验证的 OCI digest 与 ModelScope revision。

## 修复

- `./s4` 在启动 Compose 前以当前宿主用户创建并检查 bind mount 目录；
- Isaac 官方资产的新默认缓存迁移到 `.s4/isaac-assets`，避免 Docker daemon 在干净 clone 中
  创建 `root`/`nobody` 目录；
- 自动创建被 ModelScope 资产覆盖的 `s4_smolvla_isaaclab/assets` 空挂载点，避免 Docker 在
  只读源码挂载内创建目标时报错；
- 对已有 `local_assets/isaac` 完整缓存自动向后兼容，不复制、不重新下载；
- `.env.example` 不再把 UID/GID 固定为 1000，由 `./s4` 自动使用当前用户身份；
- 权限、路径类型、DISPLAY、X11 cookie 等前置条件失败时给出可操作的错误信息。

## GUI rollout

新增本地 Linux 桌面入口：

```bash
./s4 rollout sim-gui
```

入口使用私有 X11 cookie，不要求 `xhost +`，并只在 GUI 路径把 Vulkan ICD 从 headless EGL
切换到 NVIDIA GLX。RTX 4090 / driver 580.159.03 / X.Org 1.21.1.4 上已完成 120-step 窗口、
完整场景与策略 rollout smoke，退出码为 0。无本地真实显示器的服务器仍应使用 headless 或
offline 入口。

## 独立 clone 复验

在同一工作站的独立 `v0.1.0` clone 中重新验证了固定 GHCR digest、ModelScope 165 个条目、
231 个 Isaac 资产、3344 个 Kit extension 文件、sim runtime、禁网 rollout、policy 单步训练、
真机 300K 离线推理/ZMQ 协议和 robot 无硬件检查。该结果不等于另一台物理设备兼容性验证。

完整禁网 rollout 的一次复验在抽屉 gate 处正常提前结束，结果为
`complete=false/success=false`。这属于发布的 350K policy 行为，不是容器或下载失败；本版本
不宣称策略任务成功率。

## 不变内容

- ModelScope：`zfy2qiling/qiling_smolvla@3686874898fdf908431db487468f21a527507988`；
- sim image digest：`sha256:e0fb24a132c27ef271e20fd234fa215d34cf2e331296010f3f92d0ee55288c44`；
- policy image digest：`sha256:9f2bced045e647c1ca210bc37a217f9ac43f3c8ad15e7764224af36fa266fedb`；
- robot image digest：`sha256:6a36352a87939ec296a663343a8949c9685ef8fc0af0d3e2f63a599bf1d0b1b5`。

物理机器人相机、ROS feedback、shadow/live motion，另一台物理设备复现和真实双 GPU DDP
仍未验收，不应被表述为已通过。
