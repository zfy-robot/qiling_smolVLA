# 安装

## 前置条件

- Ubuntu 22.04、NVIDIA GPU 和兼容 Isaac Sim 5.1 的驱动。
- Conda、Git；建议至少 24GB GPU 显存和 100GB 可用磁盘。
- 获取本项目单独分发的 Isaac 场景资产包、SmolVLM2 基础模型和 S4 robot assets。

## IsaacLab 环境

```bash
conda env create -f environment/isaaclab.yml
conda activate env_isaaclab
# 按 IsaacLab 官方方式安装 Isaac Sim 5.1 与外部 IsaacLab checkout
cd "$ISAACLAB_ROOT"
./isaaclab.sh --install
```

本项目验证版本为 Isaac Sim 5.1.0.0、IsaacLab 0.54.2。IsaacLab 必须作为
外部 checkout 使用，不能复制进项目。

## 场景资产

将配套资产包解压后保持以下目录结构：

```text
local_assets/isaac/5.1/Isaac/Environments/...
local_assets/isaac/5.1/Isaac/Props/...
local_assets/isaac/5.1/manifest.json
```

`local_assets/` 不进入 Git，代码通过项目默认相对位置引用。如果维护者本机已有完整
Isaac 5.1 资产库，可用下面的命令重新生成最小依赖闭包：

```bash
ISAAC_ASSET_ROOT=/path/to/Assets/Isaac/5.1 bash run.sh prepare-assets --verify
```

脚本会复制当前两个任务所需的 USD、贴图和材质，并写入带文件清单与 SHA-256 的
`manifest.json`，便于将整个 `local_assets` 目录通过云盘单独分发。

## SmolVLA 环境

```bash
conda env create -f environment/smolvla.yml
conda activate smolvla
pip install -e "$LEROBOT_ROOT"
```

LeRobot 验证 commit 为 `3f2179f3b69708b6ad009b2e7685dd9d05269ee1`。
安装后回到项目执行 `bash run.sh doctor`。
