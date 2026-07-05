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
}

console.log("determa node launcher: all tests passed");
