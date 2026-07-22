#!/usr/bin/env node
"use strict";

// Generic Chromium runner for deterministic gameplay cases.
// The contract owns setup + input schedule; this runner owns browser input,
// fixed stepping, trace sampling, timeout boundary, hashes and evidence.
// The game may only reset, step and expose a read-only snapshot. It never
// receives the case name or expected result and cannot return a ready-made case.

const crypto = require("crypto");
const fs = require("fs");
const http = require("http");
const net = require("net");
const os = require("os");
const path = require("path");
const { spawn, spawnSync } = require("child_process");

function usage() {
  console.error("usage: node run_gameplay_runtime.js --project DIR [--out FILE] [--self-test]");
}

function parseArgs(argv) {
  const result = {};
  for (let index = 2; index < argv.length; index += 1) {
    const key = argv[index];
    if (key === "--self-test") { result.selfTest = true; continue; }
    if (!key.startsWith("--") || index + 1 >= argv.length) throw new Error(`invalid argument: ${key}`);
    result[key.slice(2)] = argv[++index];
  }
  return result;
}

function sha256File(file) {
  return crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");
}

function sleep(ms) { return new Promise((resolve) => setTimeout(resolve, ms)); }

function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const port = server.address().port;
      server.close(() => resolve(port));
    });
  });
}

function mime(file) {
  return ({
    ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8", ".json": "application/json",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".svg": "image/svg+xml", ".woff2": "font/woff2",
  })[path.extname(file).toLowerCase()] || "application/octet-stream";
}

async function staticServer(project) {
  const server = http.createServer((request, response) => {
    try {
      const pathname = decodeURIComponent(new URL(request.url, "http://localhost").pathname);
      const resolved = path.resolve(project, `.${pathname === "/" ? "/index.html" : pathname}`);
      if (resolved !== project && !resolved.startsWith(`${project}${path.sep}`)) throw new Error("outside project");
      const stat = fs.statSync(resolved);
      const file = stat.isDirectory() ? path.join(resolved, "index.html") : resolved;
      response.writeHead(200, { "Content-Type": mime(file), "Cache-Control": "no-store" });
      fs.createReadStream(file).pipe(response);
    } catch (_) {
      response.writeHead(404); response.end("not found");
    }
  });
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  return { server, port: server.address().port };
}

class CdpClient {
  constructor(ws) { this.ws = ws; this.nextId = 1; this.pending = new Map(); this.listeners = new Map(); }
  static async connect(url) {
    const ws = new WebSocket(url);
    await new Promise((resolve, reject) => {
      ws.addEventListener("open", resolve, { once: true });
      ws.addEventListener("error", reject, { once: true });
    });
    const client = new CdpClient(ws);
    ws.addEventListener("message", (event) => {
      let message;
      try { message = JSON.parse(String(event.data)); } catch (_) { return; }
      if (!message.id) {
        for (const handler of client.listeners.get(message.method) || []) handler(message.params || {});
        return;
      }
      if (!client.pending.has(message.id)) return;
      const { resolve, reject } = client.pending.get(message.id);
      client.pending.delete(message.id);
      if (message.error) reject(new Error(message.error.message));
      else resolve(message.result);
    });
    return client;
  }
  send(method, params = {}) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }
  on(method, handler) {
    const handlers = this.listeners.get(method) || [];
    handlers.push(handler); this.listeners.set(method, handlers);
  }
  close() { try { this.ws.close(); } catch (_) {} }
}

function killTree(child, signal) {
  if (!child || !child.pid) return;
  try {
    if (process.platform !== "win32") process.kill(-child.pid, signal);
    else child.kill(signal);
  } catch (_) {}
}

async function launchChrome(width, height) {
  const port = await freePort();
  const candidates = [
    process.env.CHROMIUM_BIN,
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/chromium", "chromium", "chromium-browser",
  ].filter(Boolean);
  let chrome = null, launchError = null;
  for (const candidate of candidates) {
    chrome = spawn(candidate, [
      "--headless", "--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage",
      "--disable-crash-reporter", "--disable-breakpad", "--remote-debugging-address=127.0.0.1",
      `--remote-debugging-port=${port}`, `--window-size=${width},${height}`, "about:blank",
    ], { detached: process.platform !== "win32", stdio: "ignore" });
    launchError = null;
    chrome.once("error", (error) => { launchError = error; });
    await sleep(100);
    if (!launchError) break;
    chrome = null;
  }
  if (!chrome) throw launchError || new Error("Chromium executable not found");
  const deadline = Date.now() + 5000;
  let page = null;
  while (Date.now() < deadline) {
    if (launchError) throw launchError;
    try {
      const pages = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
      page = pages.find((item) => item.type === "page");
      if (page) break;
    } catch (_) {}
    await sleep(100);
  }
  if (!page) throw new Error("unable to connect to Chromium within 5s");
  return { chrome, client: await CdpClient.connect(page.webSocketDebuggerUrl) };
}

async function evaluate(client, expression) {
  const response = await client.send("Runtime.evaluate", {
    expression, awaitPromise: true, returnByValue: true,
  });
  if (response.exceptionDetails) {
    const detail = response.exceptionDetails.exception || {};
    throw new Error(String(detail.description || detail.value || response.exceptionDetails.text || "browser evaluation failed").split("\n", 1)[0]);
  }
  return response.result.value;
}

async function waitReady(client, pageErrors) {
  const deadline = Date.now() + 8000;
  while (Date.now() < deadline) {
    try {
      const probe = await evaluate(client,
        "(()=>({ready:window.__game?.ready===true," +
        "reset:typeof window.__game?.gameplayAudit?.reset==='function'," +
        "step:typeof window.__game?.gameplayAudit?.step==='function'," +
        "snapshot:typeof window.__game?.gameplayAudit?.snapshot==='function'," +
        "legacy:typeof window.__game?.gameplayAudit?.runCase==='function'}))()");
      if (probe && probe.ready && probe.reset && probe.step && probe.snapshot) return;
      if (probe && probe.ready && probe.legacy && !(probe.reset && probe.step && probe.snapshot)) {
        throw new Error("legacy runCase-only gameplayAudit rejected; reset/step/snapshot required");
      }
    } catch (error) {
      if (String(error && error.message).includes("legacy runCase-only")) throw error;
    }
    if (pageErrors.length) throw new Error(`page exception before gameplayAudit ready: ${pageErrors.slice(0, 3).join(" | ")}`);
    await sleep(100);
  }
  throw new Error("runner-controlled gameplayAudit reset/step/snapshot did not become ready within 8s");
}

function pageError(params) {
  const detail = params && params.exceptionDetails ? params.exceptionDetails : {};
  const exception = detail.exception || {};
  return String(exception.description || exception.value || detail.text || "unknown page exception").split("\n", 1)[0];
}

function finite(value) { return typeof value === "number" && Number.isFinite(value); }

const KEY_CODES = {
  ArrowLeft: 37, ArrowUp: 38, ArrowRight: 39, ArrowDown: 40,
  Space: 32, KeyA: 65, KeyD: 68, KeyW: 87, KeyS: 83,
};

function keyValue(code) {
  if (code === "Space") return " ";
  if (code.startsWith("Key") && code.length === 4) return code.slice(3).toLowerCase();
  return code;
}

async function dispatchInput(client, input) {
  const phase = String(input.phase || "").toLowerCase();
  const down = ["press", "pressed", "down", "keydown"].includes(phase);
  const up = ["release", "released", "up", "keyup"].includes(phase);
  if (!down && !up) throw new Error(`unsupported input phase: ${input.phase}`);
  const code = input.code;
  if (typeof code !== "string" || !KEY_CODES[code]) throw new Error(`unsupported keyboard code: ${code}`);
  await client.send("Input.dispatchKeyEvent", {
    type: down ? "keyDown" : "keyUp",
    code,
    key: keyValue(code),
    windowsVirtualKeyCode: KEY_CODES[code],
    nativeVirtualKeyCode: KEY_CODES[code],
  });
}

function normalizeSnapshot(value, frame) {
  const validationErrors = [];
  const snapshot = value && typeof value === "object" ? value : {};
  if (typeof snapshot.state !== "string" || !snapshot.state.trim()) {
    validationErrors.push(`snapshot ${frame} state must be non-empty`);
  }
  const position = snapshot.position;
  const coordinates = ["x", "y", "z"].filter((key) => position && key in position);
  if (!coordinates.length || !coordinates.every((key) => finite(position[key]))) {
    validationErrors.push(`snapshot ${frame} position must contain finite x/y/z`);
  }
  if (typeof snapshot.result !== "string" || !snapshot.result.trim()) {
    validationErrors.push(`snapshot ${frame} result must be non-empty`);
  }
  if (typeof snapshot.reason !== "string" || !snapshot.reason.trim()) {
    validationErrors.push(`snapshot ${frame} reason must be non-empty`);
  }
  return {
    validationErrors,
    sample: {
      frame,
      state: snapshot.state,
      position: position && typeof position === "object" ? position : {},
    },
    result: snapshot.result,
    reason: snapshot.reason,
    done: snapshot.done === true,
  };
}

async function runDrivenCase(client, expectedCase) {
  const driver = expectedCase.driver || {};
  const seed = driver.seed;
  const dt = driver.dt;
  const maxFrames = driver.max_frames;
  const scheduled = Array.isArray(driver.inputs) ? driver.inputs : [];
  const validationErrors = [];
  const trace = [];
  const dispatched = [];
  const held = new Set();
  await evaluate(client,
    `(async()=>window.__game.gameplayAudit.reset(${JSON.stringify(seed)},${JSON.stringify(driver.setup || {})}))()`);
  let finalSnapshot = normalizeSnapshot(await evaluate(client,
    "window.__game.gameplayAudit.snapshot()"), 0);
  validationErrors.push(...finalSnapshot.validationErrors);
  trace.push(finalSnapshot.sample);
  let finalFrame = 0;
  for (let frame = 1; frame <= maxFrames; frame += 1) {
    for (const item of scheduled.filter((entry) => entry.frame === frame)) {
      await dispatchInput(client, item);
      const phase = String(item.phase).toLowerCase();
      if (["press", "pressed", "down", "keydown"].includes(phase)) held.add(item.code);
      else held.delete(item.code);
      dispatched.push({ frame, action: item.action, phase: item.phase, code: item.code });
    }
    await evaluate(client, `window.__game.gameplayAudit.step(${JSON.stringify(dt)})`);
    finalSnapshot = normalizeSnapshot(await evaluate(client,
      "window.__game.gameplayAudit.snapshot()"), frame);
    validationErrors.push(...finalSnapshot.validationErrors);
    trace.push(finalSnapshot.sample);
    finalFrame = frame;
    if (finalSnapshot.done) break;
  }
  for (const code of held) {
    await dispatchInput(client, { code, phase: "release" });
  }
  if (!dispatched.length) validationErrors.push("runner did not dispatch any scheduled browser input");
  if (trace.length < 2) validationErrors.push("runner must sample at least two fixed-step states");
  const actual = finalSnapshot.result;
  return {
    ...expectedCase,
    actual,
    seed,
    dt,
    inputs: dispatched,
    terminal: { state: finalSnapshot.sample.state, reason: finalSnapshot.reason },
    pass: validationErrors.length === 0 && actual === expectedCase.expected,
    validation_errors: validationErrors,
    trace: trace.slice(0, 1801),
    assertions: [
      "runner dispatched contract-owned inputs through Chromium CDP",
      "runner sampled reset/step/snapshot without passing case name or expected result to the game",
      `runner completed ${finalFrame} fixed steps`,
    ],
    driver_protocol: "runner-controlled-v1",
    input_source: "chromium-cdp",
  };
}

async function runProject(project, outputPath) {
  const contractPath = path.join(project, "GAMEPLAY_CONTRACT.json");
  const indexPath = path.join(project, "index.html");
  const staticAudit = spawnSync("python3", [path.join(__dirname, "audit_gameplay_report.py"), "--project", project, "--contract-only"], { encoding: "utf8" });
  if (staticAudit.status !== 0) throw new Error(`gameplay contract audit failed: ${(staticAudit.stdout || staticAudit.stderr).trim()}`);
  const contract = JSON.parse(fs.readFileSync(contractPath, "utf8"));
  const viewport = contract.viewport || { width: 450, height: 800 };
  const report = {
    version: 1, status: "FAIL", driver_protocol: "runner-controlled-v1",
    contract_sha256: sha256File(contractPath), index_sha256: sha256File(indexPath),
    bot_sha256: sha256File(__filename), cases: [], problems: [],
  };
  let server = null, chrome = null, client = null;
  try {
    const served = await staticServer(project); server = served.server;
    const launched = await launchChrome(viewport.width, viewport.height); chrome = launched.chrome; client = launched.client;
    const pageErrors = [];
    client.on("Runtime.exceptionThrown", (params) => pageErrors.push(pageError(params)));
    await client.send("Page.enable"); await client.send("Runtime.enable");
    await client.send("Emulation.setDeviceMetricsOverride", {
      width: viewport.width, height: viewport.height, deviceScaleFactor: 1, mobile: viewport.height > viewport.width,
    });
    await client.send("Page.navigate", { url: `http://127.0.0.1:${served.port}/index.html?gameplayAudit=1` });
    await waitReady(client, pageErrors);
    for (const expectedCase of contract.cases) {
      const actual = await Promise.race([
        runDrivenCase(client, expectedCase),
        new Promise((_, reject) => setTimeout(() => reject(new Error("case timeout")), 5000)),
      ]);
      report.cases.push(actual);
      if (!actual.pass) {
        const detail = actual.validation_errors.length ? `: ${actual.validation_errors.join("; ")}` : "";
        report.problems.push(`case ${expectedCase.name} did not return expected result ${expectedCase.expected}${detail}`);
      }
    }
    if (pageErrors.length) report.problems.push(...pageErrors.map((item) => `page exception: ${item}`));
    if (!report.problems.length) report.status = "PASS";
  } finally {
    if (client) client.close();
    if (chrome) { killTree(chrome, "SIGTERM"); await sleep(150); killTree(chrome, "SIGKILL"); }
    if (server) await new Promise((resolve) => server.close(resolve));
  }
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.writeFileSync(outputPath, `${JSON.stringify(report, null, 2)}\n`);
  return report;
}

async function selfTest() {
  const project = fs.mkdtempSync(path.join(os.tmpdir(), "gameplay-runtime-"));
  fs.mkdirSync(path.join(project, "evidence"));
  const cases = [
    { name: "win", category: "success", expected: "ready" },
    { name: "short", category: "failure", rule: "strength", side: "short", expected: "gameover:short" },
    { name: "long", category: "failure", rule: "strength", side: "long", expected: "gameover:long" },
    { name: "inside", category: "boundary", rule: "hitbox", side: "inside", expected: "ready" },
    { name: "outside", category: "boundary", rule: "hitbox", side: "outside", expected: "gameover" },
  ];
  for (const item of cases) {
    const strengthFrames = item.name === "short" ? 2 : item.name === "long" ? 20 : 10;
    const edgeX = item.name === "outside" ? 121 : 99;
    const edge = ["inside", "outside"].includes(item.name);
    item.driver = {
      seed: 4242, dt: 1 / 60, max_frames: edge ? 1 : strengthFrames,
      setup: edge
        ? { mode: "edge", x: edgeX, boundary: 110, stopFrame: 1 }
        : { mode: "strength", min: 50, max: 150, stopFrame: strengthFrames },
      inputs: [
        { frame: 1, action: "move-right", phase: "press", code: "ArrowRight" },
        { frame: edge ? 1 : strengthFrames, action: "move-right", phase: "release", code: "ArrowRight" },
      ],
    };
  }
  fs.writeFileSync(path.join(project, "GAMEPLAY_CONTRACT.json"), JSON.stringify({
    version: 1, source: "gdd-module-8", bot: "skill:run_gameplay_runtime.js",
    viewport: { width: 400, height: 700 }, required_categories: ["success", "failure", "boundary"],
    coverage: [
      { category: "failure", rule: "strength", required_sides: ["short", "long"] },
      { category: "boundary", rule: "hitbox", required_sides: ["inside", "outside"] },
    ], cases,
  }));
  const values = Object.fromEntries(cases.map((item) => [item.name, item.expected]));
  fs.writeFileSync(path.join(project, "index.html"), `<!doctype html><script>
    const values=${JSON.stringify(values)};
    window.__game={ready:true,gameplayAudit:{runCase(name){return {actual:values[name],seed:4242,dt:1/60,inputs:[{frame:1,action:'move-right',phase:'press'}],trace:[{frame:0,state:'start',position:{x:0,y:0}},{frame:1,state:values[name],position:{x:1,y:0}}],terminal:{state:values[name],reason:'lookup'},assertions:['fake but complete']}}}};
  </script></html>`);
  const output = path.join(project, "evidence", "gameplay-audit.json");
  let legacyRejected = false;
  try { await runProject(project, output); } catch (error) {
    legacyRejected = String(error.message).includes("reset/step/snapshot");
  }
  if (!legacyRejected) throw new Error("complete lookup-table runCase hook was not rejected");
  fs.writeFileSync(path.join(project, "index.html"), `<!doctype html><script>
    let x=0,frame=0,right=false,result='ready',setup={};
    addEventListener('keydown',e=>{if(e.code==='ArrowRight')right=true;});
    addEventListener('keyup',e=>{if(e.code==='ArrowRight')right=false;});
    window.__game={ready:true,gameplayAudit:{
      reset(seed,next){setup=next;x=next.x||0;frame=0;right=false;result='ready';},
      step(dt){frame++;if(right)x+=10;
        if(frame>=setup.stopFrame){
          if(setup.mode==='strength')result=x<setup.min?'gameover:short':x>setup.max?'gameover:long':'ready';
          else result=x>setup.boundary?'gameover':'ready';
        }},
      snapshot(){return {state:result==='ready'?'play':'gameover',position:{x,y:0},result,reason:'state-machine-derived',done:frame>=setup.stopFrame};}
    }};
  </script></html>`);
  const report = await runProject(project, output);
  const audit = spawnSync("python3", [path.join(__dirname, "audit_gameplay_report.py"), "--project", project], { encoding: "utf8" });
  if (report.status !== "PASS" || audit.status !== 0) throw new Error((audit.stdout || audit.stderr).trim());
  console.log("GAMEPLAY_RUNTIME_SELFTEST: PASS");
}

async function main() {
  const args = parseArgs(process.argv);
  if (args.selfTest) { await selfTest(); return 0; }
  if (!args.project) { usage(); return 2; }
  const project = path.resolve(args.project);
  const output = path.resolve(args.out || path.join(project, "evidence", "gameplay-audit.json"));
  if (!fs.statSync(project).isDirectory() || (output !== project && !output.startsWith(`${project}${path.sep}`))) {
    throw new Error("project must exist and output must stay inside project");
  }
  const report = await runProject(project, output);
  if (report.status === "PASS") { console.log("GAMEPLAY_RUNTIME: PASS"); return 0; }
  for (const problem of report.problems) console.error(`FAIL: ${problem}`);
  console.error(`GAMEPLAY_RUNTIME: FAIL (${report.problems.length} problem(s))`); return 1;
}

main().then((code) => { process.exitCode = code; }).catch((error) => {
  console.error(`GAMEPLAY_RUNTIME: FAIL ${error.message}`); process.exitCode = 1;
});
