#!/usr/bin/env node
/**
 * Doodle Jump 机器人通关测试（参照 skill bot_harness.js 的 DOM-shim 思路，
 * 玩法与胜负判定按本类型 GDD 第 5 步验收定义，不照抄平台跳跃判定）。
 *
 * 用法: node bot_doodle.js <index.html> [最长模拟秒数=240]
 * 退出码: 0 = 通关（WIN: true）；1 = 未通关 / 出错
 *
 * 机器人玩法（GDD 定稿，数值与代码一致）：
 *   1. 在玩家上方 dy∈[40,210] 内选代价最小的可弹平台（碎板代价 +500，终点台 -1000）
 *   2. 朝目标台中心移动（环绕取短路径，±6px 死区）
 *   3. 无候选台时保持当前方向
 * WIN 判定：G.state === 'win'（站上 10000px 终点平台）
 * 死局：坠落/碰怪 → gameover → 判负
 */
"use strict";
const fs = require("fs");
const os = require("os");
const path = require("path");

const htmlPath = process.argv[2];
const MAXSEC = Number(process.argv[3] || 240);
if (!htmlPath) {
  console.error("用法: node bot_doodle.js <index.html> [最长秒数]");
  process.exit(1);
}
const html = fs.readFileSync(htmlPath, "utf8");
const blocks = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
if (!blocks.length) { console.error("未找到内联 <script> 块"); process.exit(1); }

const STUBS = `
const ctxStub = new Proxy({}, {
  get: (o, k) => k === "createLinearGradient" ? (() => ({ addColorStop() {} }))
    : (o[k] !== undefined ? o[k] : (() => {})),
  set: (o, k, v) => { o[k] = v; return true; }
});
const cvStub = { getContext: () => ctxStub, addEventListener() {}, width: 540, height: 960, style: {} };
global.document = { getElementById: (id) => id === "game" ? cvStub : { addEventListener() {} } };
global.window = {};
global.innerWidth = 540; global.innerHeight = 960;
global.Image = class { constructor() { this.complete = false; } set src(v) {} };
global.addEventListener = () => {};
global.requestAnimationFrame = () => {};
global.performance = { now: () => 0 };
`;

const BOT = `
;(function bot() {
  const need = ["player", "platforms", "monsters", "keys", "G", "newGame", "update", "GOAL_Y", "VIEW_W", "wrapDist"];
  const missing = need.filter((n) => { try { eval(n); return false; } catch (e) { return true; } });
  if (missing.length) {
    console.error("游戏代码缺少符号: " + missing.join(", "));
    process.exit(1);
  }
  newGame();
  const DT = 1 / 60;
  let maxAlt = 0, win = false, springs = 0, lastVySign = 1, stuckT = 0, lastAlt = 0;
  const botTargetRef = { obj: null };
  const t0 = Date.now();
  for (let step = 0; step < 60 * ${MAXSEC}; step++) {
    if (G.state === "play") {
      // 与游戏内 botControl 相同的决策：近怪避让 + 反弹帧决策 + 跌过重瞄 + 坠落救场
      const p = player, cx = p.x + p.w / 2, feet = p.y + p.h, cy = p.y + p.h / 2;
      let dodging = false;
      for (const m of monsters) {
        if (!m.alive) continue;
        const mdx = wrapDist(cx, m.x + m.w / 2), mdy = Math.abs(cy - (m.y + m.h / 2));
        if (mdy < 120 && Math.abs(mdx) < 75) {
          const stomping = p.vy > 0 && feet < m.y + 12;
          if (!stomping) {
            keys.ArrowLeft = mdx > 0;
            keys.ArrowRight = mdx < 0;
            dodging = true;
            break;
          }
        }
      }
      if (!dodging) {
        const justBounced = lastVySign > 0 && p.vy < 0;
        const missed = botTargetRef.obj && p.vy > 0 && feet - botTargetRef.obj.y > 218;
        if (justBounced || missed || !botTargetRef.obj || botTargetRef.obj.broken) {
          let best = null, bs = 1e9;
          for (const pl of platforms) {
            if (pl.broken) continue;
            const dy = feet - pl.y;
            let s = null;
            if (dy >= 40 && dy <= 210) {
              s = Math.abs(wrapDist(cx, pl.x + pl.w / 2)) * 2 + dy * 0.3 + (pl.type === 2 ? 500 : 0) + (pl.goal ? -1000 : 0);
            } else if (p.vy > 0 && dy <= -20 && dy >= -300) {
              s = 300 + Math.abs(wrapDist(cx, pl.x + pl.w / 2)) * 2 + (-dy) * 0.2 + (pl.type === 2 ? 600 : 0);
            }
            if (s !== null && s < bs) { bs = s; best = pl; }
          }
          if (best) botTargetRef.obj = best;
        }
        if (botTargetRef.obj) {
          const d = wrapDist(cx, botTargetRef.obj.x + botTargetRef.obj.w / 2);
          keys.ArrowLeft = d < -8;
          keys.ArrowRight = d > 8;
        }
      }
      if (player.vy < -1400 && lastVySign >= -1400) springs++;
      lastVySign = player.vy;
    }
    update(DT);
    maxAlt = Math.max(maxAlt, G.alt);
    if (G.alt > lastAlt + 50) { lastAlt = G.alt; stuckT = 0; } else stuckT += DT;
    if (G.state === "win") { win = true; break; }
    if (G.state === "gameover") break;
    if (stuckT > 30) break; // 30 秒无新高 = 卡死，判负
  }
  console.log("WIN: " + win);
  console.log("state=" + G.state
    + " 最高高度=" + maxAlt + "m/1000m"
    + " 铅笔=" + G.pencils
    + " 踩怪=" + G.stomps + "/" + monsters.length
    + " 弹簧=" + springs
    + " 分数=" + G.score
    + " 死亡原因=" + (G.deadBy || "-")
    + " 游戏耗时=" + G.time.toFixed(1) + "s"
    + " 模拟耗时=" + ((Date.now() - t0) / 1000).toFixed(1) + "s");
  process.exit(win ? 0 : 1);
})();
`;

const combined = STUBS + "\n" + blocks.join("\n;\n") + "\n" + BOT;
const tmp = path.join(os.tmpdir(), "bot_doodle_" + process.pid + ".js");
fs.writeFileSync(tmp, combined);
require(tmp);
