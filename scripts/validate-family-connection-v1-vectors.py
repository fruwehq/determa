#!/usr/bin/env python3
"""Validate the language-neutral Family Connection/Context v1 vectors."""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import idna
from idna import idnadata, uts46data

ROOT = Path(__file__).resolve().parents[1]
VECTOR_ROOT = ROOT / "conformance" / "family-connection-v1"
NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")
IPV4_RE = re.compile(r"^(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*)){3}$")
IPV4_LIKE_RE = re.compile(
    r"^(?:0x[0-9a-f]+|[0-9]+)(?:\.(?:0x[0-9a-f]+|[0-9]+))*$",
    re.IGNORECASE,
)
ENDPOINT_RE = re.compile(
    r"^([A-Za-z][A-Za-z0-9+.-]*):\/\/([^\/?#]*)([^?#]*)$"
)
PCHAR = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~!$&'()*+,;=:@"
)
UNRESERVED = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
)
HEX = frozenset("0123456789abcdefABCDEF")
EXPECTED_UNICODE_VERSION = "15.1.0"
ERROR_CODES = frozenset(
    {
        "duplicate_key",
        "insecure_endpoint",
        "invalid_connection",
        "invalid_context",
        "invalid_endpoint_authority",
        "invalid_endpoint_characters",
        "invalid_endpoint_host",
        "invalid_endpoint_path",
        "invalid_endpoint_port",
        "invalid_endpoint_syntax",
        "invalid_endpoint_type",
        "invalid_environment",
        "invalid_name",
        "invalid_reference",
        "invalid_source",
        "invalid_type",
        "invalid_version",
        "missing_field",
        "unknown_field",
        "unresolved_connection",
        "unsupported_endpoint_scheme",
    }
)


class VectorError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class IntegerToken:
    source: str


@dataclass(frozen=True)
class NonIntegerNumberToken:
    source: str


def reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise VectorError("duplicate_key")
        result[key] = value
    return result


def reject_nonfinite_constant(_value: str) -> Any:
    raise VectorError("invalid_source")


def parse_configuration_source(source: Any) -> dict[str, Any]:
    if not isinstance(source, str):
        raise VectorError("invalid_source")
    try:
        value = json.loads(
            source,
            object_pairs_hook=reject_duplicate_pairs,
            parse_int=IntegerToken,
            parse_float=NonIntegerNumberToken,
            parse_constant=reject_nonfinite_constant,
        )
    except VectorError:
        raise
    except (json.JSONDecodeError, UnicodeError):
        raise VectorError("invalid_source") from None
    return validate_configuration(value)


def require_closed_object(
    value: Any, required: set[str], optional: set[str]
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise VectorError("invalid_type")
    if not required.issubset(value):
        raise VectorError("missing_field")
    if set(value) - required - optional:
        raise VectorError("unknown_field")
    return value


def require_name(value: Any) -> str:
    if not isinstance(value, str):
        raise VectorError("invalid_type")
    if not NAME_RE.fullmatch(value):
        raise VectorError("invalid_name")
    return value


def require_nonempty_string(value: Any) -> str:
    if not isinstance(value, str):
        raise VectorError("invalid_type")
    if not value:
        raise VectorError("invalid_name")
    return value


def validate_routes(value: Any, connection_names: set[str]) -> dict[str, str]:
    if not isinstance(value, dict):
        raise VectorError("invalid_type")
    result: dict[str, str] = {}
    for resource, connection in value.items():
        validate_resource(resource)
        if not isinstance(connection, str):
            raise VectorError("invalid_type")
        if connection not in connection_names:
            raise VectorError("invalid_reference")
        result[resource] = connection
    return result


def validate_configuration(value: Any) -> dict[str, Any]:
    root = require_closed_object(
        value,
        {"version", "connections", "contexts"},
        {"default_context", "defaults"},
    )
    version = root["version"]
    if not isinstance(version, IntegerToken) or version.source != "1":
        raise VectorError("invalid_version")

    raw_connections = root["connections"]
    if not isinstance(raw_connections, dict):
        raise VectorError("invalid_type")
    connections: dict[str, Any] = {}
    for raw_name, raw_connection in raw_connections.items():
        name = require_name(raw_name)
        connection = require_closed_object(
            raw_connection, {"endpoint"}, {"credential_ref"}
        )
        endpoint = canonicalize_endpoint(connection["endpoint"])
        normalized: dict[str, Any] = {"endpoint": endpoint}
        if "credential_ref" in connection:
            credential = require_closed_object(
                connection["credential_ref"], {"provider", "name"}, set()
            )
            normalized["credential_ref"] = {
                "provider": require_name(credential["provider"]),
                "name": require_nonempty_string(credential["name"]),
            }
        connections[name] = normalized

    connection_names = set(connections)
    raw_contexts = root["contexts"]
    if not isinstance(raw_contexts, dict):
        raise VectorError("invalid_type")
    contexts: dict[str, Any] = {}
    for raw_name, raw_context in raw_contexts.items():
        name = require_name(raw_name)
        context = require_closed_object(raw_context, {"routes"}, set())
        contexts[name] = {
            "routes": validate_routes(context["routes"], connection_names)
        }

    normalized_root: dict[str, Any] = {
        "version": 1,
        "connections": connections,
        "contexts": contexts,
    }
    if "default_context" in root:
        default_context = require_name(root["default_context"])
        if default_context not in contexts:
            raise VectorError("invalid_reference")
        normalized_root["default_context"] = default_context
    if "defaults" in root:
        defaults = require_closed_object(root["defaults"], {"routes"}, set())
        normalized_root["defaults"] = {
            "routes": validate_routes(defaults["routes"], connection_names)
        }
    return normalized_root


def validate_resource(value: Any) -> list[str]:
    if not isinstance(value, str):
        raise VectorError("invalid_type")
    segments = value.split("/")
    if not segments or any(not NAME_RE.fullmatch(segment) for segment in segments):
        raise VectorError("invalid_name")
    return segments


def domain_to_ascii(host: str) -> str:
    try:
        return idna.encode(
            host,
            uts46=True,
            transitional=False,
            std3_rules=True,
        ).decode("ascii")
    except idna.IDNAError:
        return ""


def validate_unicode_data_version() -> None:
    versions = {idnadata.__version__, uts46data.__version__}
    if versions != {EXPECTED_UNICODE_VERSION}:
        raise RuntimeError(
            "IDNA tables must both use Unicode "
            f"{EXPECTED_UNICODE_VERSION}, got {sorted(versions)}"
        )
    runtime_version = tuple(
        int(part) for part in unicodedata.unidata_version.split(".")
    )
    if runtime_version < (15, 1, 0):
        raise RuntimeError(
            "runtime Unicode data must be at least 15.1.0, got "
            f"{unicodedata.unidata_version}"
        )


def canonicalize_ipv6(address: ipaddress.IPv6Address) -> str:
    number = int(address)
    groups = [f"{(number >> shift) & 0xFFFF:x}" for shift in range(112, -1, -16)]
    best_start = -1
    best_length = 0
    index = 0
    while index < len(groups):
        if groups[index] != "0":
            index += 1
            continue
        end = index
        while end < len(groups) and groups[end] == "0":
            end += 1
        length = end - index
        if length >= 2 and length > best_length:
            best_start = index
            best_length = length
        index = end
    if best_start < 0:
        return ":".join(groups)
    left = ":".join(groups[:best_start])
    right = ":".join(groups[best_start + best_length :])
    if left and right:
        return f"{left}::{right}"
    if left:
        return f"{left}::"
    if right:
        return f"::{right}"
    return "::"


def canonicalize_host(raw_host: str, bracketed: bool) -> tuple[str, str, Any]:
    if not raw_host or "%" in raw_host:
        raise VectorError("invalid_endpoint_host")
    if bracketed:
        try:
            address = ipaddress.IPv6Address(raw_host)
        except ipaddress.AddressValueError:
            raise VectorError("invalid_endpoint_host") from None
        canonical = canonicalize_ipv6(address)
        return f"[{canonical}]", "ipv6", address

    if IPV4_RE.fullmatch(raw_host):
        octets = raw_host.split(".")
        if any(int(octet) > 255 for octet in octets):
            raise VectorError("invalid_endpoint_host")
        canonical = ".".join(str(int(octet)) for octet in octets)
        return canonical, "ipv4", ipaddress.IPv4Address(canonical)
    if IPV4_LIKE_RE.fullmatch(raw_host):
        raise VectorError("invalid_endpoint_host")

    ascii_host = domain_to_ascii(raw_host)
    if not ascii_host or ascii_host.endswith("."):
        raise VectorError("invalid_endpoint_host")
    labels = ascii_host.lower().split(".")
    if any(
        not label
        or len(label) > 63
        or not re.fullmatch(r"[a-z0-9-]+", label)
        or label.startswith("-")
        or label.endswith("-")
        for label in labels
    ):
        raise VectorError("invalid_endpoint_host")
    canonical = ".".join(labels)
    if len(canonical) > 253:
        raise VectorError("invalid_endpoint_host")
    return canonical, "registered", canonical


def normalize_path(raw_path: str) -> str:
    output: list[str] = []
    index = 0
    while index < len(raw_path):
        character = raw_path[index]
        codepoint = ord(character)
        if codepoint > 0x7F:
            raise VectorError("invalid_endpoint_path")
        if character == "%":
            if (
                index + 2 >= len(raw_path)
                or raw_path[index + 1] not in HEX
                or raw_path[index + 2] not in HEX
            ):
                raise VectorError("invalid_endpoint_path")
            octet = int(raw_path[index + 1 : index + 3], 16)
            if octet >= 0x80 or octet <= 0x1F or octet in {0x7F, 0x2F, 0x5C}:
                raise VectorError("invalid_endpoint_path")
            decoded = chr(octet)
            output.append(decoded if decoded in UNRESERVED else f"%{octet:02X}")
            index += 3
            continue
        if character != "/" and character not in PCHAR:
            raise VectorError("invalid_endpoint_path")
        output.append(character)
        index += 1
    return remove_dot_segments("".join(output))


def remove_last_segment(path: str) -> str:
    slash = path.rfind("/")
    return "" if slash < 0 else path[:slash]


def remove_dot_segments(path: str) -> str:
    source = path
    output = ""
    while source:
        if source.startswith("../"):
            source = source[3:]
        elif source.startswith("./"):
            source = source[2:]
        elif source.startswith("/./"):
            source = "/" + source[3:]
        elif source == "/.":
            source = "/"
        elif source.startswith("/../"):
            source = "/" + source[4:]
            output = remove_last_segment(output)
        elif source == "/..":
            source = "/"
            output = remove_last_segment(output)
        elif source in {".", ".."}:
            source = ""
        else:
            start = 1 if source.startswith("/") else 0
            slash = source.find("/", start)
            if slash < 0:
                output += source
                source = ""
            else:
                output += source[:slash]
                source = source[slash:]
    return output


def canonicalize_endpoint(value: Any) -> str:
    if not isinstance(value, str):
        raise VectorError("invalid_endpoint_type")
    if not value:
        raise VectorError("invalid_endpoint_syntax")
    if any(
        character == "\\"
        or character == " "
        or ord(character) <= 0x1F
        or ord(character) == 0x7F
        or 0xD800 <= ord(character) <= 0xDFFF
        for character in value
    ):
        raise VectorError("invalid_endpoint_characters")
    match = ENDPOINT_RE.fullmatch(value)
    if not match:
        raise VectorError("invalid_endpoint_syntax")
    scheme, authority, raw_path = match.groups()
    scheme = scheme.lower()
    if scheme not in {"http", "https"}:
        raise VectorError("unsupported_endpoint_scheme")
    if not authority or "@" in authority:
        raise VectorError("invalid_endpoint_authority")

    bracketed = authority.startswith("[")
    raw_port: Any = None
    if bracketed:
        close = authority.find("]")
        if close < 0:
            raise VectorError("invalid_endpoint_authority")
        raw_host = authority[1:close]
        remainder = authority[close + 1 :]
        if remainder:
            if not remainder.startswith(":"):
                raise VectorError("invalid_endpoint_authority")
            raw_port = remainder[1:]
    else:
        if "[" in authority or "]" in authority or authority.count(":") > 1:
            raise VectorError("invalid_endpoint_authority")
        if ":" in authority:
            raw_host, raw_port = authority.rsplit(":", 1)
        else:
            raw_host = authority

    canonical_host, host_kind, host_value = canonicalize_host(raw_host, bracketed)
    canonical_port = ""
    if raw_port is not None:
        if not re.fullmatch(r"[1-9][0-9]*", raw_port):
            raise VectorError("invalid_endpoint_port")
        port = int(raw_port)
        if port > 65535:
            raise VectorError("invalid_endpoint_port")
        if not ((scheme == "https" and port == 443) or (scheme == "http" and port == 80)):
            canonical_port = f":{port}"

    path = normalize_path(raw_path)
    if not path:
        path = "/"
    elif path != "/":
        path = path.rstrip("/") or "/"

    if scheme == "http":
        loopback = (
            (host_kind == "registered" and host_value == "localhost")
            or (host_kind == "ipv4" and host_value.is_loopback)
            or (host_kind == "ipv6" and host_value == ipaddress.IPv6Address("::1"))
        )
        if not loopback:
            raise VectorError("insecure_endpoint")
    return f"{scheme}://{canonical_host}{canonical_port}{path}"


def environment_name(resource: Any) -> str:
    segments = validate_resource(resource)

    def encode(segment: str) -> str:
        return "".join("_H" if character == "-" else character.upper() for character in segment)

    return f"DETERMA_{'__'.join(encode(segment) for segment in segments)}_CONNECTION"


def route_keys(resource: str) -> list[str]:
    product = resource.split("/", 1)[0]
    return [resource] if product == resource else [resource, product]


def first_route(routes: dict[str, str], resource: str) -> Any:
    for key in route_keys(resource):
        if key in routes:
            return routes[key]
    return None


def resolve_connection(
    configuration: dict[str, Any], request: dict[str, Any]
) -> str:
    resource = request.get("resource")
    validate_resource(resource)
    connections = configuration["connections"]

    if "explicit_connection" in request:
        explicit = request["explicit_connection"]
        if not isinstance(explicit, str) or explicit not in connections:
            raise VectorError("invalid_connection")
        return explicit

    environment = request.get("environment", {})
    if not isinstance(environment, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in environment.items()
    ):
        raise VectorError("invalid_environment")
    environment_keys = [environment_name(resource)]
    product = resource.split("/", 1)[0]
    product_key = environment_name(product)
    if product_key not in environment_keys:
        environment_keys.append(product_key)
    environment_keys.append("DETERMA_CONNECTION")
    for key in environment_keys:
        if key in environment:
            connection = environment[key]
            if not connection or connection not in connections:
                raise VectorError("invalid_connection")
            return connection

    if "selected_context" in request:
        selected = request["selected_context"]
        if not isinstance(selected, str) or selected not in configuration["contexts"]:
            raise VectorError("invalid_context")
        connection = first_route(configuration["contexts"][selected]["routes"], resource)
        if connection is not None:
            return connection

    defaults = configuration.get("defaults", {"routes": {}})
    connection = first_route(defaults["routes"], resource)
    if connection is not None:
        return connection

    default_context = configuration.get("default_context")
    if default_context is not None:
        connection = first_route(
            configuration["contexts"][default_context]["routes"], resource
        )
        if connection is not None:
            return connection
    raise VectorError("unresolved_connection")


def load_fixture(name: str) -> dict[str, Any]:
    path = VECTOR_ROOT / name
    with path.open(encoding="utf-8") as fixture_file:
        return json.load(fixture_file, object_pairs_hook=reject_duplicate_pairs)


def assert_expected(case: dict[str, Any], actual: Any = None, error: Any = None) -> None:
    expected = case["expect"]
    if not isinstance(case.get("id"), str) or not case["id"]:
        raise AssertionError("every vector must have a non-empty string id")
    if set(expected) not in ({"value"}, {"error"}):
        raise AssertionError(f"{case['id']}: expect must contain exactly value or error")
    if "error" in expected and expected["error"] not in ERROR_CODES:
        raise AssertionError(f"{case['id']}: unknown error code {expected['error']!r}")
    if "error" in expected:
        if error != expected["error"]:
            raise AssertionError(
                f"{case['id']}: expected error {expected['error']!r}, got {error!r}"
            )
    elif error is not None:
        raise AssertionError(f"{case['id']}: unexpected error {error!r}")
    elif actual != expected["value"]:
        raise AssertionError(
            f"{case['id']}: expected {expected['value']!r}, got {actual!r}"
        )


def run_case(case: dict[str, Any], operation: Any) -> None:
    try:
        actual = operation()
    except VectorError as error:
        assert_expected(case, error=error.code)
    else:
        assert_expected(case, actual=actual)


def validate_fixture_header(fixture: dict[str, Any], suite: str) -> None:
    if fixture.get("contract") != "family-connection-context-v1":
        raise AssertionError(f"{suite}: incorrect contract identifier")
    if fixture.get("suite") != suite:
        raise AssertionError(f"{suite}: incorrect suite identifier")
    if not isinstance(fixture.get("cases"), list):
        raise TypeError(f"{suite}: cases must be an array")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", action="store_true")
    arguments = parser.parse_args()
    validate_unicode_data_version()
    seen_ids: set[str] = set()
    passed = 0

    configuration_fixture = load_fixture("configuration.json")
    validate_fixture_header(configuration_fixture, "configuration")
    for case in configuration_fixture["cases"]:
        run_case(case, lambda case=case: parse_configuration_source(case["source"]))
        if case["id"] in seen_ids:
            raise AssertionError(f"duplicate case id: {case['id']}")
        seen_ids.add(case["id"])
        passed += 1

    endpoint_fixture = load_fixture("endpoints.json")
    validate_fixture_header(endpoint_fixture, "endpoints")
    for case in endpoint_fixture["cases"]:
        run_case(case, lambda case=case: canonicalize_endpoint(case["input"]))
        if case["id"] in seen_ids:
            raise AssertionError(f"duplicate case id: {case['id']}")
        seen_ids.add(case["id"])
        passed += 1

    environment_fixture = load_fixture("environment.json")
    validate_fixture_header(environment_fixture, "environment")
    environment_results: dict[str, str] = {}
    for case in environment_fixture["cases"]:
        run_case(case, lambda case=case: environment_name(case["resource"]))
        if "value" in case["expect"]:
            environment_results[case["id"]] = case["expect"]["value"]
        if case["id"] in seen_ids:
            raise AssertionError(f"duplicate case id: {case['id']}")
        seen_ids.add(case["id"])
        passed += 1
    for distinct_set in environment_fixture.get("distinct_sets", []):
        values = [environment_results[case_id] for case_id in distinct_set]
        if len(values) != len(set(values)):
            raise AssertionError(f"environment names collide: {distinct_set}")

    routing_fixture = load_fixture("routing.json")
    validate_fixture_header(routing_fixture, "routing")
    configurations = {
        name: parse_configuration_source(source)
        for name, source in routing_fixture["configurations"].items()
    }
    for case in routing_fixture["cases"]:
        configuration = configurations[case["configuration"]]
        run_case(
            case,
            lambda case=case, configuration=configuration: resolve_connection(
                configuration, case["request"]
            ),
        )
        if case["id"] in seen_ids:
            raise AssertionError(f"duplicate case id: {case['id']}")
        seen_ids.add(case["id"])
        passed += 1

    if arguments.verbose:
        for case_id in sorted(seen_ids):
            print(f"PASS {case_id}")
    print(f"Family Connection/Context v1 vectors: {passed} passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        AssertionError,
        json.JSONDecodeError,
        KeyError,
        RuntimeError,
        TypeError,
        VectorError,
    ) as error:
        print(f"vector validation failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
