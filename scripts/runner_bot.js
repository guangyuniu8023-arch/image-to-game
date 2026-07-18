#!/usr/bin/env node
/* 跑酷机器人生存测试：证明刷怪公平（永远有活路）且判定正确。
   用法: node runner_bot.js <index.html> [秒数=120] */
"use strict";
const fs = require("fs"), os = require("os"), path = require("path");
const htmlPath = process.argv[2];
const MAXSEC = Number(process.argv[3] || 120);
const html = fs.readFileSync(htmlPath, "utf8");
const blocks = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]).filter(s => s.trim());
if (!blocks.length) { console.error("未找到内联脚本"); process.exit(1); }

const STUBS = `
const H = { get: (t,k) => (typeof k === "symbol" ? undefined : P), apply: () => P, construct: () => P, set: () => true };
const P = new Proxy(function(){}, H);
global.THREE = P;
const ctx2d = new Proxy({}, { get: (o,k) => k === "createRadialGradient" || k === "createLinearGradient" ? (() => ({ addColorStop(){} })) : (o[k] !== undefined ? o[k] : (() => {})), set: (o,k,v) => { o[k]=v; return true; } });
const elStub = () => ({ style: {}, textContent: "", innerHTML: "", width: 0, height: 0, getContext: () => ctx2d });
global.document = { getElementById: elStub, createElement: elStub };
global.Image = class { set src(v) { if (this.onload) this.onload(); } };   // 立即视为加载完成
global.window = global;
global.innerWidth = 960; global.innerHeight = 540; global.devicePixelRatio = 1;
global.localStorage = { getItem: () => null, setItem() {} };
global.addEventListener = () => {};
global.requestAnimationFrame = () => {};
`;

const BOT = `
;(function bot() {
  const need = ["LG", "update", "newGame", "keys"];
  const missing = need.filter(n => { try { eval(n); return false; } catch (e) { return true; } });
  if (missing.length) { console.error("缺符号: " + missing.join(",")); process.exit(1); }
  newGame();
  const DT = 1 / 60;
  let deaths = 0, lastLives = LG.lives, minZ = 1e9;
  const log = [];
  for (let step = 0; step < 60 * ${MAXSEC}; step++) {
    if (LG.state === "play") {
      keys.ArrowLeft = keys.ArrowRight = keys.ArrowUp = keys.ArrowDown = false;
      const p = LG.player;
      // 最近一排
      let rz = -1e9;
      for (const o of LG.obs) if (o.z < -1 && o.z > rz) rz = o.z;
      const rows = LG.obs.filter(o => Math.abs(o.z - rz) < 2.5);
      if (rows.length && rz > -30) {
        const blocked = new Set(rows.map(o => o.lane));
        if (blocked.has(p.lane)) {
          const o = rows.find(o => o.lane === p.lane);
          if (o.type === "barrier") { if (rz > -LG.speed * 0.45) keys.ArrowUp = true; }
          else if (o.type === "beam") { if (rz > -LG.speed * 0.45) keys.ArrowDown = true; }
          else {
            let target = -1;
            for (const l of [p.lane - 1, p.lane + 1]) if (l >= 0 && l <= 2 && !blocked.has(l)) { target = l; break; }
            if (target >= 0) keys[target > p.lane ? "ArrowRight" : "ArrowLeft"] = true;
          }
        }
      }
    }
    update(DT);
    if (LG.lives < lastLives) {
      deaths++; lastLives = LG.lives;
      const near = LG.obs.filter(o => Math.abs(o.z) < 6).map(o => o.type + "@" + o.lane).join(" ");
      log.push("t=" + LG.time.toFixed(1) + "s 受击! 道=" + LG.player.lane + " 速度=" + LG.speed.toFixed(1) + " 附近障碍: " + near);
    }
    if (LG.state === "gameover") break;
  }
  console.log("存活: " + (LG.state === "play"));
  console.log("时间=" + LG.time.toFixed(1) + "s 距离=" + LG.dist.toFixed(0) + "m 分数=" + LG.score
    + " 骨头=" + LG.bones + " 生命=" + LG.lives + " 受击=" + deaths
    + " 速度=" + LG.speed.toFixed(1) + "/" + LG.maxSpeed);
  if (log.length) console.log(log.slice(0, 10).join("\\n"));
  process.exit(LG.state === "play" ? 0 : 1);
})();
`;

const tmp = path.join(os.tmpdir(), "runner_bot_" + process.pid + ".js");
fs.writeFileSync(tmp, STUBS + "\n" + blocks.join("\n;\n") + "\n" + BOT);
require(tmp);
