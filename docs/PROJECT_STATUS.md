# 项目模块化状态与后续执行顺序

> 唯一进度账本。每完成或发现一个步骤，都更新本文件；不要仅依赖聊天记录。
> 最近更新：2026-09-19（Asia/Shanghai）。

## 本版本结束标志

本次以 **v0.1.0 本机完整验证版** 收口。完成条件是：模块化源码与制品发布完成；三个环境
镜像公开且 digest 固定；旧单体大镜像的构建、启动和 Compose 入口从仓库移除；所有用户文档
只描述根目录 `./s4` 与 `compose.yaml`；本机静态及动态验收通过；最终提交的 CI 通过；创建
`v0.1.0` tag 和 GitHub Release。

异机干净 clone、双 GPU DDP 和物理机器人相机/feedback/shadow/live motion 因工期明确延期，
必须在文档中如实标注，但不阻塞本版本发布。延期不等于这些能力已经验收。

## v0.1.1 补丁发布

`v0.1.0` tag 保持不可移动。`v0.1.1` 只修改宿主编排脚本、Compose 默认值、运行时 fallback
与文档，不改变 sim/policy/robot 镜像内环境，因此复用三个已验证 OCI digest，并给相同内容
增加 `v0.1.1` tag。发布门为：干净 clone 问题已修复；GUI 短 rollout 在本地 X11 桌面显示
完整场景并退出码 0；静态门禁通过；GHCR 新标签远端 digest 与 v0.1.0 相同；main、tag 与
GitHub Release 均公开。

## 最终目标

- GitHub 只维护源码、配置、Docker/Compose、教程、lock/manifest 和小型许可证文件；
- IsaacLab、LeRobot 使用固定 commit 的 Git submodule；
- ModelScope 维护模型、数据集、S4 机器人资产和项目场景资产；
- NVIDIA Isaac Sim 官方场景资产不二次分发，由 lock 文件从 NVIDIA 官方 CDN 获取；
- `sim`、`policy`、`robot` 三个职责独立的环境镜像不包含项目源码、数据、模型或场景；
- 宿主 NVIDIA 驱动由 NVIDIA Container Toolkit 在运行时注入，不构建进镜像；
- 新用户通过少量 `./s4` 命令完成 preflight、下载、构建、验证和运行。

## 已完成并有证据的事项

### 源码与制品边界

- [x] 主项目按 Apache-2.0 公开发布，已准备 `LICENSE` 和 `NOTICE`；
- [x] IsaacLab submodule：`zfy-robot/IsaacLab@f764c12a5ccf5cc6997de699653b4bb70e56a3f7`；
- [x] LeRobot submodule：`3f2179f3b69708b6ad009b2e7685dd9d05269ee1`；
- [x] ModelScope public dataset repo：`zfy2qiling/qiling_smolvla`；
- [x] 固定 ModelScope revision：`3686874898fdf908431db487468f21a527507988`；
- [x] 165 个发布文件上传成功，失败数为 0；
- [x] `sim_rollout` 下载成功：112 个远端文件，111 个内容文件通过 SHA256；
- [x] 仿真采用 350K policy，真机采用 300K policy，不发布 `training_state/`；
- [x] Git 当前版本已移除 84 个 `assets/` 文件，运行时从 ModelScope 只读挂载；
- [x] NVIDIA Isaac 5.1 最小闭包：231 个文件、523,528,659 bytes，lock 中 SHA256 已验证；
- [x] Miniforge installer 已固定版本和 SHA256，并支持宿主缓存/断点下载；
- [x] Docker build context 已排除 models、datasets、outputs、assets、local assets、旧 Kit exts。

### 宿主和仿真环境

- [x] `./s4 preflight` 在当前主机通过，状态为 `HOST READY`；
- [x] 当前验证硬件：RTX 4090 24GB，NVIDIA driver 580.159.03；
- [x] sim 镜像构建成功：`s4-smolvla-sim:dev`；
- [x] 最终 sim 镜像已于 2026-09-11 重建，镜像内 runtime entrypoint 与仓库 SHA256
  `56aead31781bf3d54de0371561e0a2086a5bba3c2cabe59c3d409b363be0caf0` 一致；
  - OCI manifest：`sha256:954140a9d6748fecc9b9b6f80e84fcd60171629e017ec5a96cf6d142e305b84f`；
  - OCI manifest list / local image ID：
    `sha256:e0fb24a132c27ef271e20fd234fa215d34cf2e331296010f3f92d0ee55288c44`；
  - image config：`sha256:47dbe4c85fa75f90dee009c63e8198a80707f026cfc46b35625af014dac653c5`；
  - Linux amd64，unpacked size 22,576,256,457 bytes；
- [x] 镜像内 PyTorch 2.7.0+cu128、CUDA 12.8、Isaac Sim 5.1.0.0、IsaacLab、LeRobot 0.6.1 导入通过；
- [x] NVIDIA Vulkan renderer 实测识别 RTX 4090 和 driver 580.159.03；
- [x] 项目 doctor 通过：Isaac 资产 231/231、26D state/action、三相机契约、频率和两个 Python 环境均正确；
- [x] 350K checkpoint 已离线加载 config、tokenizer、preprocessor、postprocessor；
- [x] headless renderer 已实际启动，TiledCamera 已产生 RGB `(1, 128, 128, 3)`；
- [x] checkpoint 中 4 个 JSON 已进行便携路径检查，无宿主绝对路径残留。

## 当前正在收口的事项

- [x] 重新执行完整 `./s4 verify sim` 并取得最终退出码 0（2026-09-10）。
  - 已修复 `ldconfig | grep -q` 在 `pipefail` 下产生 141 的误判；
  - 已修复专用相机 smoke test 在成功后卡于 `SimulationApp.close()` 的问题；
  - 已把 XDG runtime 改为容器内、owner 正确的临时目录；
  - 静态检查、Compose 展开、Python 编译和 checkpoint 4 JSON 检查均已通过；
  - 实测最终标记为 `[OK] rollout runtime verification passed`、`VERIFY_RC=0`。
- [x] 下载 rollout 所需的轻量仿真数据视图：`meta/** + data/**`，明确排除视频；
  - ModelScope 下载 118 个远端文件，117 个内容文件校验通过，`SETUP_RC=0`；
  - rollout 新增部分包含 28,921,764-byte Parquet 与完整 meta；
  - contract SHA256 为 `d81439c113ce6ed8b0f594d91d9823b6c7465c837bd8579901b9c7fbc91d6266`。
- [x] 12-step 真实集成 smoke：完整场景、三相机、350K GPU policy、12 阶段 schedule、一次推理；
  - policy schedule 从 200/200 episodes 恢复为 12 phases、599 frames；
  - summary 写入 `outputs/eval/rollout_20260910_021048_det_ckpt350000/summary.json`；
  - `complete=false/success=false` 符合 12-step 预期，最终 `SMOKE_RC=0`。
- [x] 固定 IsaacLab 额外需要的两个 NVIDIA Kit extension 官方 ZIP SHA256，并验证离线启动；
  - 第一次 offline smoke 已证明缓存内容存在，但发现 Kit 在 registry disabled 时不会自动搜索全局 cache；
  - Kit 107.3 在此启动路径未注册等号形式，已改为两参数形式
    `--ext-folder /workspace/cache/home/.local/share/ov/data/exts/v2`；
  - 专用禁网 GPU 验证已实际启用 URDF Importer 2.4.31、导入 native interface，并解析
    `omni.kit.pip_archive`；
  - 完整禁网 12-step rollout smoke 已通过，`OFFLINE_RC=0`，输出目录为
    `outputs/eval/rollout_20260910_023401_det_ckpt350000`；完整日志中未出现 registry 同步、
    CDN 下载或 extension dependency resolution failure。
- [x] 完整任务级仿真 rollout，保存成功/失败指标和日志；
  - 严格禁网单回合完成：`complete=true`、`success=false`、`failure_reason=null`；
  - 仿真时间 36.95 秒、墙钟时间 174.93 秒，当前主机约为 0.21x realtime；
  - 产出 50,598,950-byte AVI、1,915,211-byte CSV、373,857-byte PNG 和 summary；
  - policy 未完成任务：罐子最终位于 `(0.540, -0.122, 1.151)`，不在抽屉范围内；该结果
    作为 350K checkpoint 基线，不判定为环境失败。

## 后续阶段（严格按顺序）

### 1. 完成 sim 动态验收

- [x] 完整 runtime verify 退出码 0；
- [x] 运行短仿真 smoke，确认场景、机器人、三相机、policy 子进程、26D 动作和输出目录；
- [x] 将 `isaacsim.asset.importer.urdf` 2.4.31 与配套 `omni.kit.pip_archive` 固定为
  NVIDIA 官方下载 + 本地持久缓存；公开仓库/ModelScope/镜像不再分发其二进制；
  - lock：`release/isaac_extensions_5.1.lock.json`；
  - 两个 archive 与 3344 个安装文件已完整复验；
- [x] 在 `S4_KIT_OFFLINE=1` 和 Compose `network_mode: none` 下复验 smoke，运行阶段没有
  registry/CDN 请求；
- [x] 运行一个完整 deterministic episode；
- [x] 记录本机完整 episode 耗时；首次冷启动约 50 秒，任务墙钟约 175 秒；显存峰值仍需
  在后续训练 smoke 中统一采集；
- [x] 所有镜像内脚本变更完成后重建最终 sim 镜像并记录 digest；
- [x] 对最终重建的 sim 镜像执行完整 `./s4 verify sim`；2026-09-11 最终日志确认 CUDA、
  NVIDIA Vulkan、231 个资产、两个 Python 环境、checkpoint processor、Isaac headless renderer
  和 RGB `(1, 128, 128, 3)` camera frame 全部通过，最终标记
  `[OK] rollout runtime verification passed`。

### 2. 构建并验收 policy 环境

- [x] 下载并验证 `sim_training` 制品：50 个远端条目、49 个内容文件，`SETUP_RC=0`；
  - 本地 artifact 根目录约 5.9GiB；
  - 完整仿真训练集约 2.2GiB，20 个文件，其中三路相机共 13 个 MP4；
  - `smolvla_base` 约 873MiB，config、权重和 processor 文件齐全；
- [x] 构建 `s4-smolvla-policy:dev`；
  - LeRobot 0.6.1 wheel 构建成功，`pip check` 输出 `No broken requirements found`；
  - 首次构建的 manifest list
    `sha256:14e7559da83cc043b1c805f484e72e1a39fe8760fea3a830101fc48efe8cd742` 已由
    entrypoint 修正版取代；
  - 当前 OCI manifest：`sha256:757f6643bc5f840f008628e0b8c1e12a5394776a7b5d4ef9a0e65150b9f53b75`；
  - 当前 OCI manifest list：`sha256:9f2bced045e647c1ca210bc37a217f9ac43f3c8ad15e7764224af36fa266fedb`；
  - 当前 image config：`sha256:f0842bf040ce0f00ab78ec49212fdb96e800e46da45cb5174fe17212a88923e4`；
- [x] policy runtime verify 最终 `VERIFY_RC=0`；
  - 首次验证暴露 Compose 未激活 `/opt/conda/envs/smolvla/bin`；固定 `PATH` 和
    `CONDA_PREFIX` 后复验通过；
  - CUDA tensor 在 RTX 4090 / CUDA 12.8 上通过；
  - PyTorch 2.7.0+cu128、LeRobot 0.6.1、Transformers 5.5.4、Accelerate 1.14.0、
    Datasets 5.0.0、PyArrow 25.0.0、PyAV 15.1.0 导入通过；
  - 完整数据集为 200 episodes / 120,403 frames / 20Hz / 26D，13 个视频全部首尾解码并
    校验总帧数；
  - policy cache 已从 sim cache 隔离，避免不同容器 UID 产生不可写缓存警告。
  - 后续单元测试发现公共 entrypoint 会把 Conda base `python3` 置于 policy Python 之前；正式
    `run.sh train` 会自行修正，但裸容器命令不正确。已修复为根据 `S4_SMOLVLA_PYTHON` 自动激活
    policy 环境；训练脚本及独立 smoke 输出保护测试为 9/9 通过；缓存式重建后，默认
    `python3`、`lerobot-train`、`accelerate` 均实测来自 `/opt/conda/envs/smolvla/bin`。
- [x] 验证 CUDA、LeRobot、Transformers、Accelerate 和本地 VLM/checkpoint 加载；
- [x] 验证仿真训练数据 contract、Parquet 和视频解码；
- [x] 做单步/极短训练 smoke，验证 optimizer、反向传播、checkpoint 写入；
  - 1 step 实际训练完成，训练阶段速度约 2.21 step/s；
  - 独立输出目录为 `.s4/outputs/train/policy_smoke_20260910T061420Z_2729614`，约 1.3GiB；
  - `checkpoints/000001` 与 `last -> 000001` 均存在；权重为 906,781,640 bytes，optimizer
    state 为 412,797,404 bytes，scheduler、RNG 与 `training_step.json` 均完整；
  - `training_step.json` 记录 `step=1`、`num_processes=1`、`batch_size=1`；数据 contract
    与发布版本逐字节一致；
  - 14 次采样的 GPU 显存峰值为 4,994MiB；输出目录归宿主用户所有。
- [x] 多卡启动逻辑测试完成；当前主机仅暴露 1 张 GPU，故不执行虚假的本机 DDP 验收；
  - 训练脚本测试 9/9 通过，包含 Accelerate DDP launcher 参数与输出隔离；
  - 将来在 2 张以上 GPU 的发布主机上补做真实 DDP 性能/通信验收，不阻塞单卡教程发布。
- [x] 下载并校验 `real_full`：134 个远端条目、133 个内容文件，`SETUP_RC=0`；
  - 包含真机数据集、300K policy、VLM/SmolVLA base 和机器人资产；
  - 数据集与部署 manifest 的 contract SHA256 均为
    `792de8a5373a1eb284febeaade03b9ae21adf880065ab13d8281d966bda90f68`；
  - 两者的 LeRobot commit 均为 `3f2179f3b69708b6ad009b2e7685dd9d05269ee1`，8D state/action
    与两相机键静态一致；
  - 发布数据验证不再强制依赖维护者的 raw capture 目录；300K checkpoint 验证不再写入只读制品；
  - 真机协议、server session 和训练 preflight 快速测试 8/8 通过。
- [x] 验证真机发布数据与 300K checkpoint 离线推理；
  - 数据集为 266 episodes / 81,374 frames / 20Hz / 8D；
  - head 与 wrist_right 两路 AV1 视频均完整解码 81,374 帧；
  - checkpoint 严格加载，部署 provenance、两相机键和 8D contract 通过；
  - 使用发布数据样本完成 GPU 离线推理，action chunk 为有限值 `(50, 8)`；
  - 最终标记 `[OK] real dataset and 300K checkpoint runtime verification passed`。
- [x] 验证 300K policy server 启动及两个真实 ZMQ/RTC 请求；
  - server 仅绑定容器回环 `127.0.0.1:15555`，contract SHA256 与发布数据一致；
  - request 0/1 均返回有限 `(50, 8)` chunk，推理时间分别约 322.5ms / 113.2ms；
  - RTC reset、`rtc_source_request_id=0` 与 `leftover_start_index=1` 均通过；
  - 最终标记 `[OK] real policy ZMQ protocol`，服务在测试后自动关闭。
- [x] 记录并发布最终 policy image digest；远端不可变引用见 `release/manifest.yaml`。

### 3. 构建并验收 robot 环境

- [x] 固定 ROS 2 Humble/Jammy 基础镜像 index digest：
  `sha256:1813d3c85d7f96ff7d3012d865204583255740182db5d0065f8f8cd029a83138`；
- [x] 完成 robot Dockerfile 发布边界审计；
  - 镜像内 qi workspace 固定为 `/opt/s4/qi_ws`，不再依赖宿主生成的 `ros_ws/install`；
  - Python 3.10 硬件依赖隔离在 `/opt/s4/hardware_python`，固定 NumPy 1.26.4，避免覆盖
    ROS Humble Pinocchio；
  - ROS/Pink/QP/RealSense/OpenCV/ZMQ/HDF5 共 12 个直接 Python 依赖全部固定版本；
  - 默认启动为 shell，不创建 ROS publisher，不触发机器人动作。
- [x] 构建 `s4-smolvla-robot:dev`；
  - ROS Humble、Pinocchio 4.0.0、CycloneDDS 与 qi messages 构建成功；
  - 隔离目录成功安装 12 个固定直接依赖及其传递依赖；
  - 当前 OCI manifest：`sha256:3a1d24024211af313fc938853235519f3b27555c859eaf8b731844ec2c1dce7b`；
  - 当前 OCI manifest list：`sha256:64bbcd1a6d89c6ee8cfe946c7b2e9c339b346a41db6b41c0d45cc6af68e3b411`；
  - 当前 image config：`sha256:c944625fa0cc11a2cfb41ec45ed4f75a407abf911150e17d5090b1aff0b83235`；
  - 完成入口和 verifier 修复后已缓存式重建，并由下方正式 GHCR digest 取代早期本地 digest。
- [x] 无硬件模式验证 ROS、消息包、相机 SDK、USB 枚举、配置解析和网络协议；
  - 首次运行在镜像入口加载 ROS 时触发 `AMENT_TRACE_SETUP_FILES: unbound variable`；根因是
    ROS Humble 官方 setup 脚本不兼容 shell nounset，并非 ROS/依赖缺失；
  - 已让入口在加载 ROS 时关闭 nounset，并让当前 verifier 绕过旧入口以继续验收；最终镜像
    重建会固化该修复。
  - 第二次失败仅因绕过入口时遗漏 `S4_HW_TELEOP_RUNTIME_RESOLVED=system`；补齐后维护者已
    完整复验通过；
  - Python 3.10.12、NumPy 1.26.4、ROS Pinocchio 4.0.0、qi schema、CycloneDDS、quadprog、
    DAQP、FK 和配置加载均通过；
  - 320 次 Pink QP 实测 p50=0.1853ms、p99=0.2488ms，远低于 5ms 门限；
  - 最终输出 `[OK] robot no-hardware runtime verification passed (no ROS publishers created)`；
  - 最终重建后已通过正常 entrypoint 复验；RealSense SDK 只读枚举成功，当前未连接设备，
    因此 `devices=0`，不误报为相机硬件验收。
- [ ] 连接真机后依次执行只读 preflight、相机、关节 feedback、遥操 shadow；
- [ ] 只有人工确认急停、限位、方向和频率后，才允许 5 秒低风险 live motion；
- [ ] 验证 robot client 与独立 policy-server 的 300K rollout；
- [x] 记录当前最终 robot image digest；
  - OCI manifest：`sha256:47d4ed39b263ca9c17d80dc6177fa841cda767beaa6256c55a62a7711c140e8a`；
  - OCI manifest list：`sha256:6a36352a87939ec296a663343a8949c9685ef8fc0af0d3e2f63a599bf1d0b1b5`；
  - image config：`sha256:e16e43e5f2d55729709b2d61591f9e152bc2b9c54d15a4f3143897e412169c20`。

### 4. Git 清理和正式发布

- [x] 从 Git 当前版本取消跟踪 `docker/runtime/` 的 4 个旧评估文件；文件已确认仍保留在本地；
- [x] 审计 Git 中大文件、绝对路径、token、IP、相机序列号和主机专用配置；真实
  `ros_env.sh` 与 `cameras.yaml` 已取消跟踪并确认仍保留在本地；
- [x] 把主机/机器人差异拆成公开 example 与被忽略的本地 override；相机模板通过
  `S4_CAMERA_*_SERIAL` 展开，ROS 与相机真实配置均已加入 `.gitignore`；
- [x] 完成正式 `release/manifest.yaml`；
  - [x] 模块化源码快照已提交：`86fab172e974c06d65828f228ac030bb1cee8c4f`；
  - [x] `v0.1.0` manifest candidate 已生成，包含三个本地 OCI digest、ModelScope revision、
    submodule commit、NVIDIA locks、artifact tree hash 和实际验证状态；
  - [x] 将三个镜像推送 GHCR、核对远端 digest 后，把 candidate/pending 状态改为正式发布；
    - 首次 robot push 在创建 package 前被 GHCR 拒绝：`permission_denied: The token provided
      does not match expected scopes`；没有 layer 上传成功；
    - 必须使用 token 所属个人 GitHub 用户名登录，并使用 classic PAT 的 `write:packages`；若
      `zfy-robot` 是组织而非个人用户，不能把组织名当登录用户名；
    - package 关联仓库和 Public 可见性只能在首次成功 push、package 创建后设置；
    - [x] robot `v0.1.0` 已成功推送；远端 OCI index digest
      `sha256:6a36352a87939ec296a663343a8949c9685ef8fc0af0d3e2f63a599bf1d0b1b5`
      与本地/manifest 一致；使用不含登录凭据的临时 Docker config 匿名查询成功，Public 生效；
    - [x] 推送并匿名验证 policy；
      - 首次 policy push 已复用大部分远端 layer，但上传 blob `7c7efac...` 时失败；根因是
        Docker daemon 的 HTTPS proxy `127.0.0.1:7890` 重置 PUT 连接，不是 GHCR 权限或镜像
        问题；shell 对 GHCR 直连实测约 0.47 秒；
      - Docker daemon 的 `NO_PROXY` 已加入
        `ghcr.io,.ghcr.io,pkg-containers.githubusercontent.com,.pkg-containers.githubusercontent.com`
        并完成重启；`docker info` 已确认配置生效；
      - policy 第二次幂等重试期间，上传进程与 HTTPS 发送连接曾保持存活；大 layer 上传期间
        Docker CLI 不输出百分比，因此日志长时间停留在 `Waiting`；随后父 shell 与推送进程一并
        消失，Docker daemon 无重启、OOM 或 push 错误记录，远端标签仍为 `not found`；下一次
        使用脱离终端会话的后台 runner，最终以记录在日志中的 `PUSH_RC` 和远端 digest 为准；
      - [x] 后台 runner 重试成功，`PUSH_RC=0`；远端 OCI index digest
        `sha256:9f2bced045e647c1ca210bc37a217f9ac43f3c8ad15e7764224af36fa266fedb`
        与本地/manifest 一致，amd64 manifest 为
        `sha256:757f6643bc5f840f008628e0b8c1e12a5394776a7b5d4ef9a0e65150b9f53b75`；
      - [x] 所有者已把 policy Package 关联主仓库并改为 Public；使用无登录凭据的临时 Docker
        config 匿名查询成功，返回的 index/amd64 digest 与本地及 manifest 一致；
    - [x] 推送并匿名验证 sim；
      - [x] 后台 runner 上传成功，`PUSH_RC=0`；远端 OCI index digest
        `sha256:e0fb24a132c27ef271e20fd234fa215d34cf2e331296010f3f92d0ee55288c44`
        与本地/manifest 一致，amd64 manifest 为
        `sha256:954140a9d6748fecc9b9b6f80e84fcd60171629e017ec5a96cf6d142e305b84f`；
      - [x] 所有者已把 sim Package 关联主仓库并改为 Public；使用无登录凭据的临时 Docker
        config 匿名查询成功，返回的 index/amd64 digest 与本地及 manifest 一致；
    - [x] `release_status: released`、`images.publication_status: public`，三个镜像各自记录
      `anonymous_pull_verified: 2026-09-11`；
- [x] 完成根 README 的最短教程、部署拓扑、安全门禁、制品边界和网络故障排查；
- [x] 增加 CI：shell/Python/Compose 静态检查、lock、submodule、敏感信息和无大文件检查；
  取消跟踪后，本地完整门禁已通过：494 个 tracked paths；
- [ ] **仍延期**：在另一台物理设备执行教程级复现；
- [x] 在当前工作站使用独立的 `v0.1.0` 干净 clone 完成公开消费路径复验：固定 digest 的三个
  GHCR 镜像、165 个 ModelScope 条目、231 个 Isaac 资产、3344 个 Kit extension 文件、sim
  runtime、禁网 rollout、policy verify/单步训练、真机 300K 离线推理/ZMQ 协议和 robot
  无硬件验证均可运行；
  - 首次复验发现 `setup tutorial_all` 可让 Docker daemon 把尚不存在的 Isaac bind source
    创建为 `nobody:nogroup`，普通用户随后无法写入；默认缓存已迁移到用户拥有的
    `.s4/isaac-assets`，`./s4` 在 Compose 前创建并检查所有目录；
  - 首次 `verify sim` 发现被 ModelScope 资产覆盖的嵌套目标
    `s4_smolvla_isaaclab/assets` 在干净 clone 中不存在，Docker 又无法在只读源码挂载内创建；
    `./s4` 现在预建该忽略目录，并对不可写/非目录情况给出明确错误；
  - 干净复验的完整禁网 rollout 在第 4 阶段因抽屉只打开 0.035m、未达到 0.080m gate 而
    正常提前结束，`complete=false/success=false`、进程退出码 0；这属于 350K policy 结果，
    不改写先前发布基线，也不能表述为策略成功；
  - 新增 `./s4 rollout sim-gui`，通过私有 X11 cookie 和宿主 X11 socket 显示 Isaac Sim，
    headless/offline 入口保持默认且不使用宽泛的 `xhost +`；首次 GUI smoke 暴露全局固定的
    headless EGL Vulkan ICD 会导致 GUI experience 在启动时段错误，GUI 入口现显式切换到由
    NVIDIA Container Toolkit 注入的 `/etc/vulkan/icd.d/nvidia_icd.json`（GLX）；第二次测试
    已成功创建窗口和 Vulkan renderer，随后发现主仓库仍只有旧位置的资产缓存，新入口现会在
    新默认目录尚无完整资产时自动复用完整的 legacy cache，不复制也不重新下载。
  - [x] 第三次 GUI smoke 加载完整资产后显示窗口与任务场景，执行 120 个物理步并以
    `GUI_RC=0` 结束（2026-09-19）。
- [x] 创建主项目模块化源码快照 commit；IsaacLab fork commit 已存在远端；
- [x] 正常 fast-forward 推送主项目 `main` 至许可证修复 commit `39f19fc`；公开远端 HEAD 核对一致；
- [x] GitHub Actions `static-release-checks`（run `34567064694`）完成且结论为 `success`；
- [x] 合入 NVIDIA 许可证显式接受参数文档修复并推送 main；
- [x] 从仓库删除旧单体大镜像的 Dockerfile、Compose、构建、初始化和启动入口；
- [x] 重写部署、复现、课程、模块和 Docker 文档，仅保留模块化链路；
  - 课程编号保持 6.1/6.2/6.3，内容重组为“VLA 理论与统一契约 → 仿真/真机两条完整链路 →
    两条链路的代码、进程和容器实现”；
  - 仿真事实已对照 26D、三相机、20/120Hz、27/12 phases、350K 和本地 policy 子进程；
  - 真机事实已对照 8D、两相机、20/30Hz、因果对齐、ZMQ v4、RTC、双 live 门和 300K；
  - 修复真机 rollout 日志仍写一次性容器 HOME 的实现：现在统一写入
    `${S4_OUTPUT_ROOT}/real_rollouts`，Compose 下持久化到 `.s4/outputs/real_rollouts`；
  - 其余 README、复现、pipeline、真机手册、资产/项目清单和 release 文档已交叉审计；
  - 文档收口后的模拟全暂存静态门禁通过（489 个 tracked paths），Compose/shell/Python 检查
    通过；宿主无 Torch/msgpack 的纯逻辑测试 44 项通过，正式 policy 容器中的协议、配置与
    import-boundary 测试 5/5 通过；本地 Markdown 相对链接检查 29 份文档通过。
- [x] 提交并推送本次旧链路退役与文档收口变更：
  `6e95541b6cda2975f90fccfa59285363e552ff6f`；GitHub Actions run `34571153032` 的
  `validate` job 于 2026-09-11 完成，结论为 `success`；
- [ ] 创建版本 tag 和 GitHub Release。

## 项目所有者下一步只需执行

三个镜像均已上传、公开并通过匿名 digest 验证，最终文档/旧链路收口提交及其 CI 也已通过。
当前只剩：提交这次状态账本更新、确认最后一次 CI、创建并推送 annotated tag、创建 GitHub
Release。异机和物理机器人验证已移入后续版本，不再作为本次标签的前置门槛。具体命令由
维护者在本地门禁通过后逐条提供。

## 变更与长任务协作规则

- 维护者：读代码、静态检查、修改脚本、准备命令、分析日志、更新本状态文件；
- 项目所有者：执行镜像构建、GB 级下载上传、Isaac Sim 启动、训练和真机验证；
- 每条长任务命令都使用 `set -o pipefail` 与 `tee /tmp/<明确名称>.log`；
- 每次只推进一个验收门，失败时先修根因并重跑该门，不跳到后续环境；
- 不把 ModelScope token、代理密码、设备私密标识或本地 `.env` 提交到 Git。
