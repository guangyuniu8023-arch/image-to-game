# image-to-game

把一张图片变成可玩的 HTML5 网页小游戏的 Agent Skill。

## 用法

1. 克隆本仓库，把 `SKILL.md` 所在目录作为 skill 交给你的 coding Agent（或按其 skill 机制安装；`dist/image-to-game.skill` 为打包好的分发文件）
2. 给 Agent 一张图片 + 一句话（如"做个小游戏"），它会按 skill 的流程完成：询问类型 → GDD 设计决策 → 素材/Sprite/UI 生产 → 实现 → 机器人验证 → 交付
3. 想快速出效果：直接拿 `templates/` 里的完整游戏换皮（替换素材 + 主题色），比从零构建快得多

## 目录结构

- `SKILL.md` —— 方法论主文件（工作流、通用原则、环境适配、16 条避坑）
- `references/new-type.md` —— 新类型八模块通用 GDD 策略（不是固定模板）
- `references/assets.md` / `ui-kit.md` —— 消费 GDD 设计决策的素材、Sprite、HUD/UI 生产与验收策略
- `references/` 其余文件 —— 已验证类型包、实现模式、迭代对照表、验证清单
- `scripts/` —— 抠图、去水印、取色、切帧、机器人验证、快进截图
- `templates/` —— 两个完整可运行的参考实现（platformer-2d 平台跳跃 / runner-3d 跑酷；体积原因不随 .skill 分发）
- `dist/` —— 打包好的 .skill 文件

环境相关替换点（生图接口 / 交付目录 / 版本工具）见 SKILL.md "环境适配"一节。
