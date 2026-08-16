# Family Connection/Context v1 conformance vectors

These JSON fixtures are the ecosystem-neutral executable examples for
[Family Connection and Context Configuration v1](../../docs/family-connection-context-v1.md).
They do not define a production client or resolver.

## Suites

- `configuration.json` stores configuration inputs as JSON source strings so
  integer spellings and duplicate keys remain testable. Successful cases return
  the closed normalized logical value; rejected cases return an error code.
- `endpoints.json` maps endpoint inputs to canonical endpoints or rejection
  codes.
- `environment.json` maps product/resource names to environment override names
  and declares sets that must remain pairwise distinct.
- `routing.json` defines reusable valid configurations and request cases for
  precedence, exact/product matching, invalid-value handling, and context
  fallback.

Every case has a repository-wide unique `id` and an `expect` object containing
exactly one of:

```json
{"value": "canonical output"}
```

```json
{"error": "stable_error_code"}
```

## Error codes

| code | meaning |
|---|---|
| `duplicate_key` | a source object repeats a key before model construction |
| `invalid_source` | source JSON is malformed or unavailable as a string |
| `missing_field` | a required closed-model field is absent |
| `unknown_field` | a closed-model object contains an undeclared field |
| `invalid_type` | a value has a type not accepted at that location |
| `invalid_version` | `version` is not the integer token `1` |
| `invalid_name` | a connection, context, provider, product, or resource name is invalid |
| `invalid_reference` | a context or route names an absent object |
| `invalid_endpoint_type` | an endpoint is not a string |
| `invalid_endpoint_characters` | an endpoint contains forbidden whitespace, controls, surrogates, or backslash |
| `invalid_endpoint_syntax` | an endpoint is empty, relative, opaque, or has a query/fragment |
| `unsupported_endpoint_scheme` | an endpoint scheme is not HTTP(S) |
| `invalid_endpoint_authority` | authority structure, user-info, or IP brackets are invalid |
| `invalid_endpoint_host` | IDNA, IPv4, IPv6, zone, or host-label validation fails |
| `invalid_endpoint_port` | a port is empty, non-canonical, zero, or out of range |
| `invalid_endpoint_path` | path syntax or percent encoding is unsupported |
| `insecure_endpoint` | HTTP targets a non-loopback host |
| `invalid_environment` | environment overrides are not a string map |
| `invalid_connection` | a present override is empty or names an absent connection |
| `invalid_context` | a selected context is not a configured context name |
| `unresolved_connection` | every resolution level is absent |

These codes classify vector outcomes only. A later public client/protocol error
contract requires its own specification and conformance work.

## Validation

From the repository root:

```sh
python3 scripts/validate-family-connection-v1-vectors.py
```

The validator uses only the Python standard library. Its test-only IDNA path
normalizes and Punycode-encodes only the non-ASCII scalars exercised by the
committed positive cases and conservatively rejects every other non-ASCII host
scalar. It does not claim to implement the complete UTS #46 data. This prevents
platform URL helpers from substituting transitional processing while keeping
the fixture outputs normative. The harness independently applies the v1 strict
URI, configuration, environment-name, and routing rules and is not shipped in
any package.
