# 需求驱动的构图与镜头策略

本文件用于 0-1、模板换皮和影响视角的迭代。它规定如何从当前需求推导构图、如何留下运行时证据、如何审核；不提供“游戏类型 → 镜头类型”的选择表，也不要求用户填写镜头表单。

## 1. 先分析玩家的视觉决策

从用户需求、核心循环、状态机、输入和 HUD 推导以下事实：

- 玩家在每个关键状态判断什么；
- 为完成判断必须同时看见哪些玩法实体、路径或危险方向；
- 哪些输入依赖稳定的屏幕参考系，镜头移动会干扰精度；
- 世界、目标或主体何时超出当前视口，哪个玩法事件使构图目标发生变化；
- HUD 占用哪些安全区，哪些实体不能被 HUD 遮挡；
- 主角的哪些身份特征或动作轮廓必须在目标手机尺寸可辨。

不得从“跳一跳、跑酷、消消乐”等类型名称直接选固定镜头，也不得询问用户选择镜头类型。类型包只能提供可组合的实现能力，例如固定取景、主体跟随、目标组取景、前视、死区、软区、阻尼和分区切换。由本次玩法事实决定是否组合、何时启用以及为什么。

把推导结果写入项目根 `VISUAL_CONTRACT.json`。JSON 只记录理由、策略和验收条件，不能替代推理。

合同必须写明最终审计的目标 `viewport.width/height`。每个必须可见实体还要声明 `space: "world" | "hud"`：世界实体参与相机取景、对象组基线和 HUD 遮挡检查；HUD 实体必须落在 probe 的 `hud` 保留区内，只检查其在视口内的实际可见性，不参与世界对象组，也不能对自身触发“被 HUD 遮挡”。`framing_subjects` 和 `baseline.primary_entity` 只能引用世界实体。这不是镜头选择表，而是防止坐标空间和验收口径混用。

## 2. 形成组合式策略

按以下顺序推导，不按游戏名路由：

1. 定义 `must_see`：玩家完成当前决策必须共同看见的对象。
2. 定义 `framing_subjects`：镜头取景实际跟踪的主体或对象组。它可以随状态改变。
3. 找出 `reference_sensitive_states`：蓄力、瞄准、拖拽、精确跳跃等依赖稳定参考系的状态。
4. 找出 `retarget_events`：成功落地、进入新区、目标刷新等使取景对象改变的玩法事件。
5. 决定锁定、重新取景、前视、阻尼、死区等能力如何组合；逐条写明玩法理由。
6. 为每个关键状态建立一个审计 case，声明必须可见对象和可验证的相机行为：`static`、`locked`、`transition` 或 `settled`。这些值是轨迹断言，不是镜头类型。

精确输入期间默认保持参考系稳定；若当前需求确实需要镜头移动，必须在 `rationale` 说明为什么不影响判断，并提供相应运行时 case。目标改变后重新取景，但下一次依赖稳定参考系的输入开始前必须收敛。

## 3. 由实际内容计算取景

构图以真实运行时对象组为输入，不用通用主角占屏百分比：

```text
groupBounds = union(required visible entity bounds)
safeViewport = viewport - HUD reserved regions
desiredZoom = fit(groupBounds, safeViewport, readability needs)
desiredCenter = weightedCenter(groupBounds, current decision)
```

缩放和中心同时考虑：真实 Sprite 透明像素框、目标手机分辨率、当前判断需要的距离/方向、HUD 安全区和批准预览。主角使用 `visible-pixels` 测量，不能用整张透明图片格子代替；平台、轨迹和判定区域可用 `geometry`。

正式构图先生成少量运行时候选：紧凑、平衡、决策空间优先。候选必须由同一个游戏渲染器、投影、HUD 和 Sprite 可见像素框产生。由 Agent 根据角色可读性、目标判断、路径清楚度、遮挡和空旷程度选出最强方案；简单 H5 一次比较即可，不循环抽图。选中方案经过脚本硬门后才交给用户批准。

固定数值只用于安全和稳定断言，例如对象不能被裁掉、镜头锁定不能漂移、轨迹必须在帧上限内收敛。审美尺度以批准的 Seed 运行时预览为基线，正式版本与该基线比较，不与全局万能比例比较。

## 4. 先建构图骨架，再做审批预览

GDD 通过设计门后、完整素材生产前，先建立最小运行时构图骨架：

- 正式 9:16 舞台与目标设备视口；
- 正式世界到屏幕投影和相机更新函数；
- 正式 HUD 安全区；
- 当前玩法需要的状态机片段；
- 角色、目标、路径的调试几何；
- `window.__game.visualAudit` 测试接口。

随后只生成游戏内 Seed Frame，把它临时接入该骨架，使用真实 Sprite 可见像素框重新计算取景。Seed 可以在审批专用骨架中显示，但未批准前不得生成完整动作条或把正式角色扩展成完整游戏。

游戏构图预览必须由该运行时直接截图。禁止在绘图软件或独立 Canvas 中手工拼一张与最终投影无关的预览。

## 5. 项目合同

`VISUAL_CONTRACT.json` 至少包含：

```json
{
  "version": 1,
  "source": "requirement-analysis",
  "viewport": {"width": 475, "height": 844},
  "reasoning": {
    "player_decision": "当前操作需要判断什么",
    "must_see": ["player", "nextTarget", "chargeBar"],
    "reference_sensitive_states": ["charging"],
    "retarget_events": ["successfulLanding"]
  },
  "entities": {
    "player": {
      "role": "primary",
      "space": "world",
      "measurement": "visible-pixels",
      "min_visible_height_px": 96
    },
    "nextTarget": {"role": "decision-target", "space": "world", "measurement": "geometry"},
    "chargeBar": {"role": "input-feedback", "space": "hud", "measurement": "geometry"}
  },
  "policy": {
    "framing_subjects": ["player", "nextTarget"],
    "lock_states": ["charging"],
    "retarget_on": ["successfulLanding"],
    "settle_before_states": ["charging"],
    "rationale": "从当前玩法事实推导的理由"
  },
  "cases": [
    {
      "name": "charging",
      "state": "charging",
      "behavior": "locked",
      "required_visible": ["player", "nextTarget", "chargeBar"],
      "max_frames": 30
    },
    {
      "name": "retarget-after-landing",
      "state": "cameraSettled",
      "behavior": "transition",
      "trigger_event": "successfulLanding",
      "required_visible": ["player", "nextTarget"],
      "max_frames": 30
    }
  ],
  "baseline": {
    "primary_entity": "player",
    "capture_cases": ["charging"],
    "max_primary_area_delta_ratio": 0.25,
    "max_group_area_delta_ratio": 0.25
  },
  "artifacts": ["index.html", "assets/character-seed.png"],
  "approval_artifacts": ["assets/character-seed.png"]
}
```

例子只说明结构，不是要求所有项目复制字段值。主实体必须给出至少一个 `min_visible_width_px`/`min_visible_height_px`，但数值要根据目标设备上必须辨认的身份特征、动作轮廓和当前决策推导，不能从全局模板复制。`max_*_delta_ratio` 是本项目批准预览与正式版本之间允许的相对漂移，由素材变化、动作幅度和玩法可读性决定；它不是角色绝对占屏比例。`approval_artifacts` 保存用户实际批准且生产阶段不得悄悄替换的 Seed/关键底材，不包含正常会继续实现的 `index.html`。

`artifacts` 是**当前阶段真实存在并参与运行时哈希**的文件清单，不是未来生产计划。Seed 阶段不得把尚未生成的动作 raw、strip、frames 或其它未来文件写入其中；后续动作产物由 Sprite/角色生产合同与 Production 门单独约束。目标视口必须与运行时 probe 返回的 `sample.viewport` 完全一致。

先运行静态合同门：

```bash
python3 scripts/audit_visual_contract.py --project <项目目录>
```

## 6. 运行时测试接口

每个项目提供确定性接口：

```js
window.__game.visualAudit = {
  runCase(name) {
    // 同步步进固定 dt，返回逐帧实际屏幕数据，并停在该 case 的证据帧。
    return { samples: [/* probe */] };
  }
};
```

每个 probe 至少返回：

```js
{
  state: "charging",
  viewport: { width, height },
  camera: { x, y, zoom, targetX, targetY, targetZoom },
  entities: {
    player: {
      basis: "visible-pixels",
      bounds: { x, y, width, height }
    }
  },
  hud: [{ bounds: { x, y, width, height } }]
}
```

`runCase` 必须调用真实状态机、相机更新和投影函数；禁止返回另写的一组假数据。`transition` case 另返回实际触发的 `events`，且必须包含合同声明的 `trigger_event`。每个推进循环有固定 `dt`、最大帧数和有限值断言。

## 7. 两阶段视觉硬门

Seed 阶段：

```bash
node scripts/run_bot_guard.js --timeout-ms 10000 -- \
  node scripts/audit_visual_runtime.js --project <项目目录> --phase seed \
  --out <项目目录>/evidence/visual-seed-audit.json
```

脚本直接启动浏览器、运行合同 cases、保存逐 case 截图和实际轨迹，并生成 `evidence/visual-baseline.json`。只有静态合同门和 Seed 运行时门都 PASS，才能把运行时构图预览交给用户批准。

Production 阶段：

```bash
node scripts/run_bot_guard.js --timeout-ms 10000 -- \
  node scripts/audit_visual_runtime.js --project <项目目录> --phase production \
  --baseline <项目目录>/evidence/visual-baseline.json \
  --out <项目目录>/evidence/visual-production-audit.json
```

动态门检查：必须可见对象、HUD 遮挡、有限坐标、锁定状态漂移、过渡是否趋近目标、帧上限内收敛，以及正式版本相对批准基线的主体/对象组尺度漂移。脚本 PASS 后，把 case 截图用 `make_contact_sheet.py` 合并，一次性交给 VLM 或人工检查角色存在感、路径清晰度、空旷和移动是否突兀。

## 8. 失败修复闭环

先分类再修，禁止无目的重生成：

- 主体过小或审批/正式不一致：修 Sprite 显示尺度、透明像素框或对象组 fit；
- 目标、路径不可见：修 `framing_subjects`、安全区或前视；
- 精确输入时漂移：修状态门、死区或相机锁定；
- 移动过冲/反复拉扯：修阻尼、单一目标和收敛条件；
- HUD 遮挡：修安全区或 HUD 布局；
- 投影方向与玩法认知相反：修世界到屏幕轴和生成方向。

每次只修改所属子系统并重跑同一 case。审计报告记录 `attempt`：首次运行加两轮自动修复，最多共 3 次；计数按任务、项目与阶段累计，不因修改合同、改输出路径或删除失败报告而归零。普通环境把每次预约追加到固定的 `evidence/.visual-audit-attempts.jsonl`；Pi 正式任务必须由控制器注入 `VISUAL_AUDIT_STATE_DIR` 与 `VISUAL_AUDIT_RUN_ID`，使用项目外的控制器账本，报告只留 `controller://<id>`，不能信任执行代理可删的项目文件。`audit_visual_runtime.js` 在第 3 次仍失败时写入 repair-limit 问题，第 4 次直接拒绝执行；账本损坏/缺失时也拒绝执行，不能按零次处理。浏览器在 ready 前抛出的首批 JavaScript 异常必须随失败报告透传，修复实际异常，不猜端口或等待时长。达到上限后必须报告具体 case、轨迹和截图，等待用户或外部设计判断；禁止删除/改名失败报告或账本来重置次数、降低门槛或延长无限时间。
