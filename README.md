# image-to-game

把一张图片变成可玩的 HTML5 网页小游戏的 Agent Skill。

## 用法

1. 克隆本仓库，把 `SKILL.md` 所在目录作为 skill 交给你的 coding Agent（或按其 skill 机制安装；`dist/image-to-game.skill` 为打包好的分发文件）
2. 给 Agent 一张图片 + 一句话（如“做个小游戏”），它会完成：类型路由 → 生成项目 `GDD.md`/动画决策表 → 从本次需求推导 `VISUAL_CONTRACT.json` → 最小真实构图骨架 → Seed Frame 运行时预览与批准 → 白名单序列帧与素材/UI 生产 → 玩法机器人和构图/镜头轨迹双验证 → 交付
3. 想快速出效果：直接拿 `templates/` 里的完整游戏换皮（替换素材 + 主题色），比从零构建快得多

## 目录结构

- `SKILL.md` —— 路由与执行主流程（工作流、类型注册、环境适配、20 条避坑）
- `references/gdd-strategy.md` —— 所有类型共用的八模块 GDD 策略（覆盖要求，不是模板）
- `references/new-type.md` —— 未知类型的考据、红线、验证与蒸馏流程
- `references/assets.md` / `ui-kit.md` —— 分为 GDD 设计参考和设计门后的生产/集成阶段
- `references/platformer-2d.md` / `platformer-patterns.md` —— 平台跳跃类型基线与实现模式
- `references/visual-framing.md` —— 从具体玩法需求推导组合式构图/镜头策略，不使用镜头表单或类型固定映射
- `references/` 其余文件 —— 已验证类型包、实现模式、迭代对照表、验证清单
- `scripts/` —— 抠图、去水印、取色、Seed/Strip 编排、帧归一化与锚点预览、机器人验证、构图合同与运行时轨迹审计、快进截图
- `templates/` —— 两个完整可运行的参考实现（platformer-2d 平台跳跃 / runner-3d 跑酷；体积原因不随 .skill 分发）
- `dist/` —— 打包好的 .skill 文件

环境相关替换点（生图接口 / 交付目录 / 版本工具）见 SKILL.md "环境适配"一节。
