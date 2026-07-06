"""determa — umbrella launcher for the Determa family.

A thin, git-style dispatcher: ``determa <product> [args…]`` finds and executes the
``determa-<product>`` command on ``PATH`` (e.g. ``determa state run m.yaml`` →
``determa-state run m.yaml``). It is language-agnostic — it dispatches to whichever
``determa-state`` is installed, be it the Python or the Rust build.

This distribution intentionally ships **no** ``determa/__init__.py`` so ``determa``
stays a PEP 420 namespace root shared with ``determa.state`` and future ``determa.*``
packages. The launcher lives here as a plain module in that namespace.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

PREFIX = "determa-"


def _version() -> str:
    try:
        from importlib.metadata import version

        return version("determa")
    except Exception:
        return "0+unknown"


def _stems() -> set[str]:
    """Every ``determa-<stem>`` executable stem on ``PATH`` (extension-stripped)."""
    exts = [e for e in os.environ.get("PATHEXT", "").split(os.pathsep) if e] or [""]
    found: set[str] = set()
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        if not directory or not os.path.isdir(directory):
            continue
        try:
            entries = os.listdir(directory)
        except OSError:
            continue
        for name in entries:
            if not name.startswith(PREFIX):
                continue
            stem = name
            for ext in exts:
                if ext and stem.lower().endswith(ext.lower()):
                    stem = stem[: -len(ext)]
                    break
            sub = stem[len(PREFIX) :]
            if sub:
                found.add(sub)
    return found


def _split_variant(stem: str, stems: set[str]) -> tuple[str, str | None]:
    """Split a stem into ``(product, impl)``; ``impl`` is ``None`` for a canonical product.

    A stem ``<product>-<impl>`` is treated as an implementation variant of ``<product>``
    when the canonical ``<product>`` is itself present on ``PATH`` (i.e. in ``stems``).
    The longest such product prefix wins, so multi-word products (``foo-bar``) are
    recognized before their variants (``foo-bar-rust``).
    """
    parts = stem.split("-")
    for i in range(len(parts) - 1, 0, -1):
        prefix = "-".join(parts[:i])
        if prefix in stems:
            return prefix, "-".join(parts[i:])
    return stem, None


def _discover() -> dict[str, list[str]]:
    """Products → sorted implementation variants found on ``PATH``.

    Canonical products map to an empty list. Example: with ``determa-state``,
    ``determa-state-python`` and ``determa-state-rust`` installed, returns
    ``{"state": ["python", "rust"]}``.
    """
    stems = _stems()
    products: dict[str, set[str]] = {}
    for stem in stems:
        product, impl = _split_variant(stem, stems)
        products.setdefault(product, set())
        if impl:
            products[product].add(impl)
    return {product: sorted(impls) for product, impls in sorted(products.items())}


def _exe_for(product: str) -> str | None:
    """Resolve the executable for ``product``, honoring ``DETERMA_<PRODUCT>_IMPL``.

    If set (e.g. ``DETERMA_STATE_IMPL=rust``), the language-suffixed binary
    ``determa-<product>-<impl>`` is preferred; if it is absent, or the variable is
    unset, the canonical ``determa-<product>`` command is used.
    """
    env_var = f"DETERMA_{product.replace('-', '_').upper()}_IMPL"
    impl = os.environ.get(env_var)
    if impl:
        suffixed = shutil.which(f"{PREFIX}{product}-{impl}")
        if suffixed:
            return suffixed
    return shutil.which(f"{PREFIX}{product}")


def _format_product(product: str, impls: list[str]) -> str:
    return f"{product} ({', '.join(impls)})" if impls else product


def _help() -> str:
    lines = [
        f"determa {_version()} — umbrella launcher for the Determa family",
        "",
        "usage: determa <product> [args…]",
        "       determa list        list installed products",
        "       determa --version   show this launcher's version",
        "",
        "'determa <product> …' runs the 'determa-<product>' command on PATH,",
        "e.g. 'determa state run m.yaml' → 'determa-state run m.yaml'.",
        "",
        "set DETERMA_<PRODUCT>_IMPL (e.g. DETERMA_STATE_IMPL=python|rust) to pick a",
        "specific language build when both 'determa-state-python' and 'determa-state-rust'",
        "are installed; otherwise the canonical 'determa-state' is used.",
        "",
    ]
    products = _discover()
    if products:
        lines.append("installed products:")
        lines += [f"  {_format_product(p, impls)}" for p, impls in products.items()]
    else:
        lines += [
            "no products found on PATH. install one, e.g.:",
            "  pip install determa-state",
        ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help", "help"):
        print(_help())
        return 0
    if args[0] in ("-V", "--version", "version"):
        print(f"determa {_version()}")
        return 0
    if args[0] == "list":
        for product, impls in _discover().items():
            print(_format_product(product, impls))
        return 0

    sub, rest = args[0], args[1:]
    exe = _exe_for(sub)
    if exe is None:
        sys.stderr.write(
            f"determa: unknown product '{sub}' — '{PREFIX}{sub}' not found on PATH.\n"
            f"try 'determa list', or install it (e.g. 'pip install {PREFIX}{sub}').\n"
        )
        return 127
    try:
        return subprocess.call([exe, *rest])
    except OSError as exc:  # pragma: no cover - defensive
        sys.stderr.write(f"determa: failed to run {exe}: {exc}\n")
        return 126


if __name__ == "__main__":
    raise SystemExit(main())
