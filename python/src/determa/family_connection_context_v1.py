"""Family Connection/Context v1 production resolver APIs."""

from __future__ import annotations

import bisect
import ipaddress
import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

import idna
from idna import idnadata, uts46data
from idna.core import valid_contextj

NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")
IPV4_RE = re.compile(r"^(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*)){3}$")
IPV4_LIKE_RE = re.compile(
    r"^(?:0x[0-9a-f]+|[0-9]+)(?:\.(?:0x[0-9a-f]+|[0-9]+))*$",
    re.IGNORECASE,
)
ENDPOINT_RE = re.compile(r"^([A-Za-z][A-Za-z0-9+.-]*):\/\/([^\/?#]*)([^?#]*)$")
PCHAR = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~!$&'()*+,;=:@"
)
UNRESERVED = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
HEX = frozenset("0123456789abcdefABCDEF")
EXPECTED_UNICODE_VERSION = "15.1.0"


class FamilyConnectionError(ValueError):
    """Raised when a v1 value violates the public resolver contract."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class IntegerToken:
    source: str


@dataclass(frozen=True)
class NonIntegerNumberToken:
    source: str


def _error(code: str) -> FamilyConnectionError:
    return FamilyConnectionError(code)


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _error("duplicate_key")
        result[key] = value
    return result


def _reject_nonfinite_constant(_value: str) -> Any:
    raise _error("invalid_source")


def parse_configuration_source(source: Any) -> dict[str, Any]:
    """Parse and validate a JSON source string into the closed logical model."""

    if not isinstance(source, str):
        raise _error("invalid_source")
    try:
        value = json.loads(
            source,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_int=IntegerToken,
            parse_float=NonIntegerNumberToken,
            parse_constant=_reject_nonfinite_constant,
        )
    except FamilyConnectionError:
        raise
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise _error("invalid_source") from exc
    return validate_configuration(value)


def _require_closed_object(value: Any, required: set[str], optional: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _error("invalid_type")
    if not required.issubset(value):
        raise _error("missing_field")
    if set(value) - required - optional:
        raise _error("unknown_field")
    return value


def _require_name(value: Any) -> str:
    if not isinstance(value, str):
        raise _error("invalid_type")
    if not NAME_RE.fullmatch(value):
        raise _error("invalid_name")
    return value


def _require_nonempty_string(value: Any) -> str:
    if not isinstance(value, str):
        raise _error("invalid_type")
    if not value:
        raise _error("invalid_name")
    return value


def _validate_routes(value: Any, connection_names: set[str]) -> dict[str, str]:
    if not isinstance(value, dict):
        raise _error("invalid_type")
    result: dict[str, str] = {}
    for resource, connection in value.items():
        validate_resource(resource)
        if not isinstance(connection, str):
            raise _error("invalid_type")
        if connection not in connection_names:
            raise _error("invalid_reference")
        result[resource] = connection
    return result


def validate_configuration(value: Any) -> dict[str, Any]:
    """Validate a decoded JSON-like configuration value."""

    root = _require_closed_object(
        value,
        {"version", "connections", "contexts"},
        {"default_context", "defaults"},
    )
    version = root["version"]
    if not isinstance(version, IntegerToken) or version.source != "1":
        raise _error("invalid_version")

    raw_connections = root["connections"]
    if not isinstance(raw_connections, dict):
        raise _error("invalid_type")
    connections: dict[str, Any] = {}
    for raw_name, raw_connection in raw_connections.items():
        name = _require_name(raw_name)
        connection = _require_closed_object(raw_connection, {"endpoint"}, {"credential_ref"})
        endpoint = canonicalize_endpoint(connection["endpoint"])
        normalized: dict[str, Any] = {"endpoint": endpoint}
        if "credential_ref" in connection:
            credential = _require_closed_object(
                connection["credential_ref"], {"provider", "name"}, set()
            )
            normalized["credential_ref"] = {
                "provider": _require_name(credential["provider"]),
                "name": _require_nonempty_string(credential["name"]),
            }
        connections[name] = normalized

    connection_names = set(connections)
    raw_contexts = root["contexts"]
    if not isinstance(raw_contexts, dict):
        raise _error("invalid_type")
    contexts: dict[str, Any] = {}
    for raw_name, raw_context in raw_contexts.items():
        name = _require_name(raw_name)
        context = _require_closed_object(raw_context, {"routes"}, set())
        contexts[name] = {"routes": _validate_routes(context["routes"], connection_names)}

    normalized_root: dict[str, Any] = {
        "version": 1,
        "connections": connections,
        "contexts": contexts,
    }
    if "default_context" in root:
        default_context = _require_name(root["default_context"])
        if default_context not in contexts:
            raise _error("invalid_reference")
        normalized_root["default_context"] = default_context
    if "defaults" in root:
        defaults = _require_closed_object(root["defaults"], {"routes"}, set())
        normalized_root["defaults"] = {
            "routes": _validate_routes(defaults["routes"], connection_names)
        }
    return normalized_root


def validate_resource(value: Any) -> list[str]:
    if not isinstance(value, str):
        raise _error("invalid_type")
    segments = value.split("/")
    if not segments or any(not NAME_RE.fullmatch(segment) for segment in segments):
        raise _error("invalid_name")
    return segments


def _uts46_status(codepoint: int) -> str:
    table = uts46data.uts46data
    row = table[
        codepoint if codepoint < 256 else bisect.bisect_left(table, (codepoint, "Z")) - 1
    ]
    return row[1]


def _validate_uts46_label(label: str) -> None:
    if not label:
        raise idna.IDNAError("label must be non-empty")
    if label.startswith("-") or label.endswith("-") or label[2:4] == "--":
        raise idna.IDNAError("label has disallowed hyphens")
    if "." in label or unicodedata.category(label[0]).startswith("M"):
        raise idna.IDNAError("label has invalid structure")
    for position, character in enumerate(label):
        if _uts46_status(ord(character)) not in {"V", "D"}:
            raise idna.IDNAError("label contains a disallowed code point")
        if character in {"\u200c", "\u200d"} and not valid_contextj(label, position):
            raise idna.IDNAError("label fails ContextJ")


def _encode_uts46_label(label: str) -> tuple[str, str]:
    if label.startswith("xn--"):
        if any(ord(character) > 0x7F for character in label):
            raise idna.IDNAError("Punycode label must be ASCII")
        try:
            unicode_label = label[4:].encode("ascii").decode("punycode")
        except UnicodeError as exc:
            raise idna.IDNAError("invalid Punycode label") from exc
    else:
        unicode_label = label
    _validate_uts46_label(unicode_label)
    if all(ord(character) < 0x80 for character in unicode_label):
        ascii_label = unicode_label
    else:
        ascii_label = "xn--" + unicode_label.encode("punycode").decode("ascii")
    if len(ascii_label.encode("ascii")) > 63:
        raise idna.IDNAError("label exceeds DNS length")
    return unicode_label, ascii_label


def _domain_to_ascii(host: str) -> str:
    try:
        mapped = idna.uts46_remap(host, std3_rules=True, transitional=False)
        source_labels = mapped.split(".")
        trailing_dot = bool(source_labels and source_labels[-1] == "")
        if trailing_dot:
            source_labels.pop()
        if not source_labels:
            raise idna.IDNAError("empty domain")
        encoded = [_encode_uts46_label(label) for label in source_labels]
        unicode_labels = [label for label, _ascii_label in encoded]
        bidi_domain = any(
            unicodedata.bidirectional(character) in {"R", "AL", "AN"}
            for label in unicode_labels
            for character in label
        )
        if bidi_domain:
            for label in unicode_labels:
                idna.check_bidi(label, check_ltr=True)
        ascii_domain = ".".join(label for _unicode_label, label in encoded)
        if trailing_dot:
            ascii_domain += "."
        maximum_length = 254 if trailing_dot else 253
        if len(ascii_domain.encode("ascii")) > maximum_length:
            raise idna.IDNAError("domain exceeds DNS length")
        return ascii_domain
    except (idna.IDNAError, UnicodeError):
        return ""


def validate_unicode_data_version() -> None:
    versions = {idnadata.__version__, uts46data.__version__}
    if versions != {EXPECTED_UNICODE_VERSION}:
        raise RuntimeError(
            "IDNA tables must both use Unicode "
            f"{EXPECTED_UNICODE_VERSION}, got {sorted(versions)}"
        )
    runtime_version = tuple(int(part) for part in unicodedata.unidata_version.split("."))
    if runtime_version < (15, 1, 0):
        raise RuntimeError(
            "runtime Unicode data must be at least 15.1.0, got "
            f"{unicodedata.unidata_version}"
        )


def _canonicalize_ipv6(address: ipaddress.IPv6Address) -> str:
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


def _canonicalize_host(raw_host: str, bracketed: bool) -> tuple[str, str, Any]:
    if not raw_host or "%" in raw_host:
        raise _error("invalid_endpoint_host")
    if bracketed:
        try:
            address = ipaddress.IPv6Address(raw_host)
        except ipaddress.AddressValueError as exc:
            raise _error("invalid_endpoint_host") from exc
        canonical = _canonicalize_ipv6(address)
        return f"[{canonical}]", "ipv6", address

    if IPV4_RE.fullmatch(raw_host):
        octets = raw_host.split(".")
        if any(int(octet) > 255 for octet in octets):
            raise _error("invalid_endpoint_host")
        canonical = ".".join(str(int(octet)) for octet in octets)
        return canonical, "ipv4", ipaddress.IPv4Address(canonical)
    if IPV4_LIKE_RE.fullmatch(raw_host):
        raise _error("invalid_endpoint_host")

    ascii_host = _domain_to_ascii(raw_host)
    if not ascii_host or ascii_host.endswith("."):
        raise _error("invalid_endpoint_host")
    labels = ascii_host.lower().split(".")
    if any(
        not label
        or len(label) > 63
        or not re.fullmatch(r"[a-z0-9-]+", label)
        or label.startswith("-")
        or label.endswith("-")
        for label in labels
    ):
        raise _error("invalid_endpoint_host")
    canonical = ".".join(labels)
    if len(canonical) > 253:
        raise _error("invalid_endpoint_host")
    return canonical, "registered", canonical


def _normalize_path(raw_path: str) -> str:
    output: list[str] = []
    index = 0
    while index < len(raw_path):
        character = raw_path[index]
        codepoint = ord(character)
        if codepoint > 0x7F:
            raise _error("invalid_endpoint_path")
        if character == "%":
            if (
                index + 2 >= len(raw_path)
                or raw_path[index + 1] not in HEX
                or raw_path[index + 2] not in HEX
            ):
                raise _error("invalid_endpoint_path")
            octet = int(raw_path[index + 1 : index + 3], 16)
            if octet >= 0x80 or octet <= 0x1F or octet in {0x7F, 0x2F, 0x5C}:
                raise _error("invalid_endpoint_path")
            decoded = chr(octet)
            output.append(decoded if decoded in UNRESERVED else f"%{octet:02X}")
            index += 3
            continue
        if character != "/" and character not in PCHAR:
            raise _error("invalid_endpoint_path")
        output.append(character)
        index += 1
    return _remove_dot_segments("".join(output))


def _remove_last_segment(path: str) -> str:
    slash = path.rfind("/")
    return "" if slash < 0 else path[:slash]


def _remove_dot_segments(path: str) -> str:
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
            output = _remove_last_segment(output)
        elif source == "/..":
            source = "/"
            output = _remove_last_segment(output)
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
    """Canonicalize one endpoint string according to the v1 endpoint profile."""

    if not isinstance(value, str):
        raise _error("invalid_endpoint_type")
    if not value:
        raise _error("invalid_endpoint_syntax")
    if any(
        character == "\\"
        or character == " "
        or ord(character) <= 0x1F
        or ord(character) == 0x7F
        or 0xD800 <= ord(character) <= 0xDFFF
        for character in value
    ):
        raise _error("invalid_endpoint_characters")
    match = ENDPOINT_RE.fullmatch(value)
    if not match:
        raise _error("invalid_endpoint_syntax")
    scheme, authority, raw_path = match.groups()
    scheme = scheme.lower()
    if scheme not in {"http", "https"}:
        raise _error("unsupported_endpoint_scheme")
    if not authority or "@" in authority:
        raise _error("invalid_endpoint_authority")

    bracketed = authority.startswith("[")
    raw_port: Any = None
    if bracketed:
        close = authority.find("]")
        if close < 0:
            raise _error("invalid_endpoint_authority")
        raw_host = authority[1:close]
        remainder = authority[close + 1 :]
        if remainder:
            if not remainder.startswith(":"):
                raise _error("invalid_endpoint_authority")
            raw_port = remainder[1:]
    else:
        if "[" in authority or "]" in authority or authority.count(":") > 1:
            raise _error("invalid_endpoint_authority")
        if ":" in authority:
            raw_host, raw_port = authority.rsplit(":", 1)
        else:
            raw_host = authority

    canonical_host, host_kind, host_value = _canonicalize_host(raw_host, bracketed)
    canonical_port = ""
    if raw_port is not None:
        if not re.fullmatch(r"[1-9][0-9]*", raw_port):
            raise _error("invalid_endpoint_port")
        port = int(raw_port)
        if port > 65535:
            raise _error("invalid_endpoint_port")
        if not ((scheme == "https" and port == 443) or (scheme == "http" and port == 80)):
            canonical_port = f":{port}"

    path = _normalize_path(raw_path)
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
            raise _error("insecure_endpoint")
    return f"{scheme}://{canonical_host}{canonical_port}{path}"


def environment_name(resource: Any) -> str:
    """Return the injective v1 environment override variable for a resource."""

    segments = validate_resource(resource)

    def encode(segment: str) -> str:
        return "".join("_H" if character == "-" else character.upper() for character in segment)

    return f"DETERMA_{'__'.join(encode(segment) for segment in segments)}_CONNECTION"


def _route_keys(resource: str) -> list[str]:
    product = resource.split("/", 1)[0]
    return [resource] if product == resource else [resource, product]


def _first_route(routes: dict[str, str], resource: str) -> Any:
    for key in _route_keys(resource):
        if key in routes:
            return routes[key]
    return None


def resolve_connection(configuration: dict[str, Any], request: dict[str, Any]) -> str:
    """Resolve one request to a named connection using exact v1 precedence."""

    resource = request.get("resource")
    validate_resource(resource)
    connections = configuration["connections"]

    if "explicit_connection" in request:
        explicit = request["explicit_connection"]
        if not isinstance(explicit, str) or explicit not in connections:
            raise _error("invalid_connection")
        return explicit

    environment = request.get("environment", {})
    if not isinstance(environment, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in environment.items()
    ):
        raise _error("invalid_environment")
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
                raise _error("invalid_connection")
            return connection

    if "selected_context" in request:
        selected = request["selected_context"]
        if not isinstance(selected, str) or selected not in configuration["contexts"]:
            raise _error("invalid_context")
        connection = _first_route(configuration["contexts"][selected]["routes"], resource)
        if connection is not None:
            return connection

    defaults = configuration.get("defaults", {"routes": {}})
    connection = _first_route(defaults["routes"], resource)
    if connection is not None:
        return connection

    default_context = configuration.get("default_context")
    if default_context is not None:
        connection = _first_route(configuration["contexts"][default_context]["routes"], resource)
        if connection is not None:
            return connection
    raise _error("unresolved_connection")
