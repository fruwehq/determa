"""Check that rust/Cargo.toml declares the resolved normal-dependency MSRV."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11 is not used in CI.
    import tomli as tomllib  # type: ignore[no-redef]


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def reaches_normal_dependencies(metadata: dict[str, object]) -> set[str]:
    resolve = metadata["resolve"]
    if not isinstance(resolve, dict):
        raise TypeError("cargo metadata resolve must be an object")
    root = resolve["root"]
    nodes = {
        node["id"]: node
        for node in resolve["nodes"]
        if isinstance(node, dict) and isinstance(node.get("id"), str)
    }
    seen: set[str] = set()
    stack = [root]
    while stack:
        package_id = stack.pop()
        if package_id in seen:
            continue
        seen.add(package_id)
        node = nodes[package_id]
        for dependency in node.get("deps", []):
            if any(kind.get("kind") is None for kind in dependency.get("dep_kinds", [])):
                stack.append(dependency["pkg"])
    return seen


def main() -> int:
    rust_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    manifest = rust_dir / "Cargo.toml"
    declared = tomllib.loads(manifest.read_text(encoding="utf-8"))["package"].get(
        "rust-version"
    )
    if not isinstance(declared, str):
        print("rust/Cargo.toml package.rust-version is required", file=sys.stderr)
        return 1

    metadata = json.loads(
        subprocess.check_output(
            ["cargo", "metadata", "--locked", "--format-version", "1"],
            cwd=rust_dir,
            text=True,
        )
    )
    packages = {package["id"]: package for package in metadata["packages"]}
    normal_package_ids = reaches_normal_dependencies(metadata)
    dependency_versions = [
        (
            version_key(rust_version),
            rust_version,
            package["name"],
            package["version"],
        )
        for package_id, package in packages.items()
        if package_id in normal_package_ids
        and package.get("source") is not None
        and isinstance((rust_version := package.get("rust_version")), str)
    ]

    if not dependency_versions:
        print(f"Rust MSRV declared {declared}; no dependency MSRV metadata found")
        return 0

    _key, required, name, package_version = max(dependency_versions)
    if version_key(declared) < version_key(required):
        print(
            "rust/Cargo.toml package.rust-version "
            f"{declared} is below resolved normal dependency {name} "
            f"{package_version} rust-version {required}",
            file=sys.stderr,
        )
        return 1

    print(
        "Rust MSRV declared "
        f"{declared}; maximum resolved normal dependency is {name} "
        f"{package_version} requiring {required}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
