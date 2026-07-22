# 阶段 Gate 与失败诊断

把易错的生产顺序交给环境控制器，不让执行模型自行决定是否进入下一阶段。阶段由产物生命周期驱动，与用户关键词、轮次和游戏类型无关。

## 三阶段协议

1. **design**：只生成 GDD、双合同、项目机器人/确定性接口、最小真实构图骨架和 `CHARACTER_PRODUCTION.json` draft。候选产物完成后运行 `audit_pipeline_stage.py --stage design --require-character-draft`；它用 debug/fallback 角色在真实浏览器执行合同全部 case，先证明 probe、镜头、状态与帧预算闭合。PASS 前禁止任何生图。

Design 镜头门同时校验需求推导的过渡形态：`smooth` 需要首帧未收敛、至少三个真实触发后样本、稳定 target 和单调收敛；`cut` 需要首帧已稳定。不能用相机瞬移伪装平滑跟随。
2. **seed**：只生成 manifest 指定的参考角色 Seed，接入真实骨架，制作基于 Seed 的动作节拍示意；候选产物完成后运行 `audit_pipeline_stage.py --stage seed`。PASS 后停止并等待用户批准。
3. **production**：只消费用户批准的 Seed 和生产白名单，完成素材、游戏、机器人与交付；候选产物完成后运行 `audit_pipeline_stage.py --stage production`，再完成 delivery gate。

若 `/etc/pi/pipeline-controller.json` 存在，上述“运行 Gate”的主语始终是模型进程之外的控制器：执行模型只写候选产物并返回对应 `*_READY`，不得自己调用阶段 Gate。没有控制器的环境才由当前 Agent 同步执行 Gate。

`audit_pipeline_stage.py` 与 `audit_visual_runtime.js` 会机械执行该边界：controller-backed Pi 进程内调用返回 `DEFERRED_TO_CONTROLLER`，不创建 Gate 证据、不预约视觉重试。Seedream 适配器只被允许执行 design 静态预检，不可借此运行 Seed/production Gate。

Controller-backed 候选生产只允许一次预览采样；若它暴露具体集成错误，可做一次针对性修复并再采样一次，随后必须返回 `*_READY`，由外层 Gate 给出正式 signature。禁止在 `/tmp` 自造反复 CDP/截图循环；没有正式 signature 就继续调参不算有效验证。

环境存在 `/etc/pi/pipeline-controller.json` 时，以其中只读 `task_id`、`stage`、`repair_attempt` 和审计目录为唯一授权源；不得用环境变量、输出路径、报告换名或新会话 id 自行升级阶段或重置次数。其他环境可按同一语义接入自己的控制器。

## 合同脚手架

玩法内容仍由 GDD 模块 8 推导；脚本只固定易错的 JSON 结构：

```bash
python3 scripts/scaffold_gameplay_contract.py --project <项目> \
  --bot <项目目录内的机器人路径> \
  --success 'win=ready' \
  --failure 'strength:short:too-short=gameover' \
  --failure 'strength:long:too-long=gameover' \
  --boundary 'hitbox:inside:edge-in=ready' \
  --boundary 'hitbox:outside:edge-out=gameover'
```

参数名、规则、侧和 expected 必须来自本次 GDD；这不是用户表单，也不决定玩法、镜头或主题。

## 失败 Loop

Gate 失败后先读取 `evidence/pipeline-<stage>-audit.json`：

1. 用 `categories` 确认责任层；不跨层修改。
2. 保留 `failure_signature`，写出一个可证伪的根因假设和对应文件。
3. 只做该假设要求的最小修复，再由控制器授权复测。
4. 相同 signature 再现、错误集合未减少或修复预算耗尽时，当前阶段转为 `INCOMPLETE/BLOCKED`；停止自动修补并返回证据。

审计次数上限只终止当前阶段的失控执行，不把总体目标标记为完成。新的修复轮必须由外部控制器或用户根据诊断证据重新授权。

## 环境接入

- 控制器应在模型进程外运行 Gate；模型产生候选产物，控制器判定 PASS/FAIL。
- Seedream 适配器必须读取只读阶段授权：design 禁止调用；seed 只允许 manifest 声明的 reference Seed 输出；production 才开放批准后的白名单生产。
- 视觉审计第三次失败后不得预约第四次，且不得用“超过上限”空报告覆盖第三次详细证据。
- 每个阶段设置进程级 wall-clock timeout；超时返回未完成状态并保留工作区。
