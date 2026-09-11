# 需要项目所有者配合的清单

持续更新的总进度、验收证据和严格执行顺序见
[`PROJECT_STATUS.md`](PROJECT_STATUS.md)。本文件保留制品发布范围和所有者输入说明。

不要上传整个 `models/`、`datasets/` 或 `outputs/`。精确发布目录已经生成在被 Git 忽略的
`release/staging/qiling_smolvla/`，当前共 165 个文件、约 7.6GiB，并已通过 SHA256 校验。

## 已确认的发布决定

- [x] GitHub 项目作为 public 教程发布；
- [x] 主项目代码采用 Apache-2.0；
- [x] ModelScope 使用单一 dataset repo：`zfy2qiling/qiling_smolvla`；
- [x] ModelScope 仓库实际可见性已确认是 `public`；
- [x] 仿真正式发布 350k 的 `pretrained_model/`；
- [x] 真机正式发布 300k 的 `pretrained_model/`；
- [x] 不发布 `training_state/`；
- [x] 仿真和真机数据均允许公开；
- [x] 项目机器人和场景资产允许公开发布；LinkerHand O6 保留上游 Apache-2.0 声明；
- [x] NVIDIA Isaac 场景资产不由项目二次分发，改为用户从 NVIDIA 官方源获取；
- [x] 旧 `docker/vendor/kit-exts` 不进入新镜像；Isaac Sim extscache 由官方 pip 源安装。

## 当前构建与发布进度（2026-09-10）

- [x] artifacts 镜像构建和 ModelScope 下载验证；
- [x] 项目资产上传、固定 revision、下载后 tree SHA256 验证；
- [x] NVIDIA Isaac 5.1 最小资产闭包和官方 CDN lock；
- [x] IsaacLab 与 LeRobot submodule 固定；
- [x] sim 镜像构建及 GPU、Python 环境、版本、资产挂载快速验证；
- [x] Isaac Kit headless、camera RGB 和 350k checkpoint pipeline 已分别实测通过；
- [x] 修复后的完整 sim verifier 已取得最终退出码 0；
- [x] 下载轻量 rollout dataset view，并完成 12-step 真实 policy smoke；
- [x] 固定 NVIDIA Kit extension 官方 ZIP SHA256，并完成严格离线 smoke；
- [x] 完成严格断网的完整 deterministic episode，并保存视频、诊断和 summary；
- [x] 下载并校验完整仿真训练集和 `smolvla_base`；
- [x] 构建独立 policy 镜像，镜像内 `pip check` 通过；
- [x] policy CUDA、依赖、模型、contract、Parquet 和全部视频验证通过；
- [x] policy 镜像构建、单卡单步训练 smoke；
- [x] 下载并校验真机 `real_full` 发布工件；
- [x] 真机数据 contract 与 300K checkpoint 离线推理；
- [x] 300K policy server 双请求/RTC smoke test；
- [x] robot 镜像首次构建成功；
- [x] robot 镜像构建及 ROS/qi/Pink/QP/SDK 无硬件 smoke；
- [ ] 连接真机后的相机、ROS feedback、遥操 shadow 与受控 live 验收；
- [x] 从 Git 当前版本取消跟踪 `docker/runtime/` 的 4 个旧评估文件，并取消跟踪两个真实站点配置；
- [x] 固定 ROS 基础镜像 digest，并记录 sim/policy/robot 当前最终 digest；
- [x] 完成根 README 快速开始和 CI 静态门禁；
- [ ] 生成正式 manifest、完成干净 clone 验收、版本 tag 和 GitHub 发布。

## ModelScope 仓库

已创建 `dataset zfy2qiling/qiling_smolvla`。八类制品使用目录隔离，通过固定 revision 和
`allow_patterns` 选择性下载。

六组模型/数据制品加两组项目资产都进入这一个仓库。NVIDIA Isaac 场景资产不上传，由用户
从 NVIDIA 官方源获取；项目机器人和场景资产按所有者授权公开。不要把 token 写入聊天、`.env` 或 Git；使用
`scripts/release/modelscope_release.sh login` 在自己的终端隐藏输入。

## 第三步：维护脚本已准备的上传内容

### 基础 VLM runtime

来源：
`s4_smolvla_isaaclab/models/HuggingFaceTB/SmolVLM2-500M-Video-Instruct`

包含 `model.safetensors`、config、processor、tokenizer 和模型卡；排除：

```text
onnx/
.cache/
.ms_upload_cache
```

预计从 7.4GB 降到约 2.1GB。

### SmolVLA base

来源：`s4_smolvla_isaaclab/models/lerobot/smolvla_base`，约 873MB。排除 `.cache/`，保留
权重、config、pre/post processor 和模型卡。

### 仿真数据集

来源：
`s4_smolvla_isaaclab/datasets/lerobot_data/s4_drawer_insert_close_v4_12phase_serial_acquire`
，约 2.2GB。上传前再次运行 `dataset-check`，并记录 `s4_contract.json` SHA256。

### 仿真 policy

只上传最终选定 step 下的 `pretrained_model/`，不上传 `training_state/`。如需要续训，另建
private resume artifact，不和部署 policy 混合。

### 真机数据集

来源：工作站上的 `s4_real_drawer_right_v1`，约 858MB。发布前检查 contract SHA256，并移除
转换报告中的工作站绝对路径。

### 真机 policy

来源由本机 `S4_REAL_POLICY_SOURCE` 指定；发布目录是
`policies/real/drawer_right_v1/300000/pretrained_model/`，约 865MB。上传前重写便携路径，
但不能改变权重和 contract。

## 第四步：上传后请提供

```text
repo_id:
repo_type:
revision/commit:
visibility:
```

本次公开 artifact revision 已固定为
`3686874898fdf908431db487468f21a527507988`。维护者将继续把本地 tree SHA256 和镜像 digest
写入正式 `release/manifest.yaml`。

## 第五步：硬件信息

在实际仿真/训练主机执行并把非敏感输出保存为文件：

```bash
nvidia-smi --query-gpu=index,name,driver_version,memory.total --format=csv
docker version
docker compose version
nvidia-ctk --version
uname -m
cat /etc/os-release
```

当前工作站的 host preflight 已通过：RTX 4090 24GB、driver 580.159.03；正式发布仍会保留
preflight，让其他用户在构建/运行前得到明确的驱动、GPU、内存和 Container Toolkit 诊断。
