# 限时诊断与候选交付

审计用于说明当前候选哪里可靠、哪里仍有问题，不负责授权模型进入下一阶段。生产保持一条主线：GDD → 可玩骨架 → 素材 → 完整游戏 → 限时验证 → 交付。

## 状态语义

- `GAME_READY`：HTML 可启动、核心输入有效，GDD 标为核心的成功/失败/边界 case 与视觉/镜头 case 全部通过，正式角色素材按要求接入。任一核心 case 失败或未执行都不能报 READY。
- `GAME_CANDIDATE`：HTML 可启动且可操作，但玩法、镜头、视觉、素材或证据仍有任一未通过/未执行的核心项。
- `INCOMPLETE`：HTML 不存在、无法启动、启动即抛异常或核心输入完全不可用。只要工作区已有文件，仍必须返回路径和诊断。

状态只描述质量，不控制文件可见性。任何状态都不得删除或隐藏已有候选。

## 生产顺序

1. 保存 `GDD.md`，让玩法、角色职责、镜头、素材和必要动画先闭合。
2. 建立可启动的 `index.html`，保存第一份持久候选；这是 GDD 后第一个实现检查点，必须早于首次网络生图。
3. 按 GDD 调用素材工具。参考角色调用必须携带上传图；合同、manifest 或审计报告不是调用许可证。
4. 接入素材并完成核心玩法。
5. 运行一次限时主验证。只有报告给出单一明确根因时，允许一次定向修复和一次复测。
6. 返回当前 HTML、素材、报告、状态和耗时。

## 审计运行方式

现有脚本继续保留标准退出码和报告，供 CI、Agent 与用户判断：

```bash
node scripts/run_bot_guard.js --timeout-ms 10000 -- \
  node scripts/run_gameplay_runtime.js --project <项目目录>
python3 scripts/audit_gameplay_report.py --project <项目目录>
node scripts/audit_visual_runtime.js --project <项目目录> --phase production \
  --run-id <本轮唯一ID，修复复测复用> \
  --out <项目目录>/evidence/visual-production-audit.json
```

退出码非零表示该项未通过，不表示应停止生成、禁止生图或拒绝返回 HTML。控制器应把失败摘要加入交付报告。

## 时间与循环预算

- 简单 H5 的机器人必须由 `run_bot_guard.js` 包裹，单次默认 10 秒。
- 简单 H5 的首个候选优先生产一个核心动作 strip；只有第二动作通过独立的信息增量/姿态必要性证明且仍在总预算内才继续生产，避免素材调用挤掉游戏与验收。
- 候选准备只运行一次主机器人；修复一个明确根因后最多复测一次。
- Pi 控制器用 `task_id` 隔离预算；本地 Codex 传 `--run-id`，每个新用户请求/构建使用新 ID，同一次定向修复复测必须复用原 ID。预算不得按项目终身累计。
- 不在 `/tmp` 创建多套等价 CDP/debug 脚本反复探测同一问题。
- 达到任务 wall-clock timeout 后终止子进程树，保留工作区并输出候选路径。
- 相同失败再次出现时停止自动修改，交付当前版本与证据。

## Pi 兼容

旧控制器仍可写入 `stage: design|seed|production` 和 `repair_attempt`，但 `stage` 只用于日志和旧会话兼容，不再限制图片工具。执行模型始终按完整单线流程工作并以 `GAME_READY`、`GAME_CANDIDATE` 或 `INCOMPLETE` 结束。

外层控制器可以在模型退出后运行额外审计，但审计结果只能更新状态和问题列表，不能抹去、改名或拒绝暴露模型已经生成的候选。
