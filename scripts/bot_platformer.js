#!/usr/bin/env node
/**
 * 无头机器人通关测试：验证平台跳跃游戏的关卡"确实可通关"。
 *
 * 用法: node bot_platformer.js <index.html> [最长模拟秒数=180] [--lenient]
 * 退出码: 0 = 通关且完整性断言通过；1 = 未通关 / 断言失败 / 出错
 *         --lenient: 完整性断言降级为警告(仅用于 GDD 已声明简化的实验项目)
 *
 * 原理: 提取 HTML 内联 <script> 块，前面注入浏览器 API 桩，后面接机器人
 *       代码，拼成一个 Node 模块执行。机器人按住右方向键，遇墙/悬崖/敌人
 *       自动跳跃，模拟真实玩家跑完整关。
 *
 * 约定: 游戏代码需包含 player/enemies/keys/press/G/update/newGame/tileAt/
 *       solid/TILE/ROWS 这些符号（按 references/platformer-patterns.md 写的游戏
 *       天然满足）。缺失时会明确报出缺哪个。
 */
"use strict";
const fs = require("fs");
const os = require("os");
const path = require("path");

const htmlPath = process.argv[2];
const MAXSEC = Number(process.argv[3] || 180);
const LENIENT = process.argv.includes("--lenient");
if (!htmlPath) {
  console.error("用法: node bot_platformer.js <index.html> [最长秒数]");
  process.exit(1);
}
const html = fs.readFileSync(htmlPath, "utf8");
const blocks = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
if (!blocks.length) {
  console.error("未找到内联 <script> 块");
  process.exit(1);
}

const STUBS = `
const ctxStub = new Proxy({}, {
  get: (o, k) => k === "createLinearGradient" ? (() => ({ addColorStop() {} }))
    : (o[k] !== undefined ? o[k] : (() => {})),
  set: (o, k, v) => { o[k] = v; return true; }
});
const cvStub = { getContext: () => ctxStub, addEventListener() {}, width: 960, height: 540, style: {} };
global.document = { getElementById: (id) => id === "game" ? cvStub : { addEventListener() {} } };
global.window = {};
global.innerWidth = 960; global.innerHeight = 540;
global.Image = class { constructor() { this.complete = false; } set src(v) {} };
global.addEventListener = () => {};
global.requestAnimationFrame = () => {};
`;

const BOT = `
;(function bot() {
  const need = ["player", "enemies", "keys", "press", "TILE", "ROWS", "solid", "tileAt", "update", "G", "newGame"];
  const missing = need.filter((n) => { try { eval(n); return false; } catch (e) { return true; } });
  if (missing.length) {
    console.error("游戏代码缺少符号: " + missing.join(", ") + " —— 请按 references/platformer-patterns.md 的命名写，或改机器人适配");
    process.exit(1);
  }
  newGame();

  // ===== 关卡完整性断言(platformer-2d.md 分段配方的强制校验)=====
  // 在 newGame() 后、游玩前扫描 grid 与实体表:长度/?砖/砖块群/水管/台阶/浮台/敌/收集物
  const LENIENT = ${LENIENT};
  function audit() {
    const issues = [];
    let Tmap = null, cols = 0;
    try { Tmap = eval("T"); } catch (e) {}
    try { cols = eval("COLS"); } catch (e) {}
    if (cols && cols < 200) issues.push("关卡长度 " + cols + " 列 < 规范 200(platformer-2d.md 分段配方总长 200~220)");
    if (Tmap && cols) {
      const cnt = {};
      for (let c = 0; c < cols; c++) for (let r = 0; r < ROWS; r++) {
        const t = tileAt(c, r);
        cnt[t] = (cnt[t] || 0) + 1;
      }
      const n = (k) => cnt[Tmap[k]] || 0;
      const need = [["Q", "问号砖", 4, "(顶砖机制缺失=流程减配)"], ["BRICK", "砖块群", 5, ""],
                    ["PIPE", "水管", 2, ""], ["STAIR", "台阶", 12, "(金字塔+终点大台阶)"], ["PLAT", "单向浮台", 2, ""]];
      for (const [k, label, min, note] of need) {
        if (Tmap[k] === undefined) { issues.push(label + "机制未实现(瓦片类型 T." + k + " 不存在)"); continue; }
        if (n(k) < min) issues.push(label + " " + n(k) + " 个 < 规范 ≥" + min + note);
      }
    }
    let collect = null;
    for (const nm of ["coins", "bones", "collects", "stars"]) {
      try { const v = eval(nm); if (Array.isArray(v)) { collect = v; break; } } catch (e) {}
    }
    if (collect && (collect.length < 50 || collect.length > 70))
      issues.push("收集物 " + collect.length + " 个,规范 50~70");
    if (enemies.length < 12 || enemies.length > 18)
      issues.push("敌人 " + enemies.length + " 只,规范 12~18");
    return issues;
  }
  const auditIssues = audit();
  if (auditIssues.length) {
    console.log("完整性断言: " + (LENIENT ? "WARN(实验简化模式)" : "FAIL"));
    auditIssues.forEach((i) => console.log("  - " + i));
  } else {
    console.log("完整性断言: 全部通过");
  }

  const DT = 1 / 60;
  const groundAhead = () => {
    const c = Math.floor((player.x + player.w + 12) / TILE);
    const r0 = Math.floor((player.y + player.h + 8) / TILE);
    for (let r = r0; r < ROWS; r++) if (solid(tileAt(c, r))) return true;
    return false;
  };
  const wallAhead = () => {
    const c = Math.floor((player.x + player.w + 8) / TILE);
    const rt = Math.floor((player.y + 8) / TILE), rb = Math.floor((player.y + player.h - 4) / TILE);
    for (let r = rt; r <= rb; r++) if (solid(tileAt(c, r))) return true;
    return false;
  };
  const enemyAhead = () =>
    enemies.some((e) => e.alive && e.x > player.x && e.x - player.x < 78 && Math.abs(e.y - player.y) < 70);

  let jumpHold = 0, maxX = 0, deaths = 0, lastLives = G.lives, win = false;
  const t0 = Date.now();
  for (let step = 0; step < 60 * ${MAXSEC}; step++) {
    if (G.state === "play") {
      keys.ArrowRight = true;
      if (player.onGround && (wallAhead() || !groundAhead() || enemyAhead())) { press.jump = true; jumpHold = 0.28; }
      jumpHold -= DT;
      keys.Space = jumpHold > 0;
    }
    if (G.lives < lastLives) { deaths++; lastLives = G.lives; }
    maxX = Math.max(maxX, player.x);
    update(DT);
    if (G.state === "win") { win = true; break; }
    if (G.state === "gameover") break;
  }
  const stomps = enemies.filter((e) => !e.alive && (e.squash === undefined || e.squash < 90)).length;
  const auditOk = auditIssues.length === 0 || LENIENT;
  console.log("WIN: " + (win && auditOk));
  console.log("state=" + G.state
    + " 最远列=" + (maxX / TILE).toFixed(1)
    + " 收集=" + (G.bones !== undefined ? G.bones : "-")
    + " 分数=" + (G.score !== undefined ? G.score : "-")
    + " 剩余生命=" + G.lives + " 死亡=" + deaths
    + " 踩敌=" + stomps + "/" + enemies.length
    + " 耗时=" + ((Date.now() - t0) / 1000).toFixed(1) + "s");
  process.exit(win && auditOk ? 0 : 1);
})();
`;

const combined = STUBS + "\n" + blocks.join("\n;\n") + "\n" + BOT;
const tmp = path.join(os.tmpdir(), "bot_platformer_" + process.pid + ".js");
fs.writeFileSync(tmp, combined);
require(tmp);
