#!/usr/bin/env node
"use strict";

const { spawn } = require("child_process");

function usage() {
  console.error("用法: node scripts/run_bot_guard.js [--timeout-ms 10000] -- <command> [args...]");
}

let timeoutMs = 10000;
let i = 2;
if (process.argv[i] === "--timeout-ms") {
  timeoutMs = Number(process.argv[i + 1]);
  i += 2;
}
if (process.argv[i] !== "--") {
  usage();
  process.exit(2);
}
i += 1;
const command = process.argv[i];
const args = process.argv.slice(i + 1);

if (!command || !Number.isFinite(timeoutMs) || timeoutMs < 100 || timeoutMs > 600000) {
  usage();
  process.exit(2);
}

const detached = process.platform !== "win32";
const child = spawn(command, args, { stdio: "inherit", detached });
let timedOut = false;
let killTimer = null;

function killChild(signal) {
  if (!child.pid) return;
  try {
    if (detached) process.kill(-child.pid, signal);
    else child.kill(signal);
  } catch (_) {
    // The child may already have exited between the check and the signal.
  }
}

const timer = setTimeout(() => {
  timedOut = true;
  console.error(`BOT_TIMEOUT: exceeded ${timeoutMs}ms; terminating process tree`);
  killChild("SIGTERM");
  killTimer = setTimeout(() => killChild("SIGKILL"), 500);
}, timeoutMs);

child.on("error", (error) => {
  clearTimeout(timer);
  if (killTimer) clearTimeout(killTimer);
  console.error(`BOT_START_ERROR: ${error.message}`);
  process.exitCode = 127;
});

child.on("exit", (code, signal) => {
  clearTimeout(timer);
  if (killTimer) clearTimeout(killTimer);
  if (timedOut) {
    process.exitCode = 124;
    return;
  }
  if (signal) {
    console.error(`BOT_SIGNAL: ${signal}`);
    process.exitCode = 1;
    return;
  }
  process.exitCode = code == null ? 1 : code;
});

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => {
    killChild(signal);
    process.exitCode = 130;
  });
}
