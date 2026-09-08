"""Keep workflow action pins and required launcher CI contexts fail-closed."""

from __future__ import annotations

import re
from pathlib import Path

ACTION_PIN = re.compile(
    r"^\s*- uses: (?P<action>[^\s@]+)@(?P<revision>[0-9a-f]{40}) # (?P<version>\S.*)$"
)
REQUIRED_CI_JOBS = {
    "family-connection-v1-vectors",
    "python",
    "rust",
    "rust-msrv",
    "node",
}
REQUIRED_RELEASE_JOBS = {"preflight", "build", "pypi", "crates", "npm"}


def workflow_jobs(text: str) -> set[str]:
    _, separator, jobs = text.partition("\njobs:\n")
    if not separator:
        return set()
    return set(re.findall(r"^  ([a-z][a-z0-9-]*):\n", jobs, re.MULTILINE))


def verify_workflows(repository: Path) -> None:
    workflow_dir = repository / ".github" / "workflows"
    failures: list[str] = []
    for workflow in sorted(workflow_dir.glob("*.yml")):
        for line_number, line in enumerate(workflow.read_text().splitlines(), 1):
            if "uses:" in line and ACTION_PIN.fullmatch(line) is None:
                failures.append(f"{workflow}:{line_number}: mutable or uncommented action: {line.strip()}")

    ci = (workflow_dir / "ci.yml").read_text()
    if workflow_jobs(ci) != REQUIRED_CI_JOBS:
        failures.append(f"ci.yml job contexts changed: {sorted(workflow_jobs(ci))}")
    for required in ('python-version: "3.11"', 'toolchain: 1.81.0', 'node-version: "22"'):
        if required not in ci:
            failures.append(f"ci.yml is missing required setting: {required}")

    release = (workflow_dir / "release.yml").read_text()
    if workflow_jobs(release) != REQUIRED_RELEASE_JOBS:
        failures.append(f"release.yml job set changed: {sorted(workflow_jobs(release))}")
    required_release_fragments = (
        "  preflight:\n",
        "  build:\n    needs: preflight\n    if: github.event_name == 'push'\n",
        "  pypi:\n    needs: build\n    if: github.event_name == 'push'\n",
        "  crates:\n    needs: preflight\n",
        "  npm:\n    needs: preflight\n    if: github.event_name == 'push'\n",
        "python3 scripts/verify_release.py",
        'node-version: "22"',
    )
    for required in required_release_fragments:
        if required not in release:
            failures.append(f"release.yml is missing required publication guard: {required!r}")

    if failures:
        raise SystemExit("\n".join(failures))


if __name__ == "__main__":
    verify_workflows(Path(__file__).resolve().parents[1])
    print("workflow action pins and required contexts are valid")
