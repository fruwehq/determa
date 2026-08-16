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
the Rust or the Python build.

The crate also exposes the Family Connection/Context v1 resolver APIs. The
package MSRV is Rust 1.67 because the pinned UTS #46 backend used for the
resolver requires it. The behavior-relevant ICU data crates are exact
dependencies, and `Cargo.lock` is checked in for this binary crate so the
verified Unicode 15.1 endpoint boundary is reproducible in CI and locked
installs.

## License

MIT
