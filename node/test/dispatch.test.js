"use strict";

// Minimal dependency-free tests for the determa node launcher.
const assert = require("assert");
const { spawnSync } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const BIN = path.join(__dirname, "..", "bin", "determa.js");

function run(args, env) {
  return spawnSync(process.execPath, [BIN, ...args], {
    encoding: "utf8",
    env: { ...process.env, ...env },
  });
}

let r = run(["--help"]);
assert.strictEqual(r.status, 0);
assert.ok(r.stdout.includes("umbrella launcher for the Determa family"));

r = run(["--version"]);
assert.strictEqual(r.status, 0);
assert.ok(/^determa \d/.test(r.stdout.trim()));

r = run(["definitely-not-real"]);
assert.strictEqual(r.status, 127);
assert.ok(r.stderr.includes("not found on PATH"));

for (const command of ["auth", "config", "context"]) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "determa-reserved-"));
  const stub = path.join(dir, `determa-${command}`);
  fs.writeFileSync(stub, '#!/bin/sh\necho "must-not-run"\nexit 0\n');
  fs.chmodSync(stub, 0o755);
  r = run([command], { PATH: dir + path.delimiter + process.env.PATH });
  assert.strictEqual(r.status, 2);
  assert.strictEqual(r.stdout, "");
  assert.strictEqual(
    r.stderr,
    `determa: family command '${command}' is reserved but not implemented yet.\n`
  );
}

if (process.platform !== "win32") {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "determa-test-"));
  const stub = path.join(dir, "determa-echo");
  fs.writeFileSync(stub, '#!/bin/sh\necho "echo-product: $*"\nexit 0\n');
  fs.chmodSync(stub, 0o755);
  const withPath = { PATH: dir + path.delimiter + process.env.PATH };

  r = run(["echo", "hi", "there"], withPath);
  assert.strictEqual(r.status, 0, r.stderr);
  assert.ok(r.stdout.includes("echo-product: hi there"), r.stdout);

  const boom = path.join(dir, "determa-boom");
  fs.writeFileSync(boom, "#!/bin/sh\nexit 3\n");
  fs.chmodSync(boom, 0o755);
  r = run(["boom"], withPath);
  assert.strictEqual(r.status, 3);

  // Implementation selection (DETERMA_<PRODUCT>_IMPL): language-suffixed stubs.
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "determa-state-"));
  for (const [name, marker] of [
    ["determa-state", "canonical"],
    ["determa-state-python", "python"],
    ["determa-state-rust", "rust"],
  ]) {
    const p = path.join(stateDir, name);
    fs.writeFileSync(p, `#!/bin/sh\necho "ran:${marker}: $*"\nexit 0\n`);
    fs.chmodSync(p, 0o755);
  }
  const statePath = { PATH: stateDir + path.delimiter + process.env.PATH };

  r = run(["state", "--version"], { ...statePath, DETERMA_STATE_IMPL: "rust" });
  assert.strictEqual(r.status, 0, r.stderr);
  assert.ok(r.stdout.includes("ran:rust: --version"), r.stdout);

  r = run(["state", "info"], statePath);
  assert.strictEqual(r.status, 0, r.stderr);
  assert.ok(r.stdout.includes("ran:canonical: info"), r.stdout);

  // only the canonical binary present -> env var falls back to canonical
  const canonOnly = fs.mkdtempSync(path.join(os.tmpdir(), "determa-canon-"));
  const c = path.join(canonOnly, "determa-state");
  fs.writeFileSync(c, '#!/bin/sh\necho "ran:canonical: $*"\nexit 0\n');
  fs.chmodSync(c, 0o755);
  r = run(["state", "ping"], {
    PATH: canonOnly + path.delimiter + process.env.PATH,
    DETERMA_STATE_IMPL: "rust",
  });
  assert.strictEqual(r.status, 0, r.stderr);
  assert.ok(r.stdout.includes("ran:canonical: ping"), r.stdout);

  // list shows impl variants
  r = run(["list"], { PATH: stateDir });
  assert.strictEqual(r.status, 0, r.stderr);
  assert.ok(r.stdout.includes("state (python, rust)"), r.stdout);
  assert.ok(!r.stdout.includes("state-python"));
  assert.ok(!r.stdout.includes("state-rust"));

  r = run(["--help"], { PATH: stateDir });
  assert.ok(r.stdout.includes("state (python, rust)"), r.stdout);
  assert.ok(r.stdout.includes("DETERMA_<PRODUCT>_IMPL"));

  const reservedDir = fs.mkdtempSync(path.join(os.tmpdir(), "determa-discovery-"));
  for (const name of [
    "determa-alpha",
    "determa-auth",
    "determa-config",
    "determa-config-rust",
    "determa-context",
  ]) {
    const executable = path.join(reservedDir, name);
    fs.writeFileSync(executable, "#!/bin/sh\n");
    fs.chmodSync(executable, 0o755);
  }
  r = run(["list"], { PATH: reservedDir });
  assert.strictEqual(r.stdout, "alpha\n");
  r = run(["--help"], { PATH: reservedDir });
  assert.ok(r.stdout.includes("  alpha"));
  assert.ok(!r.stdout.includes("  auth"));
  assert.ok(!r.stdout.includes("  config"));
  assert.ok(!r.stdout.includes("  context"));
}

console.log("determa node launcher: all tests passed");
