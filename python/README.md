# determa

The **umbrella launcher** for the [Determa](https://github.com/fruwehq/determa) family.

`determa` is a thin, git-style dispatcher: `determa <product> …` finds and runs the
`determa-<product>` command on your `PATH`.

```console
$ pip install "determa[state]"     # launcher + the statechart engine
$ determa state run machine.yaml   # → determa-state run machine.yaml
$ determa list                     # installed products
$ determa --version
```

- `pip install determa` — just the launcher.
- `pip install "determa[state]"` — launcher + [`determa-state`](https://pypi.org/project/determa-state/).
- `pip install "determa[all]"` — launcher + the whole family.

The launcher is language-agnostic: it dispatches to whichever `determa-state` is on
`PATH`, be it the Python or the Rust build. It ships no `determa/__init__.py`, so it
coexists cleanly with `determa.state` as a PEP 420 namespace.

## License

MIT
