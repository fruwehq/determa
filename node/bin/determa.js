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

function stems() {
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
  return found;
}

// Split a stem into [product, impl] where impl is undefined for a canonical product.
// A stem `<product>-<impl>` is a variant of `<product>` when `<product>` is also on PATH;
// the longest such product prefix wins (so multi-word products like `foo-bar` win over
// their variants `foo-bar-rust`).
function splitVariant(stem, all) {
  const parts = stem.split("-");
  for (let i = parts.length - 1; i > 0; i--) {
    const prefix = parts.slice(0, i).join("-");
    if (all.has(prefix)) return [prefix, parts.slice(i).join("-")];
  }
  return [stem, undefined];
}

// Products -> sorted impl variants (canonical products map to []). Array of [product, impls].
function discover() {
  const all = stems();
  const products = new Map();
  for (const stem of all) {
    const [product, impl] = splitVariant(stem, all);
    if (!products.has(product)) products.set(product, new Set());
    if (impl) products.get(product).add(impl);
  }
  return [...products.entries()]
    .map(([p, impls]) => [p, [...impls].sort()])
    .sort((a, b) => a[0].localeCompare(b[0]));
}

// Resolve the executable for `product`, honoring DETERMA_<PRODUCT>_IMPL.
function exeFor(product) {
  const impl = process.env[`DETERMA_${product.replace(/-/g, "_").toUpperCase()}_IMPL`];
  if (impl) {
    const suffixed = `${PREFIX}${product}-${impl}`;
    if (which(suffixed)) return suffixed;
  }
  const canonical = `${PREFIX}${product}`;
  return which(canonical) ? canonical : null;
}

// Locate an executable on PATH (like shutil.which); returns the resolved path or null.
function which(name) {
  const dirs = (process.env.PATH || "").split(path.delimiter);
  const exts =
    process.platform === "win32"
      ? (process.env.PATHEXT || ".EXE;.CMD;.BAT").split(";")
      : [""];
  for (const dir of dirs) {
    if (!dir) continue;
    let p;
    try {
      p = fs.statSync(path.join(dir, name));
    } catch {
      continue;
    }
    if (p.isFile()) return path.join(dir, name);
    if (exts.length) {
      for (const ext of exts) {
        try {
          if (fs.statSync(path.join(dir, name + ext)).isFile())
            return path.join(dir, name + ext);
        } catch {
          continue;
        }
      }
    }
  }
  return null;
}

function formatProduct(product, impls) {
  return impls.length ? `${product} (${impls.join(", ")})` : product;
}

function help() {
  const products = discover();
  let out =
    `determa ${VERSION} — umbrella launcher for the Determa family\n\n` +
    "usage: determa <product> [args…]\n" +
    "       determa list        list installed products\n" +
    "       determa --version   show this launcher's version\n\n" +
    "'determa <product> …' runs the 'determa-<product>' command on PATH,\n" +
    "e.g. 'determa state run m.yaml' → 'determa-state run m.yaml'.\n\n" +
    "set DETERMA_<PRODUCT>_IMPL (e.g. DETERMA_STATE_IMPL=python|rust) to pick a\n" +
    "specific language build when both 'determa-state-python' and 'determa-state-rust'\n" +
    "are installed; otherwise the canonical 'determa-state' is used.\n\n";
  out += products.length
    ? "installed products:\n" + products.map(([p, i]) => "  " + formatProduct(p, i)).join("\n")
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
    discover().forEach(([p, i]) => console.log(formatProduct(p, i)));
    return 0;
  }
  const exe = exeFor(cmd);
  if (!exe) {
    process.stderr.write(
      `determa: unknown product '${cmd}' — '${PREFIX}${cmd}' not found on PATH.\n` +
        `try 'determa list', or install it (e.g. 'npm install -g ${PREFIX}${cmd}').\n`
    );
    return 127;
  }
  const result = spawnSync(exe, args.slice(1), { stdio: "inherit" });
  return result.status === null ? 1 : result.status;
}

process.exit(main(process.argv));
