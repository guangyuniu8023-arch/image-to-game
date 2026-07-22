// 用法: node cdp_shot.js <url> <out.png> [readyExpr] [w] [h] [extraWaitMs] [readyTimeoutMs]
// readyExpr 必须严格返回布尔 true；默认 8s 未就绪即失败且不截图。
// 依赖: npm i chrome-remote-interface（本目录或上级 node_modules 均可）
"use strict";

function isStrictReady(result) {
  return result && result.type === "boolean" && result.value === true;
}

if (process.argv[2] === "--self-test") {
  const cases = [
    isStrictReady({ type: "boolean", value: true }) === true,
    isStrictReady({ type: "boolean", value: false }) === false,
    isStrictReady({ type: "object", value: { ready: true } }) === false,
    isStrictReady({ type: "number", value: 1 }) === false,
  ];
  if (cases.every(Boolean)) {
    console.log("CDP_SHOT_SELFTEST: PASS");
    process.exit(0);
  }
  console.error("CDP_SHOT_SELFTEST: FAIL");
  process.exit(1);
}

let CDP;
for (const p of ["chrome-remote-interface", "/tmp/node_modules/chrome-remote-interface"]) {
  try { CDP = require(p); break; } catch (e) {}
}
if (!CDP) { console.error("缺少依赖: npm i chrome-remote-interface"); process.exit(1); }
const { spawn } = require("child_process");
const fs = require("fs");
const net = require("net");

const url = process.argv[2];
const out = process.argv[3];
const readyExpr = process.argv[4] || 'document.title==="READY"';
const W = parseInt(process.argv[5] || "1280");
const H = parseInt(process.argv[6] || "800");
const extraWait = parseInt(process.argv[7] || "400");
const readyTimeout = parseInt(process.argv[8] || "8000");
const chromeBin = process.env.CHROMIUM_BIN || "chromium";

if (!url || !out || !Number.isFinite(W) || !Number.isFinite(H) ||
    !Number.isFinite(extraWait) || extraWait < 0 ||
    !Number.isFinite(readyTimeout) || readyTimeout < 500 || readyTimeout > 60000) {
  console.error("参数错误：需要 url/out，readyTimeoutMs 范围 500..60000");
  process.exit(2);
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const { port } = server.address();
      server.close(() => resolve(port));
    });
  });
}

function killTree(child, signal) {
  if (!child || !child.pid) return;
  try {
    if (process.platform !== "win32") process.kill(-child.pid, signal);
    else child.kill(signal);
  } catch (_) {}
}

(async () => {
  let client;
  let chrome;
  let chromeExited = false;
  try {
    const port = await freePort();
    chrome = spawn(chromeBin, [
      "--headless", "--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage",
      "--disable-crash-reporter", "--disable-breakpad",
      "--remote-debugging-address=127.0.0.1",
      `--remote-debugging-port=${port}`, `--window-size=${W},${H}`, "about:blank",
    ], { detached: process.platform !== "win32", stdio: "ignore" });

    let launchError = null;
    chrome.once("error", error => { launchError = error; });
    chrome.once("exit", () => { chromeExited = true; });
    const launchDeadline = Date.now() + 5000;
    while (!client && Date.now() < launchDeadline) {
      if (launchError) throw launchError;
      try { client = await CDP({ port, host: "127.0.0.1" }); }
      catch (_) { await sleep(100); }
    }
    if (!client) throw new Error("无法在 5s 内连接 Chromium CDP");

    const { Page, Runtime, Emulation } = client;
    await Page.enable();
    await Runtime.enable();
    await Emulation.setDeviceMetricsOverride({ width: W, height: H, deviceScaleFactor: 1, mobile: H > W });
    await Page.navigate({ url });

    const deadline = Date.now() + readyTimeout;
    let lastResult = "none";
    let ready = false;
    while (Date.now() < deadline) {
      try {
        const response = await Runtime.evaluate({ expression: readyExpr, returnByValue: true });
        if (response.exceptionDetails) {
          lastResult = "exception";
        } else {
          lastResult = response.result.type;
          if (isStrictReady(response.result)) { ready = true; break; }
        }
      } catch (_) {
        lastResult = "evaluation-error";
      }
      await sleep(100);
    }
    if (!ready) {
      throw new Error(`readyExpr 未在 ${readyTimeout}ms 内返回布尔 true（最后类型: ${lastResult}）`);
    }

    if (extraWait) await sleep(extraWait);
    const finalResponse = await Runtime.evaluate({ expression: readyExpr, returnByValue: true });
    if (finalResponse.exceptionDetails || !isStrictReady(finalResponse.result)) {
      const finalType = finalResponse.exceptionDetails ? "exception" : finalResponse.result.type;
      throw new Error(`readyExpr 在截图前不再为布尔 true（最后类型: ${finalType}）`);
    }
    const shot = await Page.captureScreenshot({ format: "png" });
    fs.writeFileSync(out, Buffer.from(shot.data, "base64"));
    console.error("saved", out);
  } catch (error) {
    console.error(`SHOT_ERROR: ${error.message}`);
    process.exitCode = 1;
  } finally {
    if (client) {
      try { await client.close(); } catch (_) {}
    }
    if (chrome) {
      killTree(chrome, "SIGTERM");
      await sleep(200);
      if (!chromeExited) killTree(chrome, "SIGKILL");
    }
  }
})();
