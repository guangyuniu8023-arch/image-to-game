#!/usr/bin/env node
/**
 * 无头机器人通关测试：验证平台跳跃游戏的关卡"确实可通关"。
 *
 * 用法: node bot_harness.js <index.html> [最长模拟秒数=180]
 * 退出码: 0 = 通关（WIN: true）；1 = 未通关 / 出错
 *
 * 原理: 提取 HTML 内联 <script> 块，前面注入浏览器 API 桩，后面接机器人
 *       代码，拼成一个 Node 模块执行。机器人按住右方向键，遇墙/悬崖/敌人
 *       自动跳跃，模拟真实玩家跑完整关。
 *
 * 约定: 游戏代码需包含 player/enemies/keys/press/G/update/newGame/tileAt/
 *       solid/TILE/ROWS 这些符号（按 references/game-patterns.md 写的游戏
 *       天然满足）。缺失时会明确报出缺哪个。
 */
"use strict";
const fs = require("fs");
const os = require("os");
const path = require("path");

const htmlPath = process.argv[2];
const MAXSEC = Number(process.argv[3] || 180);
if (!htmlPath) {
  console.error("用法: node bot_harness.js <index.html> [最长秒数]");
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
    console.error("游戏代码缺少符号: " + missing.join(", ") + " —— 请按 references/game-patterns.md 的命名写，或改机器人适配");
    process.exit(1);
  }
  newGame();
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
  console.log("WIN: " + win);
  console.log("state=" + G.state
    + " 最远列=" + (maxX / TILE).toFixed(1)
    + " 收集=" + (G.bones !== undefined ? G.bones : "-")
    + " 分数=" + (G.score !== undefined ? G.score : "-")
    + " 剩余生命=" + G.lives + " 死亡=" + deaths
    + " 踩敌=" + stomps + "/" + enemies.length
    + " 耗时=" + ((Date.now() - t0) / 1000).toFixed(1) + "s");
  process.exit(win ? 0 : 1);
})();
`;

const combined = STUBS + "\n" + blocks.join("\n;\n") + "\n" + BOT;
const tmp = path.join(os.tmpdir(), "bot_harness_" + process.pid + ".js");
fs.writeFileSync(tmp, combined);
require(tmp);
