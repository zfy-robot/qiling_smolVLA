# 外部资产

本项目把“大文件的分发”和“代码中的定位”分开：Git 不提交场景资产，但运行时只从
项目内 `local_assets/isaac/5.1` 读取。维护者可把该目录整体压缩后通过云盘分享，别人
解压到同一相对位置即可运行，不依赖维护者机器上的绝对路径。

## 制作资产包

本机先准备完整 Isaac Sim 5.1 资产库，并令 `ISAAC_ASSET_ROOT` 指向含 `Isaac/` 的
`5.1` 根目录，然后运行：

```bash
bash run.sh prepare-assets --verify
```

脚本从任务场景和调试标记入口递归解析 USD 依赖，只复制本项目用到的 USD、贴图和材质到：

```text
local_assets/isaac/5.1/
```

原始 Isaac 目录结构会保持不变，`manifest.json` 记录入口、文件大小和校验值。
`local_assets/` 已在 `.gitignore` 中，执行 `git status` 不会显示这些大文件。
对于 Isaac 5.1 PackingTable 中指向错误目录的贴图引用，脚本只会在所有同名候选
内容完全一致时补到 USD 期望的位置；无法唯一确认时会直接失败，不会猜测替换。
脚本还会显式解析 USD 解析器看不到的 MDL 相对导入和贴图资源，并收集 IsaacLab
调试坐标系使用的 UIElements 资产，避免材质显示为红色、无贴图或
`frame_prim.usd` 缺失。

## 使用别人分享的资产包

把压缩包解压到仓库根目录，使下列文件存在：

```text
local_assets/isaac/5.1/Isaac/Environments/Simple_Warehouse/warehouse.usd
local_assets/isaac/5.1/Isaac/Props/Sektion_Cabinet/sektion_cabinet_instanceable.usd
local_assets/isaac/5.1/Isaac/Props/YCB/Axis_Aligned/005_tomato_soup_can.usd
local_assets/isaac/5.1/Isaac/Props/PackingTable/packing_table.usd
```

随后运行 `bash run.sh doctor`。默认无需设置 `S4_SCENE_ASSET_ROOT`；只有资产包放在
别处时才需要在 `.env` 覆盖它。为了兼容已有工作站，如果项目资产包不存在，
`run.sh` 会临时回退到 `ISAAC_ASSET_ROOT`，但正式分发应使用项目内资产包。

## 其他外部内容

- Isaac Sim 5.1 和外部 IsaacLab checkout。
- LeRobot checkout，默认 `${LEROBOT_ROOT}`。
- SmolVLM2-500M-Video-Instruct，默认 `${SMOLVLA_MODEL_ROOT}`。
- S4 robot URDF/mesh（当前位于可提交的 `assets/my_robot`）。
- 训练数据与 checkpoint。

机器可读清单在 `configs/external_assets.yaml`。资产包不自动联网下载：云盘链接的权限、
版本与校验方式应由维护者在发布时提供，避免程序静默下载到错误版本。
