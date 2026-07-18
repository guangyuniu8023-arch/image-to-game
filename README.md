# image-to-game

把一张图片变成可玩的 HTML5 网页小游戏的 Agent Skill。

## 用法

1. 克隆本仓库，把 `SKILL.md` 所在目录作为 skill 交给你的 coding Agent（或按其 skill 机制安装；`dist/image-to-game.skill` 为打包好的分发文件）
2. 给 Agent 一张图片 + 一句话（如"做个小游戏"），它会按 skill 的流程完成：询问类型 → 素材生成 → GDD → 实现 → 机器人验证 → 交付

## 目录结构

- `SKILL.md` —— 方法论主文件（工作流、通用原则、环境适配、16 条避坑）
- `references/` —— 类型包（2D 平台跳跃 / 3D 跑酷）、素材流水线、UI 套件、迭代对照表、验证清单
- `scripts/` —— 抠图、去水印、取色、切帧、机器人验证、快进截图
- `dist/` —— 打包好的 .skill 文件

环境相关替换点（生图接口 / 交付目录 / 版本工具）见 SKILL.md "环境适配"一节。
