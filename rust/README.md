# determa

The **umbrella launcher** for the [Determa](https://github.com/fruwehq/determa) family.

`determa` is a thin, git-style dispatcher: `determa <product> …` finds and runs the
`determa-<product>` command on your `PATH`.

```console
$ cargo install determa
$ determa state run machine.yaml   # → determa-state run machine.yaml
$ determa list                     # installed products
$ determa --version
```

It is language-agnostic: it dispatches to whichever `determa-state` is on `PATH`, be it
the Rust or the Python build. A single static binary with no dependencies.

## License

MIT
