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


def _discover() -> list[str]:
    """Product subcommands available as ``determa-<name>`` executables on ``PATH``."""
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
            sub = stem[len(PREFIX):]
            if sub:
                found.add(sub)
    return sorted(found)


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
    ]
    products = _discover()
    if products:
        lines.append("installed products:")
        lines += [f"  {p}" for p in products]
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
        for product in _discover():
            print(product)
        return 0

    sub, rest = args[0], args[1:]
    exe = shutil.which(f"{PREFIX}{sub}")
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
