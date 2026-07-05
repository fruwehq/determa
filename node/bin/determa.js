#!/usr/bin/env node
"use strict";

// determa — umbrella launcher for the Determa family.
//
// A thin, git-style dispatcher: `determa <product> [args…]` runs the
// `determa-<product>` executable found on PATH (e.g. `determa state run m.yaml`
// → `determa-state run m.yaml`). Language-agnostic: dispatches to whichever
// `determa-state` is installed, be it the Node, Python, or Rust build.

const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const PREFIX = "determa-";
const VERSION = require("../package.json").version;

function discover() {
  const found = new Set();
  const dirs = (process.env.PATH || "").split(path.delimiter);
  const exts =
    process.platform === "win32"
      ? (process.env.PATHEXT || ".EXE;.CMD;.BAT").split(";")
      : [""];
  for (const dir of dirs) {
    if (!dir) continue;
    let entries;
    try {
      entries = fs.readdirSync(dir);
    } catch {
      continue;
    }
    for (let name of entries) {
      if (!name.startsWith(PREFIX)) continue;
      for (const ext of exts) {
        if (ext && name.toLowerCase().endsWith(ext.toLowerCase())) {
          name = name.slice(0, -ext.length);
          break;
        }
      }
      const sub = name.slice(PREFIX.length);
      if (sub) found.add(sub);
    }
  }
  return [...found].sort();
}

function help() {
  const products = discover();
  let out =
    `determa ${VERSION} — umbrella launcher for the Determa family\n\n` +
    "usage: determa <product> [args…]\n" +
    "       determa list        list installed products\n" +
    "       determa --version   show this launcher's version\n\n" +
    "'determa <product> …' runs the 'determa-<product>' command on PATH,\n" +
    "e.g. 'determa state run m.yaml' → 'determa-state run m.yaml'.\n\n";
  out += products.length
    ? "installed products:\n" + products.map((p) => "  " + p).join("\n")
    : "no products found on PATH. install one, e.g.:\n  npm install -g determa-state";
  console.log(out);
}

function main(argv) {
  const args = argv.slice(2);
  const cmd = args[0];
  if (!cmd || cmd === "-h" || cmd === "--help" || cmd === "help") {
    help();
    return 0;
  }
  if (cmd === "-V" || cmd === "--version" || cmd === "version") {
    console.log(`determa ${VERSION}`);
    return 0;
  }
  if (cmd === "list") {
    discover().forEach((p) => console.log(p));
    return 0;
  }
  const exe = PREFIX + cmd;
  const result = spawnSync(exe, args.slice(1), { stdio: "inherit" });
  if (result.error) {
    process.stderr.write(
      `determa: unknown product '${cmd}' — '${exe}' not found on PATH.\n` +
        `try 'determa list', or install it (e.g. 'npm install -g ${exe}').\n`
    );
    return 127;
  }
  return result.status === null ? 1 : result.status;
}

process.exit(main(process.argv));
