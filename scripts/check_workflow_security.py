"""Keep workflow action pins and required launcher CI contexts fail-closed."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

APPROVED_ACTIONS = {
    "actions/checkout": ("3d3c42e5aac5ba805825da76410c181273ba90b1", "v7.0.1"),
    "actions/download-artifact": ("3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c", "v8.0.1"),
    "actions/setup-node": ("820762786026740c76f36085b0efc47a31fe5020", "v7.0.0"),
    "actions/setup-python": ("5fda3b95a4ea91299a34e894583c3862153e4b97", "v7.0.0"),
    "actions/upload-artifact": ("043fb46d1a93c77aae656e7c1c64a875d1fc6a0a", "v7.0.1"),
    "dtolnay/rust-toolchain": ("6bed0761d98439e5a578e2877258200ad565ba87", "stable 2026-09-03"),
    "pypa/gh-action-pypi-publish": ("dc37677b2e1c63e2034f94d8a5b11f265b73ba33", "v1.14.2"),
    "rust-lang/crates-io-auth-action": ("c6f97d42243bad5fab37ca0427f495c86d5b1a18", "v1.0.5"),
    "Swatinem/rust-cache": ("6323deb102c322ba6fcbdcafc7e3dddab59af2b6", "v2.9.2"),
}
CI_NAMES = {
    "family-connection-v1-vectors": "family connection v1 vectors",
    "python": "python launcher",
    "rust": "rust launcher",
    "rust-msrv": "rust launcher MSRV",
    "node": "node launcher",
}
RELEASE_JOBS = {"preflight", "build", "pypi", "crates", "npm"}
PUSH_ONLY = "github.event_name == 'push'"


class UniqueBaseLoader(yaml.BaseLoader):
    """Load workflow scalars as strings while rejecting duplicate keys."""


def _construct_unique_mapping(
    loader: UniqueBaseLoader, node: MappingNode, deep: bool = False
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueBaseLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


def _load_workflow(path: Path, failures: list[str]) -> tuple[dict[str, Any], Node | None, str]:
    text = path.read_text()
    try:
        parsed = yaml.load(text, Loader=UniqueBaseLoader)
        document = yaml.compose(text, Loader=UniqueBaseLoader)
    except yaml.YAMLError as error:
        failures.append(f"{path}: invalid YAML: {error}")
        return {}, None, text
    if not isinstance(parsed, dict):
        failures.append(f"{path}: workflow must be a mapping")
        return {}, document, text
    return parsed, document, text


def _action_nodes(node: Node | None) -> list[ScalarNode]:
    if node is None:
        return []
    found: list[ScalarNode] = []
    if isinstance(node, MappingNode):
        for key_node, value_node in node.value:
            if isinstance(key_node, ScalarNode) and key_node.value == "uses":
                if isinstance(value_node, ScalarNode):
                    found.append(value_node)
            found.extend(_action_nodes(value_node))
    elif isinstance(node, SequenceNode):
        for child in node.value:
            found.extend(_action_nodes(child))
    return found


def _verify_actions(path: Path, document: Node | None, text: str, failures: list[str]) -> None:
    lines = text.splitlines()
    for node in _action_nodes(document):
        reference = node.value
        repository, separator, revision = reference.partition("@")
        approved = APPROVED_ACTIONS.get(repository)
        if not separator or approved is None or revision != approved[0]:
            failures.append(f"{path}:{node.start_mark.line + 1}: unapproved action: {reference}")
            continue
        line = lines[node.start_mark.line]
        _, comment_separator, comment = line.partition("#")
        if not comment_separator or comment.strip() != approved[1]:
            failures.append(
                f"{path}:{node.start_mark.line + 1}: action metadata must be {approved[1]!r}"
            )


def _steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    value = job.get("steps", [])
    return value if isinstance(value, list) else []


def _uses_step(job: dict[str, Any], repository: str) -> dict[str, Any] | None:
    prefix = f"{repository}@"
    return next((step for step in _steps(job) if step.get("uses", "").startswith(prefix)), None)


def _run_commands(job: dict[str, Any]) -> list[str]:
    return [step["run"].strip() for step in _steps(job) if "run" in step]


def _expect_equal(failures: list[str], label: str, actual: Any, expected: Any) -> None:
    if actual != expected:
        failures.append(f"{label}: expected {expected!r}, got {actual!r}")


def _verify_ci(workflow: dict[str, Any], failures: list[str]) -> None:
    jobs = workflow.get("jobs", {})
    if not isinstance(jobs, dict):
        failures.append("ci.yml jobs must be a mapping")
        return
    _expect_equal(failures, "ci.yml job IDs", set(jobs), set(CI_NAMES))
    for job_id, expected_name in CI_NAMES.items():
        job = jobs.get(job_id, {})
        _expect_equal(failures, f"ci.yml {job_id} name", job.get("name"), expected_name)
        _expect_equal(failures, f"ci.yml {job_id} dependencies", job.get("needs"), None)
        _expect_equal(failures, f"ci.yml {job_id} condition", job.get("if"), None)

    python_setup = _uses_step(jobs.get("python", {}), "actions/setup-python") or {}
    _expect_equal(
        failures, "ci.yml python runtime", python_setup.get("with", {}).get("python-version"), "3.11"
    )
    node_setup = _uses_step(jobs.get("node", {}), "actions/setup-node") or {}
    _expect_equal(failures, "ci.yml node runtime", node_setup.get("with", {}).get("node-version"), "22")
    for job_id, toolchain in (("rust", "stable"), ("rust-msrv", "1.81.0")):
        setup = _uses_step(jobs.get(job_id, {}), "dtolnay/rust-toolchain") or {}
        _expect_equal(
            failures, f"ci.yml {job_id} toolchain", setup.get("with", {}).get("toolchain"), toolchain
        )

    expected_commands = {
        "family-connection-v1-vectors": [
            "python -m pip install --require-hashes -r scripts/requirements-family-connection-v1-vectors.txt",
            "python3 scripts/validate-family-connection-v1-vectors.py",
            "python3 -m unittest discover -s scripts -p 'test_*.py'\npython3 scripts/check_workflow_security.py",
        ],
        "python": ["pip install -e '.[dev]'", "ruff check .", "pytest -q"],
        "rust": [
            "python3 ../scripts/check-rust-msrv.py .",
            "cargo build --release --locked",
            "cargo clippy --release --all-targets --all-features --locked -- -D warnings",
            "cargo test --locked",
            "cargo run --locked --example family-connection-context-v1-vectors --features repository-fixtures",
            "cargo package --locked\nmkdir -p target/package-test\ntar -xzf target/package/determa-*.crate -C target/package-test\ncargo test --locked --all-features --manifest-path target/package-test/determa-*/Cargo.toml",
        ],
        "rust-msrv": [
            "python3 ../scripts/check-rust-msrv.py .",
            "cargo build --release --locked",
            "cargo test --locked",
            "cargo run --locked --example family-connection-context-v1-vectors --features repository-fixtures",
        ],
        "node": ["npm ci", "npm test"],
    }
    for job_id, commands in expected_commands.items():
        _expect_equal(failures, f"ci.yml {job_id} commands", _run_commands(jobs.get(job_id, {})), commands)


def _verify_release(workflow: dict[str, Any], failures: list[str]) -> None:
    jobs = workflow.get("jobs", {})
    if not isinstance(jobs, dict):
        failures.append("release.yml jobs must be a mapping")
        return
    _expect_equal(failures, "release.yml job IDs", set(jobs), RELEASE_JOBS)
    topology = {
        "preflight": (None, None),
        "build": ("preflight", PUSH_ONLY),
        "pypi": ("build", PUSH_ONLY),
        "crates": ("preflight", None),
        "npm": ("preflight", PUSH_ONLY),
    }
    for job_id, (needs, condition) in topology.items():
        job = jobs.get(job_id, {})
        _expect_equal(failures, f"release.yml {job_id} dependencies", job.get("needs"), needs)
        _expect_equal(failures, f"release.yml {job_id} condition", job.get("if"), condition)

    _expect_equal(
        failures,
        "release.yml preflight commands",
        _run_commands(jobs.get("preflight", {})),
        ['python3 scripts/verify_release.py --event-name "$GITHUB_EVENT_NAME" --tag "$RELEASE_TAG"'],
    )
    preflight_steps = _steps(jobs.get("preflight", {}))
    verify_step = next(
        (
            step
            for step in preflight_steps
            if step.get("name") == "Verify synchronized package versions and release tag"
        ),
        {},
    )
    _expect_equal(
        failures,
        "release.yml preflight tag source",
        verify_step.get("env", {}).get("RELEASE_TAG"),
        "${{ github.event_name == 'push' && github.ref_name || '' }}",
    )
    npm_setup = _uses_step(jobs.get("npm", {}), "actions/setup-node") or {}
    _expect_equal(failures, "release.yml node runtime", npm_setup.get("with", {}).get("node-version"), "22")


def verify_workflows(repository: Path) -> None:
    workflow_dir = repository / ".github" / "workflows"
    failures: list[str] = []
    parsed: dict[str, dict[str, Any]] = {}
    for name in ("ci.yml", "release.yml"):
        workflow, document, text = _load_workflow(workflow_dir / name, failures)
        parsed[name] = workflow
        _verify_actions(workflow_dir / name, document, text, failures)
    _verify_ci(parsed["ci.yml"], failures)
    _verify_release(parsed["release.yml"], failures)
    if failures:
        raise SystemExit("\n".join(failures))


if __name__ == "__main__":
    verify_workflows(Path(__file__).resolve().parents[1])
    print("workflow topology, action pins, and required contexts are valid")
