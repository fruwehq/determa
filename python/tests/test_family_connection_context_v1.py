"""Shared Family Connection/Context v1 fixture tests for the Python implementation."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from determa import family_connection_context_v1 as family

ROOT = Path(__file__).resolve().parents[2]
VECTOR_ROOT = ROOT / "conformance" / "family-connection-v1"


def load_fixture(name: str) -> dict[str, Any]:
    with (VECTOR_ROOT / name).open(encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


def assert_case(case: dict[str, Any], operation: Callable[[], Any]) -> None:
    expected = case["expect"]
    if "error" in expected:
        with pytest.raises(family.FamilyConnectionError) as exc_info:
            operation()
        assert exc_info.value.code == expected["error"]
    else:
        assert operation() == expected["value"]


def test_unicode_data_version() -> None:
    family.validate_unicode_data_version()


def test_reserved_family_commands_are_public() -> None:
    assert family.RESERVED_FAMILY_COMMANDS == frozenset({"auth", "config", "context"})


def test_unicode_15_1_label_participates_in_bidi_domain() -> None:
    assert (
        family.canonicalize_endpoint("https://\U0002EBF0.\u0646\u0627\u0645\u0647\u200c\u0627\u06cc.example/")
        == "https://xn--8g0n.xn--mgba3gch31f060k.example/"
    )


@pytest.mark.parametrize(
    "case", load_fixture("configuration.json")["cases"], ids=lambda case: case["id"]
)
def test_configuration_vectors(case: dict[str, Any]) -> None:
    assert_case(case, lambda: family.parse_configuration_source(case["source"]))


@pytest.mark.parametrize(
    "case", load_fixture("endpoints.json")["cases"], ids=lambda case: case["id"]
)
def test_endpoint_vectors(case: dict[str, Any]) -> None:
    assert_case(case, lambda: family.canonicalize_endpoint(case["input"]))


@pytest.mark.parametrize(
    "case", load_fixture("environment.json")["cases"], ids=lambda case: case["id"]
)
def test_environment_vectors(case: dict[str, Any]) -> None:
    assert_case(case, lambda: family.environment_name(case["resource"]))


def test_environment_distinct_sets() -> None:
    fixture = load_fixture("environment.json")
    results = {
        case["id"]: family.environment_name(case["resource"])
        for case in fixture["cases"]
        if "value" in case["expect"]
    }
    for distinct_set in fixture.get("distinct_sets", []):
        values = [results[case_id] for case_id in distinct_set]
        assert len(values) == len(set(values))


@pytest.fixture(scope="module")
def routing_configurations() -> dict[str, dict[str, Any]]:
    fixture = load_fixture("routing.json")
    return {
        name: family.parse_configuration_source(source)
        for name, source in fixture["configurations"].items()
    }


@pytest.mark.parametrize("case", load_fixture("routing.json")["cases"], ids=lambda case: case["id"])
def test_routing_vectors(
    case: dict[str, Any], routing_configurations: dict[str, dict[str, Any]]
) -> None:
    configuration = routing_configurations[case["configuration"]]
    assert_case(case, lambda: family.resolve_connection(configuration, case["request"]))
