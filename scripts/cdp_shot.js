// 用法: node cdp_shot.js <url> <out.png> [readyExpr] [w] [h] [extraWaitMs]
// 等 readyExpr（默认 document.title==="READY"）为真后截图
// 依赖: npm i chrome-remote-interface（本目录或上级 node_modules 均可）
let CDP;
for (const p of ["chrome-remote-interface", "/tmp/node_modules/chrome-remote-interface"]) {
  try { CDP = require(p); break; } catch (e) {}
}
if (!CDP) { console.error("缺少依赖: npm i chrome-remote-interface"); process.exit(1); }
const { execFile } = require("child_process");
const fs = require("fs");

const url = process.argv[2];
const out = process.argv[3];
const readyExpr = process.argv[4] || 'document.title==="READY"';
const W = parseInt(process.argv[5] || "1280");
const H = parseInt(process.argv[6] || "800");
const extraWait = parseInt(process.argv[7] || "400");
const PORT = 9222;

const chrome = execFile("chromium", [
  "--headless", "--disable-gpu", "--no-sandbox",
  `--remote-debugging-port=${PORT}`, `--window-size=${W},${H}`, "about:blank",
], () => {});

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

(async () => {
  let client;
  for (let i = 0; i < 30; i++) {
    try { client = await CDP({ port: PORT }); break; } catch (e) { await sleep(500); }
  }
  if (!client) { console.error("no cdp"); process.exit(1); }
  const { Page, Runtime, Emulation } = client;
  await Page.enable(); await Runtime.enable();
  await Emulation.setDeviceMetricsOverride({ width: W, height: H, deviceScaleFactor: 1, mobile: H > W });
  await Page.navigate({ url });
  let ok = false;
  for (let i = 0; i < 120; i++) {
    await sleep(500);
    try {
      const r = await Runtime.evaluate({ expression: readyExpr });
      if (r.result.value) { ok = true; break; }
    } catch (e) {}
  }
  console.error("ready:", ok);
  await sleep(extraWait);
  const shot = await Page.captureScreenshot({ format: "png" });
  fs.writeFileSync(out, Buffer.from(shot.data, "base64"));
  console.error("saved", out);
  await client.close();
  chrome.kill("SIGKILL");
  process.exit(0);
})();
