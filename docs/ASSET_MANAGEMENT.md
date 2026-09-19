# 资产管理边界

项目把资产分成两类，避免将许可证不同的内容混在 Git、Docker 镜像或同一个发布许可中。

| 类别 | 本地位置 | 正式来源 | 发布方式 |
|---|---|---|---|
| S4 机器人、LinkerHand O6、项目场景 | `assets/` | ModelScope `assets/` | 按 revision 下载并只读挂载 |
| NVIDIA Isaac Sim 5.1 USD/材质/纹理 | `.s4/isaac-assets/` | NVIDIA 官方资产包/CDN | 用户从 NVIDIA 获取，本地生成最小闭包 |

## 项目资产

ModelScope 中分为两个独立 artifact：

- `assets/my_robot/`：S4 URDF/mesh 和 LinkerHand O6；
- `assets/scenes/`：教程使用的项目场景物体。

`sim_rollout` 会下载两者，`real_rollout` 只下载机器人资产。Compose 将下载结果覆盖挂载到
源码树的 `assets/` 位置，因此镜像中不包含这些二进制文件。

只准备项目资产而不下载模型/数据集：

```bash
docker compose --profile setup run --rm artifacts project_assets \
  --local-dir /artifacts \
  --revision 3686874898fdf908431db487468f21a527507988
```

旧提交已经包含约 103MiB 的 asset blob。ModelScope 发布验证完成后，从 Git 当前版本取消
跟踪 `assets/`；是否进一步重写 Git 历史应作为单独的破坏性迁移决定，不和本次发布混做。

LinkerHand O6 来源是 Apache-2.0 的
`https://github.com/linker-bot/linkerhand-urdf`，其上游许可和署名继续有效。

## NVIDIA Isaac 资产

`.s4/isaac-assets/` 不进入 Git、ModelScope 或 Docker image。NVIDIA 说明 Isaac Sim 的 3D 模型和
纹理属于额外许可组件，并非随 Isaac Sim 源码一起采用 Apache-2.0。项目因此不二次分发。

默认只从 NVIDIA 官方 CDN 下载项目锁定的 231 个文件（约 501 MiB），逐文件校验 SHA256：

```bash
./s4 setup-isaac-assets
```

如果使用者已经下载并解压 NVIDIA 官方 Isaac Sim 5.1 Local Assets Pack，则不再请求网络，
而是从本地提取同一个依赖闭包。传给命令的目录必须直接包含 `Isaac/` 子目录：

```bash
./s4 build sim
./s4 setup-isaac-assets /path/to/Assets/Isaac/5.1
```

`prepare_local_assets.py` 按项目依赖闭包复制所需 USD、MDL 和纹理，并生成包含逐文件大小与
SHA256 的 `.s4/isaac-assets/5.1/manifest.json`。生成服务仅在这一步给目标目录写权限；
正常的 `sim` 服务通过 `S4_ISAAC_ASSETS_DIR` 将它只读挂载。官方完整资产包可保存在项目外，
闭包生成并校验完成后不再参与运行，也不应提交到本项目。

已有正确的 `.s4/isaac-assets/5.1` 时不需要重新生成。本项目当前闭包约 501 MiB；它只在
每台机器首次准备，Docker 重建不会复制或重新下载它。
