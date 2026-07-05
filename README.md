# Determa

**Determa** is a family of tools for defining and running well-specified, verifiable
behavior. This repository holds the **umbrella launcher** — the `determa` command — and
the family landing page.

## The launcher

`determa` is a thin, git-style dispatcher: `determa <product> …` finds and runs the
`determa-<product>` command on your `PATH`.

```
determa state run machine.yaml   # → determa-state run machine.yaml
determa list                     # installed products
determa --version
```

It is **language-agnostic** — it dispatches to whichever `determa-state` you installed
(the Python or the Rust build). Install the launcher in whichever ecosystem you like;
each one provides the same `determa` command:

| ecosystem | install | source |
|---|---|---|
| Python | `pip install determa` — or `pip install "determa[all]"` for the launcher **plus** the family | [`python/`](python/) |
| Rust | `cargo install determa` | [`rust/`](rust/) |
| npm | `npm install -g determa` | [`node/`](node/) |

## The family

| product | what it is | repositories |
|---|---|---|
| **Determa State** | a language-agnostic statechart engine (Harel/UML lineage) | [spec](https://github.com/fruwehq/determa-state-spec) · [conformance](https://github.com/fruwehq/determa-state-conformance) · [python](https://github.com/fruwehq/determa-state-python) · [rust](https://github.com/fruwehq/determa-state-rust) |

Future products slot in under the same `determa <product>` dispatch — no launcher
change needed, they just have to be on `PATH` as `determa-<product>`.

## License

MIT — see [LICENSE](LICENSE).
