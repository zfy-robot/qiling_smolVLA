# Release manifest

`manifest.yaml` 定义本次 release 的代码、镜像、硬件支持线和 ModelScope 制品之间的唯一映射；
`manifest.example.yaml` 仅用于创建下一版本。

发布规则：

1. 先创建不含 manifest 的源码快照 commit；
2. manifest 的 `source.project.commit` 固定到该快照，避免 Git commit 自引用；
3. 所有镜像和制品使用不可变 digest/revision，不用 `latest`；
4. CI 拒绝 `TODO`、错误 SHA、漂移 submodule、绝对主机路径和大文件；
5. GHCR 推送完成并核对远端 digest 后，将 `release_status` 和
   `images.publication_status` 改为正式状态，再创建 release commit/tag；
6. 本地 `.env` 只决定挂载位置，不能覆盖 artifact 身份和版本。

发布 GHCR 镜像前使用 classic PAT 的 `write:packages` 权限登录。先推最小 robot 镜像验证权限：

```bash
docker login ghcr.io -u <PAT所属的个人GitHub用户名>
scripts/release/publish_ghcr_images.sh 0.1.0 robot
```

GHCR 当前要求 classic PAT；fine-grained PAT 不适用于这个登录流程。登录用户名必须是创建 PAT
的个人账号，而不是组织名；该账号需要拥有向 `zfy-robot` namespace 发布 package 的权限。

确认 package 属于 `zfy-robot`、关联到代码仓库并设为 public 后，再推其余两个：

```bash
scripts/release/publish_ghcr_images.sh 0.1.0 policy
scripts/release/publish_ghcr_images.sh 0.1.0 sim
```

发布脚本默认最多重试三次；网络中断后会复用 registry 中已存在的内容寻址 layer。可用
`S4_GHCR_PUSH_ATTEMPTS` 调整次数。三个 package 均公开并完成匿名 digest 验证后，普通用户通过
`./s4 pull sim|policy|robot|all` 从正式 manifest 拉取固定版本。

公共 Container registry 镜像允许匿名拉取。PAT 只在本机 Docker credential store 中使用，
不得写入 `.env`、manifest、日志或 shell 脚本。
