# Release manifest

`manifest.example.yaml` 定义代码、镜像、硬件支持线和 ModelScope 制品之间的唯一映射。

发布规则：

1. 复制 example 为 `manifest.yaml`；
2. 所有 `TODO` 替换为不可变 commit、revision、digest 或 SHA256；
3. CI 拒绝仍包含 `TODO`、dirty source、浮动 tag 或不匹配 contract 的发布；
4. `manifest.yaml` 随 Git release tag 提交；
5. 本地 `.env` 只决定挂载位置，不能覆盖 artifact 身份和版本。

在模块化 Docker/ModelScope 同步脚本完成前，example 仅作为数据结构，不应被当成可运行
release。

