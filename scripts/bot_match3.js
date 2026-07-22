#!/usr/bin/env node
/**
 * 消消乐无头机器人通关测试（match-3 版，用 DOM/canvas 桩执行游戏逻辑）。
 *
 * 用法: node bot_match3.js <index.html>
 * 退出码: 0 = 全部通过（WIN: true + 死盘洗牌验证通过）；1 = 失败
 *
 * 原理: 提取 HTML 内联 <script> 块，前面注入浏览器 API 桩，后面接机器人
 *       代码拼成一个 Node 模块执行。机器人用游戏内置的贪心选步 botPickMove()
 *       连续自动走步，验证：合法交换检测 / 消除结算 / 连锁 / 30 步达标胜利。
 *       另做死盘测试：构造无步可走的棋盘，验证 checkDeadlock() 触发自动洗牌。
 */
"use strict";
const fs = require("fs");
const os = require("os");
const path = require("path");

const htmlPath = process.argv[2];
if (!htmlPath) {
  console.error("用法: node bot_match3.js <index.html>");
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
  get: (o, k) => {
    if (k === "createLinearGradient" || k === "createRadialGradient") return () => ({ addColorStop() {} });
    if (k === "measureText") return () => ({ width: 10 });
    return o[k] !== undefined ? o[k] : (() => {});
  },
  set: (o, k, v) => { o[k] = v; return true; }
});
const cvStub = {
  getContext: () => ctxStub,
  addEventListener() {},
  getBoundingClientRect: () => ({ left: 0, top: 0, width: 540, height: 960 }),
  width: 540, height: 960, style: {}
};
global.document = { getElementById: (id) => id === "game" ? cvStub : { addEventListener() {} }, title: "" };
global.window = { addEventListener() {} };
global.location = { search: "" };
global.Image = class { constructor() { this.complete = true; this.naturalWidth = 0; this.naturalHeight = 0; } set src(v) {} };
global.addEventListener = () => {};
`;

const BOT = `
;(function bot() {
  const need = ["G", "update", "newGame", "trySwap", "findMatches", "findAllMoves",
    "botPickMove", "checkDeadlock", "hasMoves", "TARGET", "COLS", "ROWS"];
  /* MOVES_MAX 不进清单：限时变体（match3-timed）用 TIME_MAX 替代——
     制式探测在下方做（TIMED/MOVES_LIM），两种制式必居其一。 */
  const missing = need.filter((n) => { try { eval(n); return false; } catch (e) { return true; } });
  if (missing.length) {
    console.error("游戏代码缺少符号: " + missing.join(", "));
    process.exit(1);
  }
  const DT = 1 / 60;
  const ok = (cond, msg) => { if (!cond) { console.error("FAIL: " + msg); process.exit(1); } };
  const stepUntilIdle = () => {
    let guard = 0;
    while (G.state === "play" && G.phase !== "idle" && guard++ < 20000) update(DT);
    ok(guard < 20000, "结算相位卡死（phase=" + G.phase + "）");
  };
  const boardTypes = () => G.board.map(row => row.map(p => p.t).join("")).join("|");

  /* 制式探测：限步（G.moves 为剩余、MOVES_MAX 存在）/ 限时（G.timeLeft 存在）。
     限时变体（match3-timed）：moves=用步统计不限量，判负由时间心跳负责。 */
  const TIMED = (() => { try { return typeof G.timeLeft === "number"; } catch (e) { return false; } })();
  const MOVES_LIM = (() => { try { return MOVES_MAX; } catch (e) { return Infinity; } })();

  // ---- 初始棋盘不变量 ----
  newGame();
  ok(findMatches().length === 0, "初始棋盘存在现成消除");
  ok(findAllMoves().length > 0, "初始棋盘无可走步");
  ok(TIMED ? (G.moves === 0 && G.timeLeft > 0) : (G.moves === MOVES_LIM && G.score === 0), "初始步数/时间/分数异常");
  console.log("INIT: 8x8 棋盘无现成消除且有可走步 ✓");

  // ---- 非法交换测试：不形成匹配的交换必须弹回且不扣步数 ----
  let invalid = null;
  for (let r = 0; r < ROWS && !invalid; r++) for (let c = 0; c < COLS && !invalid; c++) {
    for (const [dr, dc] of [[0, 1], [1, 0]]) {
      const r2 = r + dr, c2 = c + dc;
      if (r2 >= ROWS || c2 >= COLS) continue;
      const p = G.board[r][c], q = G.board[r2][c2];
      if (p.s === "color" || q.s === "color" || p.t === q.t) continue;
      // 试交换后确认无匹配
      G.board[r][c] = q; G.board[r2][c2] = p;
      const bad = findMatches().length === 0;
      G.board[r][c] = p; G.board[r2][c2] = q;
      if (bad) { invalid = { a: { r, c }, b: { r: r2, c: c2 } }; break; }
    }
  }
  ok(invalid, "找不到可用于测试的非法交换（棋盘异常？）");
  const movesB = G.moves, scoreB = G.score, boardB = boardTypes();
  ok(trySwap(invalid.a, invalid.b) === true, "非法交换未被接受执行动画");
  stepUntilIdle();
  ok(G.moves === movesB, "非法交换扣了步数");
  ok(G.score === scoreB, "非法交换产生了分数");
  ok(boardTypes() === boardB, "非法交换后棋盘未弹回");
  console.log("INVALID_SWAP: 不形成匹配的交换已弹回、不扣步不计分 ✓");

  // ---- 主循环：机器人连续自动走步 ----
  let steps = 0, shuffles0 = G.shuffles;
  const t0 = Date.now();
  while (G.state === "play") {
    ok(G.phase === "idle", "相位未回到 idle: " + G.phase);
    const mv = botPickMove();
    ok(mv, "有步可走但 botPickMove 返回空");
    const sc0 = G.score;
    ok(trySwap(mv.a, mv.b), "合法交换被拒绝");
    steps++;
    stepUntilIdle();
    ok(G.score >= sc0, "分数倒退");
    ok(TIMED || steps <= MOVES_LIM + 2, "步数超出上限仍未结束");
  }
  const win = G.state === "win" && (TIMED || steps <= MOVES_LIM);
  console.log("WIN: " + win);
  console.log("state=" + G.state
    + " 用步=" + steps + (TIMED ? "(限时制 剩余=" + G.timeLeft.toFixed(1) + "s)" : "/" + MOVES_LIM)
    + " 分数=" + G.score + "(目标 " + TARGET + ")"
    + " 最大连锁=x" + G.maxChain
    + " 洗牌=" + G.shuffles
    + " 耗时=" + ((Date.now() - t0) / 1000).toFixed(1) + "s");

  // ---- 死盘检测 + 自动洗牌测试 ----
  newGame();
  const formulas = [
    (r, c) => (c + 2 * r) % 6,
    (r, c) => (2 * c + r) % 6,
    (r, c) => (c + 3 * r) % 6,
    (r, c) => (r * c + r + c) % 6
  ];
  let deadSet = false;
  for (const f of formulas) {
    for (let r = 0; r < ROWS; r++) for (let c = 0; c < COLS; c++) {
      G.board[r][c] = { t: f(r, c), s: null, x: c, y: r, id: 90000 + r * COLS + c };
    }
    if (findMatches().length === 0 && findAllMoves().length === 0) { deadSet = true; break; }
  }
  ok(deadSet, "未能构造出死盘棋盘（测试自身问题）");
  const shB = G.shuffles;
  const triggered = checkDeadlock();
  ok(triggered === true, "死盘未被检测出来");
  ok(G.shuffles === shB + 1, "死盘检测后未执行洗牌");
  stepUntilIdle();
  ok(findMatches().length === 0, "洗牌后仍存在现成消除");
  ok(findAllMoves().length > 0, "洗牌后仍无步可走");
  console.log("DEADLOCK: 死盘检测触发自动洗牌，洗牌后棋盘可玩 ✓");

  process.exit(win ? 0 : 1);
})();
`;

const combined = STUBS + "\n" + blocks.join("\n;\n") + "\n" + BOT;
const tmp = path.join(os.tmpdir(), "bot_match3_" + process.pid + ".js");
fs.writeFileSync(tmp, combined);
require(tmp);
