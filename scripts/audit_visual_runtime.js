#!/usr/bin/env node
"use strict";

// Browser-level visual/camera audit for simple HTML5 games.
// No npm dependency: Node 22+ provides fetch and WebSocket; Chromium is launched
// directly and controlled through the DevTools protocol.

const crypto = require("crypto");
const fs = require("fs");
const http = require("http");
const net = require("net");
const path = require("path");
const { spawn, spawnSync } = require("child_process");

function usage() {
  console.error("用法: node scripts/audit_visual_runtime.js --project DIR --phase design|seed|production --out FILE [--baseline FILE]");
}

function parseArgs(argv) {
  const result = {};
  for (let i = 2; i < argv.length; i += 1) {
    const key = argv[i];
    if (key === "--self-test") { result.selfTest = true; continue; }
    if (!key.startsWith("--") || i + 1 >= argv.length) throw new Error(`invalid argument: ${key}`);
    result[key.slice(2)] = argv[++i];
  }
  return result;
}

function finite(value) { return typeof value === "number" && Number.isFinite(value); }
function clamp(value, low, high) { return Math.max(low, Math.min(high, value)); }

function rect(value, label, problems) {
  if (!value || typeof value !== "object") {
    problems.push(`${label} must be an object`);
    return null;
  }
  const result = {
    x: value.x, y: value.y, width: value.width, height: value.height,
  };
  for (const [key, number] of Object.entries(result)) {
    if (!finite(number)) problems.push(`${label}.${key} must be finite`);
  }
  if (!finite(result.width) || result.width <= 0 || !finite(result.height) || result.height <= 0) {
    problems.push(`${label} must have positive width/height`);
    return null;
  }
  return result;
}

function intersectionArea(a, b) {
  const x0 = Math.max(a.x, b.x);
  const y0 = Math.max(a.y, b.y);
  const x1 = Math.min(a.x + a.width, b.x + b.width);
  const y1 = Math.min(a.y + a.height, b.y + b.height);
  return Math.max(0, x1 - x0) * Math.max(0, y1 - y0);
}

function unionIntersectionArea(subject, rects) {
  const clips = rects.map((item) => {
    const x0 = Math.max(subject.x, item.x);
    const y0 = Math.max(subject.y, item.y);
    const x1 = Math.min(subject.x + subject.width, item.x + item.width);
    const y1 = Math.min(subject.y + subject.height, item.y + item.height);
    return x1 > x0 && y1 > y0 ? { x0, y0, x1, y1 } : null;
  }).filter(Boolean);
  const xs = [...new Set(clips.flatMap((item) => [item.x0, item.x1]))].sort((a, b) => a - b);
  let total = 0;
  for (let index = 1; index < xs.length; index += 1) {
    const left = xs[index - 1], right = xs[index];
    const intervals = clips
      .filter((item) => item.x0 < right && item.x1 > left)
      .map((item) => [item.y0, item.y1])
      .sort((a, b) => a[0] - b[0]);
    let covered = 0, start = null, end = null;
    for (const [low, high] of intervals) {
      if (start === null) { start = low; end = high; }
      else if (low <= end) end = Math.max(end, high);
      else { covered += end - start; start = low; end = high; }
    }
    if (start !== null) covered += end - start;
    total += (right - left) * covered;
  }
  return total;
}

function unionBounds(bounds) {
  if (!bounds.length) return null;
  const x0 = Math.min(...bounds.map((r) => r.x));
  const y0 = Math.min(...bounds.map((r) => r.y));
  const x1 = Math.max(...bounds.map((r) => r.x + r.width));
  const y1 = Math.max(...bounds.map((r) => r.y + r.height));
  return { x: x0, y: y0, width: x1 - x0, height: y1 - y0 };
}

function cameraSample(sample, label, problems) {
  const camera = sample && sample.camera;
  if (!camera || typeof camera !== "object") {
    problems.push(`${label}.camera must be an object`);
    return null;
  }
  const values = {
    x: camera.x, y: camera.y, zoom: camera.zoom,
    targetX: camera.targetX, targetY: camera.targetY, targetZoom: camera.targetZoom,
  };
  for (const [key, value] of Object.entries(values)) {
    if (!finite(value)) problems.push(`${label}.camera.${key} must be finite`);
  }
  return Object.values(values).every(finite) ? values : null;
}

function validateCase(contract, caseDef, result, phase = "production") {
  const problems = [];
  if (!result || typeof result !== "object" || !Array.isArray(result.samples) || !result.samples.length) {
    return { problems: [`case ${caseDef.name} returned no samples`], metrics: null };
  }
  if (caseDef.behavior === "transition" &&
      (!Array.isArray(result.events) || !result.events.includes(caseDef.trigger_event))) {
    problems.push(`case ${caseDef.name} did not report trigger_event ${caseDef.trigger_event}`);
  }
  if (result.samples.length > caseDef.max_frames) {
    problems.push(`case ${caseDef.name} exceeded max_frames (${result.samples.length}/${caseDef.max_frames})`);
  }
  const camera = [];
  const requiredBoundsBySample = [];
  let primaryAreaRatio = null;
  let groupAreaRatio = null;

  for (let index = 0; index < result.samples.length; index += 1) {
    const sample = result.samples[index];
    const label = `case ${caseDef.name} sample ${index}`;
    if (!sample || typeof sample !== "object") {
      problems.push(`${label} must be an object`);
      continue;
    }
    if (index === result.samples.length - 1 && sample.state !== caseDef.state) {
      problems.push(`${label}.state must end at ${caseDef.state}`);
    }
    const viewport = rect(
      sample.viewport && { x: 0, y: 0, width: sample.viewport.width, height: sample.viewport.height },
      `${label}.viewport`, problems,
    );
    if (viewport && (viewport.width !== contract.viewport.width || viewport.height !== contract.viewport.height)) {
      problems.push(
        `${label}.viewport ${viewport.width}x${viewport.height} must match contract ` +
        `${contract.viewport.width}x${contract.viewport.height}`,
      );
    }
    const cam = caseDef.behavior === "static" ? null : cameraSample(sample, label, problems);
    if (cam) camera.push(cam);
    const entities = sample.entities;
    if (!entities || typeof entities !== "object") {
      problems.push(`${label}.entities must be an object`);
      continue;
    }
    const hudRects = [];
    if (sample.hud !== undefined && !Array.isArray(sample.hud)) {
      problems.push(`${label}.hud must be an array`);
    }
    for (let h = 0; h < (Array.isArray(sample.hud) ? sample.hud.length : 0); h += 1) {
      const hudRect = rect(sample.hud[h] && sample.hud[h].bounds, `${label}.hud[${h}].bounds`, problems);
      if (hudRect) hudRects.push(hudRect);
    }
    const currentRequired = [];
    for (const entityName of caseDef.required_visible) {
      const entity = entities[entityName];
      const spec = contract.entities[entityName];
      if (!entity || typeof entity !== "object") {
        problems.push(`${label} missing required entity ${entityName}`);
        continue;
      }
      if (entity.basis !== spec.measurement) {
        problems.push(`${label}.${entityName}.basis must be ${spec.measurement}`);
      }
      const phaseSources = caseDef.required_render_sources &&
        caseDef.required_render_sources[entityName] &&
        caseDef.required_render_sources[entityName][phase];
      if (Array.isArray(phaseSources) && phaseSources.length && !phaseSources.includes(entity.render_source)) {
        problems.push(
          `${label}.${entityName}.render_source ${JSON.stringify(entity.render_source)} ` +
          `must be one of ${JSON.stringify(phaseSources)} for ${phase}`,
        );
      }
      const bounds = rect(entity.bounds, `${label}.${entityName}.bounds`, problems);
      if (!bounds || !viewport) continue;
      if (spec.space === "world") currentRequired.push(bounds);
      if (finite(spec.min_visible_width_px) && bounds.width < spec.min_visible_width_px) {
        problems.push(`${label}.${entityName} visible width ${bounds.width} < ${spec.min_visible_width_px}`);
      }
      if (finite(spec.min_visible_height_px) && bounds.height < spec.min_visible_height_px) {
        problems.push(`${label}.${entityName} visible height ${bounds.height} < ${spec.min_visible_height_px}`);
      }
      const area = bounds.width * bounds.height;
      const visibleRatio = intersectionArea(bounds, viewport) / area;
      const minVisible = finite(caseDef.min_visible_ratio) ? caseDef.min_visible_ratio : 0.9;
      if (visibleRatio + 1e-9 < minVisible) {
        problems.push(`${label}.${entityName} visible ratio ${visibleRatio.toFixed(3)} < ${minVisible}`);
      }
      if (spec.space === "world") {
        const maxHudOverlap = finite(caseDef.max_hud_overlap_ratio) ? caseDef.max_hud_overlap_ratio : 0.05;
        const overlapRatio = unionIntersectionArea(bounds, hudRects) / area;
        if (overlapRatio - 1e-9 > maxHudOverlap) {
          problems.push(`${label}.${entityName} HUD overlap ${overlapRatio.toFixed(3)} > ${maxHudOverlap}`);
        }
      } else {
        const hudRegionRatio = unionIntersectionArea(bounds, hudRects) / area;
        if (hudRegionRatio + 1e-9 < 0.9) {
          problems.push(`${label}.${entityName} is declared as HUD but only ${hudRegionRatio.toFixed(3)} lies in HUD regions`);
        }
      }
      if (index === result.samples.length - 1 && entityName === contract.baseline.primary_entity) {
        primaryAreaRatio = area / (viewport.width * viewport.height);
      }
    }
    requiredBoundsBySample.push(currentRequired);
    if (index === result.samples.length - 1 && viewport) {
      const group = unionBounds(currentRequired);
      if (group) groupAreaRatio = (group.width * group.height) / (viewport.width * viewport.height);
    }
  }

  if (caseDef.behavior === "locked" && camera.length > 1) {
    const first = camera[0];
    const pxTol = finite(caseDef.lock_tolerance_px) ? caseDef.lock_tolerance_px : 0.5;
    const zoomTol = finite(caseDef.lock_tolerance_zoom) ? caseDef.lock_tolerance_zoom : 0.002;
    for (let index = 1; index < camera.length; index += 1) {
      const item = camera[index];
      if (Math.hypot(item.x - first.x, item.y - first.y) > pxTol || Math.abs(item.zoom - first.zoom) > zoomTol) {
        problems.push(`case ${caseDef.name} camera drifted during locked state at sample ${index}`);
        break;
      }
    }
  }

  if ((caseDef.behavior === "transition" || caseDef.behavior === "settled") && camera.length) {
    const pxTol = finite(caseDef.settle_tolerance_px) ? caseDef.settle_tolerance_px : 1;
    const zoomTol = finite(caseDef.settle_tolerance_zoom) ? caseDef.settle_tolerance_zoom : 0.005;
    const distances = camera.map((item) => ({
      position: Math.hypot(item.x - item.targetX, item.y - item.targetY),
      zoom: Math.abs(item.zoom - item.targetZoom),
    }));
    const last = distances[distances.length - 1];
    if (last.position > pxTol || last.zoom > zoomTol) {
      problems.push(`case ${caseDef.name} camera did not settle (px=${last.position.toFixed(3)}, zoom=${last.zoom.toFixed(4)})`);
    }
    if (caseDef.behavior === "transition" && caseDef.allow_overshoot !== true) {
      for (let index = 1; index < distances.length; index += 1) {
        if (distances[index].position > distances[index - 1].position + pxTol ||
            distances[index].zoom > distances[index - 1].zoom + zoomTol) {
          problems.push(`case ${caseDef.name} camera moved away from target at sample ${index}`);
          break;
        }
      }
    }
    if (caseDef.behavior === "transition") {
      const beforeSample = result.before;
      if (!beforeSample || typeof beforeSample !== "object") {
        problems.push(`case ${caseDef.name} must return a real pre-trigger probe in result.before`);
      } else {
        if (beforeSample.state !== caseDef.before_state) {
          problems.push(
            `case ${caseDef.name} before.state must be ${caseDef.before_state}, got ${beforeSample.state}`,
          );
        }
        const beforeCamera = cameraSample(beforeSample, `case ${caseDef.name} before`, problems);
        if (beforeCamera) {
          const afterTarget = camera[0];
          const afterCamera = camera[camera.length - 1];
          const targetDelta = Math.hypot(
            afterTarget.targetX - beforeCamera.targetX,
            afterTarget.targetY - beforeCamera.targetY,
          );
          const cameraDelta = Math.hypot(
            afterCamera.x - beforeCamera.x,
            afterCamera.y - beforeCamera.y,
          );
          if (targetDelta + 1e-9 < caseDef.min_target_delta_px) {
            problems.push(
              `case ${caseDef.name} retarget delta ${targetDelta.toFixed(3)} < ${caseDef.min_target_delta_px}`,
            );
          }
          if (cameraDelta + 1e-9 < caseDef.min_camera_delta_px) {
            problems.push(
              `case ${caseDef.name} camera movement ${cameraDelta.toFixed(3)} < ${caseDef.min_camera_delta_px}`,
            );
          }
          for (const axis of caseDef.required_target_axes || []) {
            const key = axis === "x" ? "targetX" : "targetY";
            const delta = Math.abs(afterTarget[key] - beforeCamera[key]);
            if (delta + 1e-9 < caseDef.min_axis_target_delta_px) {
              problems.push(
                `case ${caseDef.name} target ${axis} delta ${delta.toFixed(3)} < ` +
                `${caseDef.min_axis_target_delta_px}`,
              );
            }
          }
        }
      }
    }
  }

  return {
    problems,
    metrics: {
      samples: result.samples.length,
      primary_area_ratio: primaryAreaRatio,
      required_group_area_ratio: groupAreaRatio,
    },
  };
}

function compareBaseline(contract, currentMetrics, baseline) {
  const problems = [];
  if (!baseline || typeof baseline !== "object" || !baseline.metrics) {
    return ["production phase requires a valid visual baseline"];
  }
  const primaryTol = contract.baseline.max_primary_area_delta_ratio;
  const groupTol = contract.baseline.max_group_area_delta_ratio;
  for (const caseName of contract.baseline.capture_cases) {
    const oldMetric = baseline.metrics[caseName];
    const newMetric = currentMetrics[caseName];
    if (!oldMetric || !newMetric) {
      problems.push(`baseline comparison missing case ${caseName}`);
      continue;
    }
    for (const [key, tolerance, label] of [
      ["primary_area_ratio", primaryTol, "primary area"],
      ["required_group_area_ratio", groupTol, "required group area"],
    ]) {
      const oldValue = oldMetric[key];
      const newValue = newMetric[key];
      if (!finite(oldValue) || !finite(newValue) || oldValue <= 0) {
        problems.push(`baseline comparison ${caseName} has invalid ${label} metric`);
        continue;
      }
      const delta = Math.abs(newValue - oldValue) / oldValue;
      if (delta > tolerance) {
        problems.push(`${caseName} ${label} drift ${delta.toFixed(3)} > ${tolerance}`);
      }
    }
  }
  return problems;
}

function sha256File(file) {
  return crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");
}

function artifactDigest(project, artifacts) {
  const hash = crypto.createHash("sha256");
  for (const rel of [...artifacts].sort()) {
    hash.update(rel).update("\0").update(fs.readFileSync(path.join(project, rel))).update("\0");
  }
  return hash.digest("hex");
}

function safeName(value) { return value.replace(/[^A-Za-z0-9._-]+/g, "-"); }
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
  const ext = path.extname(file).toLowerCase();
  return ({
    ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8", ".json": "application/json",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".svg": "image/svg+xml", ".woff2": "font/woff2",
  })[ext] || "application/octet-stream";
}

async function staticServer(project) {
  const server = http.createServer((req, res) => {
    try {
      const requestPath = decodeURIComponent(new URL(req.url, "http://localhost").pathname);
      const resolved = path.resolve(project, `.${requestPath === "/" ? "/index.html" : requestPath}`);
      if (resolved !== project && !resolved.startsWith(`${project}${path.sep}`)) throw new Error("outside project");
      const stat = fs.statSync(resolved);
      const file = stat.isDirectory() ? path.join(resolved, "index.html") : resolved;
      res.writeHead(200, { "Content-Type": mime(file), "Cache-Control": "no-store" });
      fs.createReadStream(file).pipe(res);
    } catch (_) {
      res.writeHead(404); res.end("not found");
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
    handlers.push(handler);
    this.listeners.set(method, handlers);
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
  let chrome = null;
  let launchError = null;
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
  if (response.exceptionDetails) throw new Error("browser evaluation failed");
  return response.result.value;
}

function pageExceptionMessage(params) {
  const detail = params && params.exceptionDetails ? params.exceptionDetails : {};
  const exception = detail.exception || {};
  const raw = exception.description || exception.value || detail.text || "unknown page exception";
  const firstLine = String(raw).split("\n", 1)[0];
  const location = detail.url
    ? ` at ${detail.url}:${Number(detail.lineNumber || 0) + 1}:${Number(detail.columnNumber || 0) + 1}`
    : "";
  return `${firstLine}${location}`;
}

async function waitReady(client, pageErrors) {
  const started = Date.now();
  const deadline = Date.now() + 8000;
  while (Date.now() < deadline) {
    try {
      const ready = await evaluate(client,
        "!!window.__game && window.__game.ready === true && !!window.__game.visualAudit && " +
        "typeof window.__game.visualAudit.snapshot === 'function' && " +
        "typeof window.__game.visualAudit.runCase === 'function'");
      if (ready === true) return;
    } catch (_) {}
    if (pageErrors.length && Date.now() - started >= 1000) {
      throw new Error(`page exception before visualAudit ready: ${pageErrors.slice(0, 3).join(" | ")}`);
    }
    await sleep(100);
  }
  const detail = pageErrors.length ? `; page exceptions: ${pageErrors.slice(0, 3).join(" | ")}` : "";
  throw new Error(`window.__game.visualAudit did not become ready within 8s${detail}`);
}

function nextAttempt(prior, phase, ledgerAttempts = 0) {
  const reportAttempts = prior && prior.phase === phase &&
    Number.isInteger(prior.attempt) && prior.attempt > 0 ? prior.attempt : 0;
  return Math.max(reportAttempts, ledgerAttempts) + 1;
}

const PIPELINE_CONTROLLER_FILE = "/etc/pi/pipeline-controller.json";

function readControllerIdentity(controllerPath = PIPELINE_CONTROLLER_FILE) {
  if (!fs.existsSync(controllerPath)) return null;
  let value;
  try { value = JSON.parse(fs.readFileSync(controllerPath, "utf8")); }
  catch (_) { throw new Error("pipeline controller identity is invalid JSON"); }
  const taskId = value && value.task_id;
  const stateDir = value && value.audit_state_dir;
  if (!taskId || !/^[A-Za-z0-9][A-Za-z0-9._-]{1,126}[A-Za-z0-9]$/.test(taskId)) {
    throw new Error("pipeline controller identity has an invalid task_id");
  }
  if (typeof stateDir !== "string" || !path.isAbsolute(stateDir)) {
    throw new Error("pipeline controller identity requires an absolute audit_state_dir");
  }
  return { taskId, stateDir };
}

function attemptLedgerLocation(project, controllerPath = PIPELINE_CONTROLLER_FILE) {
  const controller = readControllerIdentity(controllerPath);
  if (controller) {
    const root = path.resolve(controller.stateDir);
    const id = crypto.createHash("sha256").update(controller.taskId).update("\0").update(project).digest("hex");
    return { path: path.join(root, `${id}.jsonl`), reference: `controller://${id}` };
  }
  const stateDir = process.env.VISUAL_AUDIT_STATE_DIR;
  const runId = process.env.VISUAL_AUDIT_RUN_ID;
  if (stateDir || runId) {
    if (!stateDir || !runId || !/^[A-Za-z0-9][A-Za-z0-9._-]{1,126}[A-Za-z0-9]$/.test(runId)) {
      throw new Error("controller audit state requires valid VISUAL_AUDIT_STATE_DIR and VISUAL_AUDIT_RUN_ID");
    }
    const root = path.resolve(stateDir);
    const id = crypto.createHash("sha256").update(runId).update("\0").update(project).digest("hex");
    return { path: path.join(root, `${id}.jsonl`), reference: `controller://${id}` };
  }
  const ledgerPath = path.join(project, "evidence", ".visual-audit-attempts.jsonl");
  return { path: ledgerPath, reference: path.relative(project, ledgerPath) };
}

function reserveAttempt(project, phase, prior, contractSha, controllerPath = PIPELINE_CONTROLLER_FILE) {
  const location = attemptLedgerLocation(project, controllerPath);
  const ledgerPath = location.path;
  fs.mkdirSync(path.dirname(ledgerPath), { recursive: true });
  let ledgerAttempts = 0;
  if (fs.existsSync(ledgerPath)) {
    const lines = fs.readFileSync(ledgerPath, "utf8").split(/\r?\n/).filter(Boolean);
    for (let index = 0; index < lines.length; index += 1) {
      let item;
      try { item = JSON.parse(lines[index]); }
      catch (_) { throw new Error(`visual audit attempt ledger is corrupt at line ${index + 1}; refusing to reset`); }
      if (item && item.version === 1 && item.phase === phase &&
          Number.isInteger(item.attempt) && item.attempt > ledgerAttempts) {
        ledgerAttempts = item.attempt;
      }
    }
  }
  const completedAttempts = Math.max(
    ledgerAttempts,
    prior && prior.phase === phase && Number.isInteger(prior.attempt) ? prior.attempt : 0,
  );
  if (completedAttempts >= 3) {
    throw new Error(
      "visual audit repair limit reached: the detailed third-attempt report is terminal; " +
      "do not reserve another attempt",
    );
  }
  const attempt = completedAttempts + 1;
  fs.appendFileSync(ledgerPath, `${JSON.stringify({
    version: 1, phase, attempt, contract_sha256: contractSha,
    reserved_at: new Date().toISOString(),
  })}\n`);
  return { attempt, ledgerPath, ledgerReference: location.reference };
}

function selfTest() {
  const contract = {
    viewport: { width: 400, height: 700 },
    entities: {
      player: { space: "world", measurement: "visible-pixels", min_visible_height_px: 80 },
      target: { space: "world", measurement: "geometry" },
      meter: { space: "hud", measurement: "geometry" },
    },
    baseline: { primary_entity: "player", capture_cases: ["charge"], max_primary_area_delta_ratio: 0.2, max_group_area_delta_ratio: 0.2 },
  };
  const sources = { player: { seed: ["generated-seed"], production: ["generated-sprite"] } };
  const caseDef = {
    name: "charge", entry: "scripted", state: "charging", behavior: "locked",
    required_visible: ["player", "target", "meter"], required_render_sources: sources, max_frames: 4,
  };
  const sample = (x = 100, height = 100, renderSource = "generated-sprite") => ({
    state: "charging", viewport: { width: 400, height: 700 },
    camera: { x, y: 0, zoom: 1, targetX: x, targetY: 0, targetZoom: 1 },
    entities: {
      player: { basis: "visible-pixels", render_source: renderSource, bounds: { x: 80, y: 400, width: 80, height } },
      target: { basis: "geometry", bounds: { x: 220, y: 380, width: 100, height: 80 } },
      meter: { basis: "geometry", bounds: { x: 20, y: 10, width: 120, height: 30 } },
    },
    hud: [{ bounds: { x: 0, y: 0, width: 400, height: 60 } }],
  });
  const pass = validateCase(contract, caseDef, { samples: [sample(), sample()] });
  const tiny = validateCase(contract, caseDef, { samples: [sample(100, 30)] });
  const drift = validateCase(contract, caseDef, { samples: [sample(100), sample(110)] });
  const fallback = validateCase(contract, caseDef, { samples: [sample(100, 100, "fallback")] });
  const fallbackDesign = validateCase(
    contract, caseDef, { samples: [sample(100, 100, "fallback")] }, "design",
  );
  const transitionCase = {
    name: "retarget", entry: "scripted", state: "settled", before_state: "ready",
    behavior: "transition", trigger_event: "landed", required_visible: ["player", "target"],
    required_render_sources: sources, max_frames: 4, min_target_delta_px: 8,
    min_camera_delta_px: 8, required_target_axes: ["y"], min_axis_target_delta_px: 8,
  };
  const transitionSample = (x, y, targetX, targetY, state = "settled") => ({
    ...sample(x, 100), state,
    camera: { x, y, zoom: 1, targetX, targetY, targetZoom: 1 },
  });
  const transition = validateCase(contract, transitionCase, {
    events: ["landed"], before: transitionSample(0, 0, 0, 0, "ready"),
    samples: [transitionSample(5, 8, 20, 20), transitionSample(20, 20, 20, 20)],
  });
  const fakeTransition = validateCase(contract, transitionCase, {
    events: ["landed"], before: transitionSample(0, 0, 0, 0, "ready"),
    samples: [transitionSample(0, 0, 0, 0), transitionSample(0, 0, 0, 0)],
  });
  const preTriggerLeak = validateCase(contract, transitionCase, {
    events: ["landed"], before: transitionSample(0, 0, 0, 0, "ready"),
    samples: [transitionSample(0, 0, 0, 0, "ready"), transitionSample(20, 20, 20, 20)],
  });
  const wrongViewportSample = sample();
  wrongViewportSample.viewport = { width: 390, height: 700 };
  const wrongViewport = validateCase(contract, caseDef, { samples: [wrongViewportSample] });
  const baseline = { metrics: { charge: pass.metrics } };
  const mismatch = compareBaseline(contract, { charge: { primary_area_ratio: pass.metrics.primary_area_ratio * 0.5, required_group_area_ratio: pass.metrics.required_group_area_ratio } }, baseline);
  const ledgerProject = fs.mkdtempSync(path.join(require("os").tmpdir(), "visual-audit-ledger-"));
  const controllerPath = path.join(ledgerProject, "controller.json");
  const stateDir = path.join(ledgerProject, "state");
  fs.writeFileSync(controllerPath, JSON.stringify({ task_id: "self-test-task", audit_state_dir: stateDir }));
  const ledgerFirst = reserveAttempt(ledgerProject, "seed", null, "abc", controllerPath).attempt;
  const ledgerSecond = reserveAttempt(ledgerProject, "seed", null, "changed-contract", controllerPath).attempt;
  const ledgerThird = reserveAttempt(ledgerProject, "seed", null, "changed-contract", controllerPath).attempt;
  let fourthRejected = false;
  try { reserveAttempt(ledgerProject, "seed", null, "changed-contract", controllerPath); }
  catch (error) { fourthRejected = error.message.includes("third-attempt report is terminal"); }
  process.env.VISUAL_AUDIT_RUN_ID = "model-attempted-override";
  const controllerLocation = attemptLedgerLocation(ledgerProject, controllerPath);
  const controllerStable = controllerLocation.reference.includes("controller://");
  const exceptionDetail = pageExceptionMessage({ exceptionDetails: {
    text: "Uncaught", url: "http://example.test/index.html", lineNumber: 4, columnNumber: 2,
    exception: { description: "TypeError: broken ready assignment\n at boot" },
  } });
  if (!pass.problems.length && !fallbackDesign.problems.length && !transition.problems.length &&
      tiny.problems.some((p) => p.includes("visible height")) &&
      drift.problems.some((p) => p.includes("drifted")) &&
      fallback.problems.some((p) => p.includes("render_source")) &&
      fakeTransition.problems.some((p) => p.includes("retarget delta")) &&
      preTriggerLeak.problems.some((p) => p.includes("retarget delta")) &&
      wrongViewport.problems.some((p) => p.includes("must match contract")) &&
      mismatch.length && ledgerFirst === 1 && ledgerSecond === 2 && ledgerThird === 3 &&
      fourthRejected && controllerStable &&
      exceptionDetail.includes("TypeError: broken ready assignment") && exceptionDetail.includes(":5:3")) {
    console.log("VISUAL_RUNTIME_SELFTEST: PASS");
    return 0;
  }
  console.error("VISUAL_RUNTIME_SELFTEST: FAIL", {
    pass, tiny, drift, fallback, fallbackDesign, transition, fakeTransition, preTriggerLeak,
    wrongViewport, mismatch,
    ledgerFirst, ledgerSecond, ledgerThird, fourthRejected, controllerStable, exceptionDetail,
  });
  return 1;
}

async function main() {
  let args;
  try { args = parseArgs(process.argv); } catch (error) { console.error(error.message); usage(); return 2; }
  if (args.selfTest) return selfTest();
  if (fs.existsSync(PIPELINE_CONTROLLER_FILE)) {
    console.error(
      "VISUAL_RUNTIME_AUDIT: DEFERRED_TO_CONTROLLER controller-backed Pi workers cannot " +
      "reserve visual-audit attempts; run this gate from the external controller after the worker exits",
    );
    return 3;
  }
  if (!args.project || !args.phase || !args.out || !["design", "seed", "production"].includes(args.phase)) {
    usage(); return 2;
  }
  const project = path.resolve(args.project);
  const contractPath = path.join(project, "VISUAL_CONTRACT.json");
  const outputPath = path.resolve(args.out);
  const evidenceDir = path.dirname(outputPath);
  const baselinePath = path.resolve(args.baseline || path.join(project, "evidence", "visual-baseline.json"));
  if (outputPath !== project && !outputPath.startsWith(`${project}${path.sep}`)) {
    console.error("output must stay inside project"); return 2;
  }
  fs.mkdirSync(evidenceDir, { recursive: true });
  const initialContractSha = fs.existsSync(contractPath) ? sha256File(contractPath) : null;
  let priorReport = null;
  if (fs.existsSync(outputPath)) {
    try { priorReport = JSON.parse(fs.readFileSync(outputPath, "utf8")); } catch (_) {}
  }
  let reserved;
  try { reserved = reserveAttempt(project, args.phase, priorReport, initialContractSha); }
  catch (error) { console.error(`VISUAL_RUNTIME_AUDIT: FAIL ${error.message}`); return 1; }
  const attempt = reserved.attempt;
  const report = {
    version: 1, phase: args.phase, status: "FAIL", generated_at: new Date().toISOString(),
    attempt, repair_limit: 3,
    attempt_ledger: reserved.ledgerReference,
    contract_sha256: initialContractSha, index_sha256: null, artifact_sha256: null,
    baseline_sha256: null, metrics: {}, cases: [], problems: [],
  };
  let server = null;
  let chrome = null;
  let client = null;
  try {
    const staticAudit = spawnSync("python3", [path.join(__dirname, "audit_visual_contract.py"), "--project", project], { encoding: "utf8" });
    if (staticAudit.status !== 0) throw new Error(`visual contract audit failed: ${(staticAudit.stdout || staticAudit.stderr).trim()}`);
    const contract = JSON.parse(fs.readFileSync(contractPath, "utf8"));
    report.contract_sha256 = sha256File(contractPath);
    report.index_sha256 = sha256File(path.join(project, "index.html"));
    report.artifact_sha256 = artifactDigest(project, contract.artifacts);
    let baseline = null;
    if (args.phase === "production") {
      baseline = JSON.parse(fs.readFileSync(baselinePath, "utf8"));
      report.baseline_sha256 = sha256File(baselinePath);
      if (baseline.contract_sha256 !== report.contract_sha256) {
        throw new Error("baseline contract hash does not match current VISUAL_CONTRACT.json");
      }
      for (const rel of contract.approval_artifacts || []) {
        if (!baseline.approval_artifacts || baseline.approval_artifacts[rel] !== sha256File(path.join(project, rel))) {
          throw new Error(`approved visual artifact changed after Seed approval: ${rel}`);
        }
      }
    }
    const served = await staticServer(project); server = served.server;
    const viewport = contract.viewport;
    const launched = await launchChrome(viewport.width, viewport.height);
    chrome = launched.chrome; client = launched.client;
    const pageErrors = [];
    client.on("Runtime.exceptionThrown", (params) => pageErrors.push(pageExceptionMessage(params)));
    await client.send("Page.enable"); await client.send("Runtime.enable");
    await client.send("Emulation.setDeviceMetricsOverride", {
      width: viewport.width, height: viewport.height, deviceScaleFactor: 1, mobile: viewport.height > viewport.width,
    });
    await client.send("Page.navigate", { url: `http://127.0.0.1:${served.port}/index.html?visualAudit=1` });
    await waitReady(client, pageErrors);
    for (const caseDef of contract.cases) {
      const expression = caseDef.entry === "natural"
        ? "(async()=>await window.__game.visualAudit.snapshot())()"
        : `(async()=>await window.__game.visualAudit.runCase(${JSON.stringify(caseDef.name)}))()`;
      const result = await evaluate(client, expression);
      const checked = validateCase(contract, caseDef, result, args.phase);
      report.problems.push(...checked.problems);
      report.metrics[caseDef.name] = checked.metrics;
      const screenshot = path.join(evidenceDir, `visual-${args.phase}-${safeName(caseDef.name)}.png`);
      const shot = await client.send("Page.captureScreenshot", { format: "png" });
      fs.writeFileSync(screenshot, Buffer.from(shot.data, "base64"));
      report.cases.push({
        name: caseDef.name,
        screenshot: path.relative(project, screenshot),
        samples: result && Array.isArray(result.samples) ? result.samples.length : 0,
      });
    }
    if (args.phase === "production") {
      report.problems.push(...compareBaseline(contract, report.metrics, baseline));
    }
    if (!report.problems.length) {
      report.status = "PASS";
      if (args.phase === "seed") {
        const baseline = {
          version: 1,
          contract_sha256: report.contract_sha256,
          artifact_sha256: report.artifact_sha256,
          approval_artifacts: Object.fromEntries(
            (contract.approval_artifacts || []).map((rel) => [rel, sha256File(path.join(project, rel))]),
          ),
          generated_at: report.generated_at,
          metrics: report.metrics,
        };
        fs.mkdirSync(path.dirname(baselinePath), { recursive: true });
        fs.writeFileSync(baselinePath, `${JSON.stringify(baseline, null, 2)}\n`);
        report.baseline_sha256 = sha256File(baselinePath);
      }
    }
  } catch (error) {
    report.problems.push(error.message);
  } finally {
    if (client) client.close();
    if (chrome) { killTree(chrome, "SIGTERM"); await sleep(150); killTree(chrome, "SIGKILL"); }
    if (server) await new Promise((resolve) => server.close(resolve));
  }
  if (report.status !== "PASS" && attempt >= 3 &&
      !report.problems.some((problem) => problem.includes("repair limit"))) {
    report.problems.push("visual audit repair limit reached: stop automatic edits and report this case with screenshots/trace");
  }
  fs.writeFileSync(outputPath, `${JSON.stringify(report, null, 2)}\n`);
  if (report.status === "PASS") {
    console.log(`VISUAL_RUNTIME_AUDIT: PASS phase=${args.phase}`); return 0;
  }
  for (const problem of report.problems) console.error(`FAIL: ${problem}`);
  console.error(`VISUAL_RUNTIME_AUDIT: FAIL (${report.problems.length} problem(s))`);
  return 1;
}

main().then((code) => { process.exitCode = code; }).catch((error) => {
  console.error(`VISUAL_RUNTIME_AUDIT: FAIL ${error.message}`); process.exitCode = 1;
});
