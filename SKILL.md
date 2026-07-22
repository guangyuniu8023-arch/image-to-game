---
name: image-to-game
description: 把用户提供的图片变成可玩的 HTML5 网页小游戏，并支持后续迭代与换皮。先用轻量 GDD 明确玩法、角色职责、镜头、素材与必要动画，再生成素材和游戏；始终保留可玩候选，限时验证并把未通过项与 HTML 一并交付。已有类型包：2D 平台跳跃、3D 跑酷、消消乐、竖版弹跳；新类型走通用推演。当用户要求“做个小游戏 / 平台跳跃 / 跑酷 / 消消乐 / 弹跳 / 3D 游戏”，或要修改、修 bug、换素材、换主题、加功能时使用。
---

# Image to Game

把用户图片变成可玩的网页小游戏。先判断工作流：新游戏走 0-1；已有游戏走迭代；命中现有模板走模板换皮。

## 核心原则

1. **GDD 先于素材**：先保存项目 `GDD.md`，明确核心循环、输入、成功/失败、角色职责、镜头、HUD、素材清单、动画最小充分集和验证方式，再调用生图工具。GDD 指导生产，但不设置审批许可证。
2. **单线生成，候选必交付**：按 GDD → 骨架 → 素材 → 完整游戏 → 限时验证 → 交付执行。GDD 写完后的第一个实现检查点必须是可启动的 `index.html`；在首次网络生图前保存加载页、自动开局、核心输入、成功/失败状态机和程序化回退。`index.html` 一旦可启动就作为持久候选保存；后续审计失败、超时或元数据错误不得删除、隐藏或拒绝返回该候选。
3. **只让致命运行错误阻止“可玩”声明**：HTML 无法加载、启动即抛异常、没有可操作入口或核心输入完全失效时，标记 `INCOMPLETE`；仍返回现有文件和诊断。玩法、视觉、合同、证据或 Sprite 检查失败时标记 `GAME_CANDIDATE`，返回链接与未通过项，不冒充 `GAME_READY`。
4. **验证有硬时间预算，不允许机器人主导生产循环**：`GAMEPLAY_CONTRACT.json` 保存固定 seed、`dt`、初始场景和输入时间表；项目只暴露 `window.__game.gameplayAudit.reset/step/snapshot`。通用 `scripts/run_gameplay_runtime.js` 在真实 Chromium 中通过 CDP 发送键盘输入、固定步进并自己采样 trace；游戏不会收到 case 名或 expected，不能一次性自报验收结果。再由 `scripts/audit_gameplay_report.py` 核对哈希与覆盖；不得为每个项目临时造 VM/DOM/Image 浏览器替身。合同只写正式输入可达的规则，同一规则的多个失败侧必须返回不同语义结果，不能都用 `OVER` 冒充。外层仍用 `scripts/run_bot_guard.js`；简单 H5 默认一次主验证，只有明确根因时允许一次定向修复和一次复测。达到预算立即停止验证并交付当前候选。
5. **参考角色必须实际调用生图工具**：用户提供可识别角色图且角色承担操作主体或主体驱动者时，先完成 GDD，再把上传图作为 reference 生成正式游戏内角色 Seed。`CHARACTER_PRODUCTION.json` 只做生成后的记录，不是调用 Seedream 的前置许可证；缺失或 schema 错误只能产生诊断，不能阻止生图或交付。API 失败应报告并保留明确标注的程序化回退候选，不得谎称正式角色已完成。
6. **Sprite 保留 Game Studio 的一致性流程**：GDD 只选择必要动作。连续标量若已由 HUD、形变或特效清楚表达，不再为同一信息生成动作条；简单 H5 首个候选通常只生产一个真正改变身体轮廓/物理事件的核心动作，第二个动作必须单独证明信息增量与姿态必要性。先得到游戏内 Seed；每个必要动作必须按 `build_sprite_edit_canvas.py` → 把输出画布作为生图 reference 一次生成整条 → `normalize_sprite_strip.py --lock-frame1` → `render_sprite_preview_sheet.py` 的顺序执行，禁止逐帧抽卡或跳过编辑画布。全帧共享比例和 bottom-center root anchor，再在游戏内预览。Sprite 检查失败不吞掉已有游戏。
7. **镜头由需求推导**：按 [references/visual-framing.md](references/visual-framing.md) 分析玩家判断、必须共同可见对象、精确输入的稳定参考系、目标变化事件和 HUD 安全区。不得让用户选择镜头表单，也不得按游戏类型套固定镜头。自然启动在资源就绪后必须直接呈现首个可玩构图；需要跟随时必须检查连续游玩后的真实镜头移动。
8. **资源加载门和竖屏布局必须保留**：游戏舞台锁定 9:16；自然启动只显示轻量加载页，图片与字体全部成功或明确失败后初始化本局、设置 `window.__game.ready = true` 并自动进入可玩状态。加载失败走程序化回退；默认不生成封面资产、不显示标题页或“开始游戏”按钮，也不要求第二次点击。
9. **审计是诊断，不是生产授权**：`GAMEPLAY_CONTRACT.json`、`VISUAL_CONTRACT.json`、角色记录、运行时报告和交付 manifest 可用于定位问题与复现，但任何 schema 或报告 FAIL 都不得阻止后续素材生成，也不得阻止返回现有 HTML。
10. **每轮结束都交付、快照、备份**：交付目录必须持久且用户可访问，`index.html` 在项目根；同时保存源码、素材、GDD、验证报告和仍未解决的问题。

## 工作流一：0-1 创建

1. **分析图片与需求**：确认图片主体、玩法类型和角色职责。用户已指明类型就直接做；只说“做个小游戏”才一次性询问类型。未附图时先索要图片。
2. **写轻量 GDD**：读取 [references/gdd-strategy.md](references/gdd-strategy.md) 与对应类型包；新类型再读 [references/new-type.md](references/new-type.md)。保存核心循环、规则红线、加载页与自动开局、镜头理由、素材清单、动画决策表和验证用例。每个失败用例都必须能由正式输入到达；输入维度不足时先修正操作设计，不在机器人中伪造失败。不要在这一阶段生图，也不要为合同格式反复返工。
3. **建立可玩骨架**：命中模板就复制模板，否则建立单个 `index.html` 的最小完整状态机。先实现正式舞台、输入、成功/失败、加载页、自动开局、HUD、投影和镜头；代码角色只作为暂时回退。加载期间不得接受玩法输入；资源全部成功或明确失败后初始化本局并直接进入首个可玩状态，不插入标题页或开始按钮。骨架可启动后立即保存候选，暴露 `window.__game.ready`、`visualAudit` 和 `gameplayAudit.reset/step/snapshot`；首次生图前不得把工作区停留在只有文档的状态。用 `scripts/scaffold_gameplay_contract.py --project . --bot skill:run_gameplay_runtime.js --success NAME=EXPECTED --failure RULE:SIDE:NAME=EXPECTED --boundary RULE:SIDE:NAME=EXPECTED` 生成结构正确的合同，再按 GDD 为每个 case 填入 runner 拥有的 `driver.seed/dt/max_frames/setup/inputs`；同类参数通过重复 flag 添加，不手写另一套 schema。
4. **按 GDD 生产素材**：参考角色直接用上传图生成游戏内 Seed；背景、平台、棋子、UI 底材按 GDD 需要生产。必要角色动作使用 Seed → 整条 → 归一化 → 预览流程，不生成 GDD 未选择的动作。把结果写入 `ASSET_LEDGER.md`；角色记录可在生成后补写。
5. **完成游戏**：接入正式素材和资源加载门，完成全部核心规则、加载完成自动开局、镜头跟随、反馈与重开。除非用户明确要求，禁止新增封面图、标题页或开局 CTA。素材失败时保留回退并在交付报告标记，不得中止已有可玩版本。
6. **限时验证**：按 [references/verification.md](references/verification.md) 运行语法、一次成功路径、GDD 声明的失败/边界、自然启动、真实输入、角色 render source、镜头与控制台检查。简单 H5 一轮验证总预算以控制器为准；只允许一次定向修复复测。
7. **无条件返回当前结果**：通过核心检查时报告 `GAME_READY`；仍有问题时报告 `GAME_CANDIDATE` 或 `INCOMPLETE`。三种状态都必须返回项目路径、可打开的 `index.html`（若已存在）、已完成内容、失败项和耗时。

## 工作流二：1-N 迭代

恢复项目与 GDD，判定受影响模块，做最小修改；只重跑受影响的机器人/截图 case。每轮都产生新的可回退候选，不因回归失败隐藏上一版。详见 [references/iteration.md](references/iteration.md)。

## 工作流三：模板换皮

请求类型与 `templates/<类型>/` 匹配时复制模板，先写差异 GDD，再只替换当前 GDD 需要的素材与主题令牌。玩法、输入、资源加载门和已验证物理基线默认继承；角色身份或动作体系变化时仍走 reference Seed 和整条 Sprite 流程。换皮后的验证失败应返回候选和报告，不得回退成从零重写。

## 类型注册表

| 类型 | 设计/实现 reference | 真实浏览器主验证 | 可选逻辑快测 |
|---|---|---|---|
| 2D 平台跳跃 | [platformer-2d.md](references/platformer-2d.md) + [platformer-patterns.md](references/platformer-patterns.md) | `scripts/run_gameplay_runtime.js` + 项目合同 | `scripts/bot_platformer.js` |
| 3D 跑酷 | [runner-3d.md](references/runner-3d.md) | `scripts/run_gameplay_runtime.js` + 项目合同 | `scripts/runner_bot.js` |
| 消消乐 | [match3.md](references/match3.md) | `scripts/run_gameplay_runtime.js` + 项目合同 | `scripts/bot_match3.js` |
| 竖版弹跳 | [doodle-jump.md](references/doodle-jump.md) | `scripts/run_gameplay_runtime.js` + 项目合同 | `scripts/bot_doodle.js` |
| 新类型 | [gdd-strategy.md](references/gdd-strategy.md) + [new-type.md](references/new-type.md) | `scripts/run_gameplay_runtime.js` + 项目合同 | GDD 明确声明的可选快测 |

新增类型只有在游戏已交付、机器人证据通过且用户验收后，才固化成类型包或模板。

## Pi 沙盒执行约定

- `/etc/pi/pipeline-controller.json` 只提供任务身份、超时和修复计数；旧的 `design/seed/production` 字段仅作兼容与日志记录，不再是素材能力边界。
- 任何阶段只要项目已有 `GDD.md`，就可以按 GDD 调用图片工具；参考角色调用必须带上传图 reference。
- 执行模型完成整条任务后返回 `GAME_READY`；预算耗尽或仍有问题时返回 `GAME_CANDIDATE`/`INCOMPLETE` 和现有候选路径。
- 不得自行调用权威审计形成循环。可运行一次必要静态检查和一次受看门狗保护的主机器人；明确修复后最多复测一次。
- 超时、工具失败或审计失败时保留工作区，不删除已有 `index.html`、素材和证据。

## 常见坑

1. `index.html` 必须闭合 `</body></html>`；替换前断言目标字符串存在。
2. 世界实体使用世界坐标，HUD 使用画布坐标；镜头移动时不要重复叠加偏移。
3. 图片和字体都进入加载门；加载失败要放行回退，不能卡在加载圈。
4. 背景 prompt 禁止画假平台、假按钮或可交互物。
5. 角色动作按单动作整条生成；不同动作可分开，但同一动作不得逐帧生成。
6. 主角 Sprite 用可见像素框计算尺寸；透明画布尺寸不能当角色实际占屏尺寸。
7. 机器人必须固定 `dt`、固定种子、有限循环和进程级超时。
8. 审计失败先返回候选，再决定是否继续；不得为了拿 PASS 修改测试预期或删除失败证据。
9. `window.__game.ready` 必须在状态机和测试接口建立后、资源成功或明确回退后变成严格布尔 `true`；相机 probe 使用 `x/y/zoom/targetX/targetY/targetZoom` 全名，不能另造 `tx/ty` 缩写。
10. 玩法机器人使用真实 Chromium 通用 harness；禁止用同步 busy-wait、假 `Image`、假 Canvas 或临时 VM 复刻浏览器加载过程。
