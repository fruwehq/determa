"""Fail-closed release metadata and tag verification for all launchers."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import tomllib

STABLE_VERSION = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", re.ASCII)


class ReleaseVerificationError(ValueError):
    """Release metadata or invocation is unsafe to publish."""


def read_versions(repository: Path) -> dict[str, str]:
    with (repository / "python" / "pyproject.toml").open("rb") as file:
        python_version = tomllib.load(file)["project"]["version"]
    with (repository / "rust" / "Cargo.toml").open("rb") as file:
        rust_version = tomllib.load(file)["package"]["version"]
    with (repository / "node" / "package.json").open(encoding="utf-8") as file:
        node_version = json.load(file)["version"]
    with (repository / "node" / "package-lock.json").open(encoding="utf-8") as file:
        node_lock = json.load(file)

    versions = {
        "Python": python_version,
        "Rust": rust_version,
        "Node": node_version,
        "Node lock": node_lock["version"],
        "Node lock root package": node_lock["packages"][""]["version"],
    }
    if not all(isinstance(version, str) for version in versions.values()):
        raise ReleaseVerificationError("every package version must be a string")
    return versions


def verify_release(repository: Path, event_name: str, tag: str | None) -> str:
    versions = read_versions(repository)
    distinct_versions = set(versions.values())
    if len(distinct_versions) != 1:
        details = ", ".join(f"{name}={version!r}" for name, version in versions.items())
        raise ReleaseVerificationError(f"package versions differ: {details}")

    version = distinct_versions.pop()
    if STABLE_VERSION.fullmatch(version) is None:
        raise ReleaseVerificationError(f"package version is not canonical stable SemVer: {version!r}")

    expected_tag = f"v{version}"
    if event_name == "push":
        if tag != expected_tag:
            raise ReleaseVerificationError(
                f"release tag {tag!r} does not exactly match package versions ({expected_tag!r})"
            )
    elif event_name == "workflow_dispatch":
        if tag:
            raise ReleaseVerificationError("manual release verification does not accept a tag")
    else:
        raise ReleaseVerificationError(f"unsupported release event: {event_name!r}")

    return expected_tag


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--event-name", required=True)
    parser.add_argument("--tag")
    args = parser.parse_args()

    try:
        expected_tag = verify_release(args.repository, args.event_name, args.tag)
    except (KeyError, OSError, json.JSONDecodeError, tomllib.TOMLDecodeError, ReleaseVerificationError) as error:
        parser.error(str(error))

    print(f"release metadata is coherent for {expected_tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
