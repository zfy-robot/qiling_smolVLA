# 项目所有者发布与维护清单

持续进度和验收证据以 [`PROJECT_STATUS.md`](PROJECT_STATUS.md) 为准。本文件只列需要项目
所有者亲自执行或确认的操作。

## v0.1.0 已完成

- [x] GitHub 项目按 Apache-2.0 公开；
- [x] IsaacLab fork 与 LeRobot 以固定 commit 的 submodule 管理；
- [x] ModelScope `zfy2qiling/qiling_smolvla` 公开，并固定 revision
  `3686874898fdf908431db487468f21a527507988`；
- [x] 发布仿真 350K、真机 300K checkpoint，不发布 `training_state/`；
- [x] 项目数据、机器人和场景资产进入 ModelScope；
- [x] NVIDIA 资产与 Kit extensions 只从官方源获取，不由项目二次分发；
- [x] `sim`、`policy`、`robot` 三个镜像已推送 GHCR、关联仓库、设为 Public，并完成匿名
  digest 验证；
- [x] 当前工作站完成仿真、训练、真机策略协议及 robot 无硬件验证；
- [x] 主分支已推送到 GitHub。

## v0.1.0 最后操作

- [x] 合入“退役旧单体镜像链路与文档收口”的最终提交 `6e95541`；
- [x] 确认该提交的 GitHub Actions run `34571153032` 通过；
- [ ] 创建并推送不可移动的 annotated tag `v0.1.0`；
- [ ] 使用 [`RELEASE_NOTES_v0.1.0.md`](../release/RELEASE_NOTES_v0.1.0.md) 创建 GitHub Release。

完成以上四项后，本版本状态记为 **v0.1.0 本机完整验证版**。异机复现和物理机器人动作验收
因工期延期，已经在 manifest 和 Release Notes 中明确，不阻塞本次标签。

## 后续版本再做

- [ ] 在另一台符合支持线的 NVIDIA 主机，从 tag 干净 clone 后执行教程级复现；
- [ ] 连接真机后依次完成相机枚举、ROS feedback、shadow rollout 与人工安全门禁；
- [ ] 只有急停、方向、限位、频率和 publisher 唯一性均确认后，才做低风险 live motion；
- [ ] 如需续训 checkpoint，将 `training_state/` 放入独立私有仓库，不混入公开部署制品。

## 每次发布必须遵守

1. 更新 submodule commit、ModelScope revision、镜像 digest 和 lock；
2. 本机运行 `bash scripts/ci/static_checks.sh`；
3. 先推不可变镜像并匿名核对 digest，再提交正式 manifest；
4. 先推 main、确认 CI，再打 tag；已公开 tag 不移动；
5. `.env`、token、代理凭据、相机序列号、局域网地址和现场配置不得进入 Git。
