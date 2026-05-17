#!/usr/bin/env node
'use strict';

const { spawnSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const packageRoot = path.resolve(__dirname, '..');
const args = process.argv.slice(2);

const runtimeEntries = [
  'src',
  'pixel_square_daily.py',
  'webhook_app.py',
  'requirements.txt',
  '.env.example',
  'Dockerfile',
  'docker-compose.yml',
];

const requiredEnvKeys = [
  'TELEGRAM_BOT_TOKEN',
  'TELEGRAM_CHAT_ID',
  'WEBHOOK_PUBLIC_URL',
  'TELEGRAM_WEBHOOK_SECRET',
  'OPENAI_BASE_URL',
  'OPENAI_API_KEY',
  'OPENAI_MODEL',
  'BINANCE_SQUARE_OPENAPI_KEY',
];

function printHelp() {
  console.log(`Pixel Square Daily npm CLI

Usage:
  pixel-square-daily setup [dir]
  pixel-square-daily doctor [dir]
  pixel-square-daily start [dir] --docker
  pixel-square-daily start [dir] --webhook [--host 127.0.0.1] [--port 8096]
  pixel-square-daily start [dir] --once

Examples:
  npx pixel-square-daily@latest setup ./pixel-square-daily
  npx pixel-square-daily@latest doctor ./pixel-square-daily
  npx pixel-square-daily@latest start ./pixel-square-daily --docker
`);
}

function fail(message, code = 1) {
  console.error(`Error: ${message}`);
  process.exit(code);
}

function run(command, commandArgs, options = {}) {
  const result = spawnSync(command, commandArgs, {
    stdio: 'inherit',
    shell: process.platform === 'win32',
    ...options,
  });
  if (result.error) fail(result.error.message);
  if (result.status !== 0) process.exit(result.status || 1);
}

function tryRun(command, commandArgs, options = {}) {
  return spawnSync(command, commandArgs, {
    stdio: 'ignore',
    shell: process.platform === 'win32',
    ...options,
  });
}

function parseDir(defaultDir = process.cwd()) {
  const positional = args.slice(1).find((arg) => !arg.startsWith('--'));
  return path.resolve(positional || defaultDir);
}

function optionValue(name, fallback) {
  const idx = args.indexOf(name);
  if (idx === -1 || idx + 1 >= args.length) return fallback;
  return args[idx + 1];
}

function hasFlag(name) {
  return args.includes(name);
}

function pythonCommand() {
  for (const command of ['python3', 'python']) {
    const result = tryRun(command, ['--version']);
    if (result.status === 0) return command;
  }
  fail('Python 3 is required. Install python3 first.');
}

function venvPython(targetDir) {
  if (process.platform === 'win32') {
    return path.join(targetDir, '.venv', 'Scripts', 'python.exe');
  }
  return path.join(targetDir, '.venv', 'bin', 'python');
}

function shouldSkipCopy(entry) {
  return entry === '__pycache__' || entry === '.pytest_cache' || entry.endsWith('.pyc');
}

function copyRecursive(source, target) {
  const name = path.basename(source);
  if (shouldSkipCopy(name)) return;
  const stat = fs.statSync(source);
  if (stat.isDirectory()) {
    fs.mkdirSync(target, { recursive: true });
    for (const entry of fs.readdirSync(source)) {
      copyRecursive(path.join(source, entry), path.join(target, entry));
    }
    return;
  }
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.copyFileSync(source, target);
}

function setup() {
  const targetDir = parseDir(path.join(process.cwd(), 'pixel-square-daily'));
  fs.mkdirSync(targetDir, { recursive: true });

  for (const entry of runtimeEntries) {
    copyRecursive(path.join(packageRoot, entry), path.join(targetDir, entry));
  }

  const envPath = path.join(targetDir, '.env');
  if (!fs.existsSync(envPath)) {
    fs.copyFileSync(path.join(targetDir, '.env.example'), envPath);
    console.log(`Created ${envPath}`);
  } else {
    console.log(`Kept existing ${envPath}`);
  }

  const py = pythonCommand();
  const venvPath = path.join(targetDir, '.venv');
  if (!fs.existsSync(venvPython(targetDir))) {
    run(py, ['-m', 'venv', venvPath], { cwd: targetDir });
  }
  run(venvPython(targetDir), ['-m', 'pip', 'install', '-r', path.join(targetDir, 'requirements.txt')], { cwd: targetDir });

  console.log(`\nSetup complete: ${targetDir}`);
  console.log('Next:');
  console.log(`  cd ${targetDir}`);
  console.log('  nano .env');
  console.log('  npx pixel-square-daily@latest doctor .');
  console.log('  npx pixel-square-daily@latest start . --docker');
}

function parseEnvFile(filePath) {
  if (!fs.existsSync(filePath)) return {};
  const env = {};
  for (const line of fs.readFileSync(filePath, 'utf8').split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#') || !trimmed.includes('=')) continue;
    const [key, ...rest] = trimmed.split('=');
    env[key.trim()] = rest.join('=').trim().replace(/^['"]|['"]$/g, '');
  }
  return env;
}

function doctor() {
  const targetDir = parseDir();
  const checks = [];
  const add = (ok, label) => checks.push({ ok, label });

  add(fs.existsSync(targetDir), `target dir: ${targetDir}`);
  add(fs.existsSync(path.join(targetDir, 'pixel_square_daily.py')), 'pixel_square_daily.py exists');
  add(fs.existsSync(path.join(targetDir, 'webhook_app.py')), 'webhook_app.py exists');
  add(fs.existsSync(path.join(targetDir, 'src')), 'src/ exists');
  add(fs.existsSync(venvPython(targetDir)), '.venv Python exists');
  add(fs.existsSync(path.join(targetDir, '.env')), '.env exists');
  add(tryRun('docker', ['--version']).status === 0, 'docker available');

  const env = parseEnvFile(path.join(targetDir, '.env'));
  for (const key of requiredEnvKeys) {
    add(Boolean(env[key] && !env[key].includes('your_') && !env[key].includes('123456:ABC')), `.env ${key}`);
  }

  let failed = 0;
  for (const check of checks) {
    console.log(`${check.ok ? 'OK ' : 'ERR'} ${check.label}`);
    if (!check.ok) failed += 1;
  }
  if (failed) fail(`${failed} check(s) failed`, 2);
}

function ensureReady(targetDir) {
  if (!fs.existsSync(venvPython(targetDir))) {
    fail(`Missing .venv. Run: pixel-square-daily setup ${targetDir}`);
  }
}

function start() {
  const targetDir = parseDir();
  if (hasFlag('--docker')) {
    run('docker', ['compose', 'up', '-d'], { cwd: targetDir });
    return;
  }

  ensureReady(targetDir);
  const env = { ...process.env, PYTHONPATH: targetDir };

  if (hasFlag('--once')) {
    run(venvPython(targetDir), ['pixel_square_daily.py'], {
      cwd: targetDir,
      env: { ...env, RUN_ONCE: 'true' },
    });
    return;
  }

  if (hasFlag('--webhook')) {
    const host = optionValue('--host', '127.0.0.1');
    const port = optionValue('--port', '8096');
    run(venvPython(targetDir), ['-m', 'uvicorn', 'webhook_app:app', '--host', host, '--port', port], {
      cwd: targetDir,
      env,
    });
    return;
  }

  fail('Choose one start mode: --docker, --webhook, or --once');
}

const command = args[0];
if (!command || command === '--help' || command === '-h') {
  printHelp();
} else if (command === 'setup') {
  setup();
} else if (command === 'doctor') {
  doctor();
} else if (command === 'start') {
  start();
} else {
  fail(`Unknown command: ${command}`);
}
