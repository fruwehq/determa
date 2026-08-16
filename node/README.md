# determa

The **umbrella launcher** for the [Determa](https://github.com/fruwehq/determa) family.

`determa` is a thin, git-style dispatcher: `determa <product> …` finds and runs the
`determa-<product>` command on your `PATH`.

```console
$ npm install -g determa
$ determa state run machine.yaml   # → determa-state run machine.yaml
$ determa list                     # installed products
$ determa --version
```

It is language-agnostic: it dispatches to whichever `determa-state` is on `PATH`, be it
the Node, Python, or Rust build.

The package also exposes the Family Connection/Context v1 resolver APIs. Node
18 or newer is required by the pinned UTS #46 dependency.

## License

MIT
