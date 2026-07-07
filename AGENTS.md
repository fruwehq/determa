# AGENTS.md — determa (umbrella launcher)

Guidance for AI/coding agents working in this repository. (Tool-agnostic; not specific to any one assistant.)

## What this repo is
The **umbrella launcher** for the Determa family: the `determa` command, a thin git-style
dispatcher — `determa <product> …` runs the `determa-<product>` executable on `PATH`
(e.g. `determa state run m.yaml` → `determa-state run m.yaml`). It is a **monorepo of three
independent packages** that ship the *same* behavior in each ecosystem:
- `python/` — PyPI **`determa`** (namespace-safe: ships `determa/_cli.py`, **no**
  `determa/__init__.py`, so it coexists with `determa-state`'s `determa.state`; extras
  `determa[state]`/`[all]`).
- `rust/` — crates.io **`determa`** (single static dispatcher binary).
- `node/` — npm **`determa`** (bin dispatcher).

Implementation selection: `determa state …` honors `DETERMA_<PRODUCT>_IMPL`
(e.g. `DETERMA_STATE_IMPL=python|rust`) to run `determa-<product>-<impl>`; otherwise the
canonical `determa-<product>`. `determa list` groups variants, e.g. `state (python, rust)`.

The launcher versions **independently** of the spec (currently **0.2.0**; the Determa State
spec/engines are at 0.0.6).

## Determa in one paragraph
**Determa** is a family for defining/running well-specified, verifiable behavior. Its first
product, **Determa State**, is a language-agnostic **statechart engine** (Harel/UML lineage,
PSiCC RTC) with a shared conformance suite and **CEL** guards. This repo is the launcher
that ties the family together and reserves the `determa` name on every registry.

## Repositories (org `fruwehq`, local folders `~/src/personal/`)
| Repo | Role |
|---|---|
| determa-state-spec | normative prose spec + schema. No CI. |
| determa-state-conformance | the conformance suite (arbiter). No CI. |
| determa-state-python | Python impl — `determa-state` / `determa.state`. |
| determa-state-rust | Rust impl — crate `determa-state`. |
| **determa** (this) | umbrella launcher — `python/`, `rust/`, `node/`. |

## Working rules
- **One issue → one PR**, branch → PR → **squash-merge**, linear history, resolve threads.
- **No AI/assistant attribution** anywhere (commits, PRs, comments, docs).
- Keep the three launchers **behaviorally identical** (same dispatch, env-var selection, `list` grouping, help text). Each has its own test suite.

## Gates (`ci.yml` runs all three)
```sh
# python
cd python && pip install -e '.[dev]' && ruff check . && pytest -q
# rust
cd rust && cargo build --release && cargo clippy --release --all-targets -- -D warnings && cargo test
# node
cd node && node test/dispatch.test.js
```
Note: unlike `determa-state-rust`, the rust launcher **does** enforce `clippy -D warnings` in CI — keep it clean.

## Releasing (a single `vX.Y.Z` tag releases all three)
`release.yml` on a `v*` tag:
- **PyPI** (`python/`) via **Trusted Publishing (OIDC)** — gated on the `pypi` GitHub Environment (manual approval).
- **crates.io** (`rust/`) via `CARGO_REGISTRY_TOKEN` (org secret). `workflow_dispatch` runs the crates job alone.
- **npm** (`node/`) via **OIDC Trusted Publishing** — a trusted publisher is configured on the npm `determa` package (no token; `NPM_TOKEN` has been removed).

Bump the version in `python/pyproject.toml`, `rust/Cargo.toml`, **and** `node/package.json` together before tagging.

## Gotchas (shared across Determa repos)
- **Workflow files** (`.github/workflows/*`) require a token with the GitHub `workflow` OAuth scope to push. If a push is rejected, use the GitHub web editor or a server-side merge; `git` over **SSH** is not subject to this.
- `main` is protected — never push directly; go via PR.

## Pointers
- Dispatch logic: `python/src/determa/_cli.py`, `rust/src/main.rs`, `node/bin/determa.js` (keep them in sync).
- Family landing + install matrix: `README.md`.
