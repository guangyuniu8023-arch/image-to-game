# 限时验证与候选交付

验证回答“当前候选哪些部分可信”，不决定用户能否拿到已经生成的游戏。所有检查都保留标准退出码和报告；失败时停止宣称 `GAME_READY`，但必须返回现有 HTML、素材和问题。

## 1. Skill 回归

修改 Skill 后运行：

```bash
bash scripts/selfcheck.sh
```

这一步决定修改能否提交，不参与具体游戏的素材授权。

## 2. 候选最低可运行检查

在项目第一次形成 `index.html` 后立即保存持久候选，并检查：

1. 文件存在且闭合 `</body></html>`；
2. 内联脚本可通过 `node --check`；
3. 页面自然启动时没有首屏 JavaScript 异常；
4. 资源加载成功或失败后都能结束 loading；
5. 至少一个真实用户输入可以改变游戏状态；
6. `window.__game.ready === true`，且 `visualAudit.snapshot/runCase` 与 GDD 的确定性玩法入口已存在；相机 probe 使用 `targetX/targetY/targetZoom` 标准字段。启动界面策略不作为最低可运行审计的独立裁决项；它由 Skill/GDD 定义，用户显式要求可覆盖默认。

上述任一失败时状态为 `INCOMPLETE`，但仍返回工作区和已有文件。

## 3. 玩法诊断

主验证统一使用 `scripts/run_gameplay_runtime.js` 在真实 Chromium 中消费项目 GDD 合同。类型包的旧 CLI bot 只是可选的纯逻辑快测，可用于检查长关卡或随机生成不变量，但其假 DOM/Canvas/Image 结果不能作为 `GAME_READY` 证据。

| 类型 | `GAME_READY` 主证据 | 可选补充快测 |
|---|---|---|
| 2D 平台跳跃 | `run_gameplay_runtime.js` + 项目合同 | `bot_platformer.js` 长关卡通关/完整性 |
| 3D 跑酷 | `run_gameplay_runtime.js` + 项目合同 | `runner_bot.js` 长时存活/刷怪公平性 |
| 消消乐 | `run_gameplay_runtime.js` + 项目合同 | `bot_match3.js` 随机棋盘不变量 |
| 竖版弹跳 | `run_gameplay_runtime.js` + 项目合同 | `bot_doodle.js` 长循环/固定种子 |
| 新类型 | `run_gameplay_runtime.js` + 项目合同 | GDD 明确声明的可选逻辑快测 |

简单 H5 的 GDD 至少声明一次成功路径、每种真实失败侧和一个边界内/外用例。“真实”指玩家可通过正式输入达到；仅蓄力无方向输入的游戏不得伪造侧向落空 case。首次生图前用下面的确切格式保存 `GAMEPLAY_CONTRACT.json`：

```bash
python3 scripts/scaffold_gameplay_contract.py --project <项目目录> \
  --bot skill:run_gameplay_runtime.js \
  --success perfect=READY \
  --failure jump:short:too-short=FAIL_SHORT \
  --failure jump:over:too-far=FAIL_OVER \
  --boundary hitbox:inside:edge-in=READY \
  --boundary hitbox:outside:edge-out=FAIL_OUTSIDE
```

同一规则有多个失败侧时，每侧的 `EXPECTED` 必须是不同的语义结果，不能全部写成 `OVER`。脚手架生成结构后，按 GDD 为每个 case 填写 `driver.seed/dt/max_frames/setup/inputs`；`setup` 只放可重现的初始世界数据，`inputs` 逐条声明 `frame/action/phase/code`。项目只实现 `window.__game.gameplayAudit.reset(seed, setup)`、`step(dt)` 和只读 `snapshot()`；`snapshot` 返回当前 `state/position/result/reason/done`，不接收 case 名或 expected。通用 runner 通过 Chromium CDP 发送真实键盘输入，自己固定步进、采样 trace，并生成 `{actual, seed, dt, inputs, trace, terminal, assertions}`。`actual` 必须与该 case `expected` **完全相同**。只实现 `runCase(name)`、查表直接返回 expected、伪造完整证据对象或一句 PASS 均不构成证据。case 可固定关卡布局，但不得直接赋值结果或终态。合同 schema 失败不能阻止角色生图或游戏实现，但不得另写一套私有 schema 绕开覆盖检查。

推荐命令：

```bash
python3 scripts/audit_gameplay_report.py --project <项目目录> --contract-only
node scripts/run_bot_guard.js --timeout-ms 10000 -- \
  node scripts/run_gameplay_runtime.js --project <项目目录> \
  --out <项目目录>/evidence/gameplay-audit.json
python3 scripts/audit_gameplay_report.py --project <项目目录>
```

项目 case 必须固定 `dt`、固定种子、有限循环和有限数值断言；核心状态不等待真实动画时间。浏览器启动、资源加载、CDP 输入、case 超时、trace 采样和证据哈希均由通用 runner 负责。禁止用 Node VM、假 DOM/Canvas/Image、同步 busy-wait 或项目自造 CDP 脚本模拟浏览器；这类替身既容易死锁，也不能证明真实页面可玩。一次主验证后，只有明确单一根因时允许一次定向修复和一次复测。禁止连续创建多个 `dbg*.js`、重复安装浏览器依赖或无限延长等待。

玩法检查失败时状态为 `GAME_CANDIDATE`；报告列出失败规则、实际 trace 和当前 HTML 路径。

## 4. 角色与 Sprite 诊断

用户提供可识别角色图且角色承担 A/B 职责时，检查 Seedream 日志和项目文件，确认正式 Seed 的调用真实携带 reference。`CHARACTER_PRODUCTION.json` 和 `scripts/audit_character_production.py` 可用于核对，但不是图片调用的许可证。

必要 Sprite 动作执行：

```bash
python3 scripts/audit_sprite_frames.py --frames-dir <sprites/action> --expected <N> \
  --meta <sprites/action/sprite-meta.json> --anchor <seed.png> --min-distinct <M>
```

同时检查动作时间线证据：起势、物理事件帧、收势；root anchor 稳定；交互 socket 与物理事件一致；实际游戏尺寸下姿态可读。失败时游戏可回退到 Seed 或程序化反馈，但必须标记正式 Sprite 未完成，不得冒充通过。

## 5. 视觉、自动开局与镜头诊断

视觉事实来自 GDD 和可选 `VISUAL_CONTRACT.json`。启动界面是产品设计决策，不由视觉审计根据状态名反推。至少检查：

- `window.__game.ready === true` 时可忠实采样 GDD 定义的自然状态，不得由审计入口偷换状态；
- 核心循环中主角和当前决策目标可见；
- 角色 `render_source` 是正式 Seed/Sprite，或明确标记 fallback；
- 精确输入期间镜头不漂移；
- GDD 要求跟随时，连续成功后相机目标和真实相机位置都移动；
- 主角使用可见像素框测量，在目标手机视口可辨；
- HUD 不遮挡世界决策对象；
- 控制台没有运行时异常。

可使用：

```bash
node scripts/run_bot_guard.js --timeout-ms 10000 -- \
  node scripts/audit_visual_runtime.js --project <项目目录> --phase production \
  --run-id <本轮唯一ID，修复复测复用> \
  --out <项目目录>/evidence/visual-production-audit.json
```

脚本非零时把具体 case、轨迹和截图加入交付报告。VLM 或人工只负责观感判断，不代替几何和玩法证据。简单 H5 默认一次视觉诊断，明确修复后最多复测一次。

## 6. 交付状态

- `GAME_READY`：最低可运行检查通过；GDD 标为核心的玩法成功/失败/边界 case 和视觉/镜头 case 已执行且全部通过；正式角色素材符合 GDD。
- `GAME_CANDIDATE`：可启动、可操作，但玩法、镜头、视觉、角色或证据存在任一未通过/未执行的核心项。
- `INCOMPLETE`：没有可启动候选或核心输入完全不可用。

无论状态如何，都返回：

1. 当前项目目录；
2. 当前 `index.html`（如果存在）；
3. 已生成素材与实际 render source；
4. 已通过和未通过检查；
5. Seedream、机器人、浏览器和总耗时；
6. 下一步最小修复建议。

可继续生成 `DELIVERY_MANIFEST.json`、`game-build` 和运行时哈希用于版本核对；缺失或审计失败只影响 `GAME_READY`，不影响候选可见性。保存版本快照并备份源码，禁止用旧链接或旧构建冒充当前候选。
