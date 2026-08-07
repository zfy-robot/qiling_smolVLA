# 安装

## 前置条件

- Ubuntu 22.04、NVIDIA GPU 和兼容 Isaac Sim 5.1 的驱动。
- Conda、Git；建议至少 24GB GPU 显存和 100GB 可用磁盘。
- 单独下载 Isaac Sim 5.1 assets、SmolVLM2 基础模型和 S4 robot assets。

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

## SmolVLA 环境

```bash
conda env create -f environment/smolvla.yml
conda activate smolvla
pip install -e "$LEROBOT_ROOT"
```

LeRobot 验证 commit 为 `3f2179f3b69708b6ad009b2e7685dd9d05269ee1`。
安装后回到项目执行 `bash run.sh doctor`。
