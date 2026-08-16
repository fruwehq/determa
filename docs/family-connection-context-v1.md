# Determa Family Connection and Context Configuration v1

## Status and scope

This document defines the **public, language-neutral configuration contract** for
future Determa family clients. It reserves stable names and resolution semantics
before Determa Cloud, customer-hosted endpoints, or remote product clients are
implemented.

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHOULD**, **SHOULD NOT**,
and **MAY** are to be interpreted as described in RFC 2119 and RFC 8174.

Current Python, Rust, and Node `determa` packages implement this contract as
local resolver APIs and reserve the family command names below before product
dispatch. They do not discover or read a configuration file and do not perform
remote transport. This document does not define a configuration-file location,
credential store, network protocol, server, client, or State machine/checkpoint
format. The Rust implementation uses exact behavior-relevant ICU data
dependencies and a checked lockfile because the v1 endpoint profile depends on
the exact Unicode 15.1 UTS #46 boundary.

## Principles

- A connection is named, reusable, and product-neutral. A process MAY use many
  connections concurrently.
- Contexts select routes; they are not a process-wide endpoint singleton.
- Connections contain endpoint identity and a reference to credentials, never
  credentials themselves.
- Machine definitions, portable State checkpoints, State `store_uri` values,
  and `DETERMA_<PRODUCT>_IMPL` are not connection configuration.
- The same contract applies to a Determa-managed endpoint and a customer-hosted
  endpoint. Endpoint ownership is not inferred from its name or URL.

## Logical configuration model

A future configuration source represents the following closed, JSON-shaped
logical model. Its file syntax, location, and discovery rules are intentionally
unspecified in v1. Concrete syntaxes MUST preserve the value types below and
MUST reject duplicate map keys before constructing this model.

```yaml
version: 1
default_context: personal
connections:
  cloud:
    endpoint: https://api.determa.example
    credential_ref:
      provider: keychain
      name: determa-cloud-personal
  customer-production:
    endpoint: https://determa.example.customer
    credential_ref:
      provider: environment
      name: CUSTOMER_DETERMA_TOKEN
contexts:
  personal:
    routes:
      state: cloud
      state/instances: cloud
  customer:
    routes:
      state: customer-production
defaults:
  routes:
    guard: cloud
```

The model is closed as follows. "Map" means a map with string keys. No field
accepts `null`, an array, a Boolean, or a numeric value unless the table says so.

| location | field | presence | value |
|---|---|---|---|
| root | `version` | required | integer exactly equal to numeric `1` |
| root | `connections` | required | connection map; MAY be empty |
| root | `contexts` | required | context map; MAY be empty |
| root | `default_context` | optional | context name |
| root | `defaults` | optional | defaults object |
| connection | `endpoint` | required | non-empty string accepted by the canonical endpoint profile |
| connection | `credential_ref` | optional | credential-reference object |
| credential reference | `provider` | required | provider name |
| credential reference | `name` | required | non-empty provider-specific string |
| context | `routes` | required | route map; MAY be empty |
| defaults | `routes` | required | route map; MAY be empty |

Every object MUST reject fields not listed for its location. The string `"1"`,
the numbers `1.0` and `1e0`, and the Boolean `true` are not the required integer
`version: 1`. A concrete syntax that cannot distinguish an integer token from a
non-integer numeric token MUST reject the latter tokens before constructing the
logical model.

Connection names, context names, and credential-provider names MUST match
`^[a-z][a-z0-9-]*$`. They are case-sensitive ASCII strings and undergo no
normalization. Names MUST be unique within their map. Connection and context
names occupy separate namespaces, so the same name MAY occur once in each map.
Two connections MAY have the same canonical endpoint and remain distinct named
connections.

A route key MUST be a product/resource value defined below. A route value MUST
be a connection-name string and MUST name an entry in `connections`.
`default_context`, when present, MUST name an entry in `contexts`. Duplicate
source keys and duplicate logical names are invalid even if their associated
values are equal. Because every logical name is already canonical ASCII, there
is no case folding or Unicode normalization that can merge names after parsing.

An empty `connections` map is valid but no remote request can resolve. An empty
`contexts` map is valid only when `default_context` is absent. An empty context
`routes` map contributes no route. An absent `defaults` object and a present
`defaults: {routes: {}}` object have the same routing effect.

`credential_ref` is optional. When present, it is a structured opaque locator.
It MAY identify an operating-system keychain, environment variable, workload
identity, secret manager, or another credential provider. `name` is interpreted
only by the named provider and is not normalized by the family contract.
`provider` and `name` MUST NOT contain a token, private key, password,
certificate body, authorization header, or other secret material. The provider
resolves a credential only when a future client performs authenticated
transport; the resolved value is never part of this logical configuration or a
portable State value.

These examples are normative model-validation vectors:

| value | result | reason |
|---|---|---|
| `{version: 1, connections: {}, contexts: {}}` | valid | minimal configuration; resolution always fails |
| `{version: 1, connections: {}, contexts: {}, defaults: {routes: {}}}` | valid | explicit empty defaults |
| `{version: 1, connections: {}, contexts: {personal: {routes: {}}}, default_context: personal}` | valid | empty default context contributes no route |
| `{version: "1", connections: {}, contexts: {}}` | invalid | version is a string |
| `{version: 1.0, connections: {}, contexts: {}}` | invalid | version token is not an integer |
| `{version: 1, connections: {}}` | invalid | `contexts` is required |
| `{version: 1, connections: [], contexts: {}}` | invalid | `connections` is not a map |
| `{version: 1, connections: {}, contexts: {}, extra: {}}` | invalid | unknown root field |
| `{version: 1, connections: {cloud: {endpoint: "https://example.com", extra: true}}, contexts: {}}` | invalid | unknown connection field |
| `{version: 1, connections: {}, contexts: {}, default_context: personal}` | invalid | referenced context is absent |
| `{version: 1, connections: {}, contexts: {personal: {routes: {state: cloud}}}}` | invalid | referenced connection is absent |
| `{version: 1, connections: {cloud: {endpoint: ""}}, contexts: {}}` | invalid | endpoint is empty |
| `{version: 1, connections: {cloud: {endpoint: "https://example.com", credential_ref: null}}, contexts: {}}` | invalid | optional fields cannot be null |

A source document containing two `cloud` keys in the same `connections` map is
invalid before model construction. A parser MUST NOT keep the first value, keep
the last value, or silently merge the two connection objects.

## Canonical endpoints

Each connection has exactly one `endpoint`. A configuration reader MUST apply
the ordered algorithm below before comparison, routing, or persistence. The
result is an ASCII absolute URI under RFC 3986. Implementations MUST implement
this profile directly or prove their URL library produces the same result; a
library's platform-dependent URL normalization is not normative.

1. The input MUST be a non-empty Unicode string. Reject ASCII whitespace,
   control characters, backslash, an invalid Unicode scalar sequence, and any
   leading or trailing whitespace rather than trimming it.
2. Parse component boundaries as an absolute URI according to RFC 3986, with
   one extension: a registered-name host MAY contain Unicode scalar values for
   the UTS #46 processing in step 4. Every other component remains within the
   RFC 3986 ASCII grammar. The value MUST have scheme, authority, non-empty
   host, and optional path only. User-info, query, and fragment components are
   forbidden. Opaque URIs and relative references are forbidden.
3. ASCII-lowercase the scheme. It MUST be `https` or `http`.
4. Canonicalize exactly one host form:
   - A registered name is processed with Unicode Technical Standard #46,
     revision 31, using the Unicode 15.1.0 data and these options:
     `Transitional_Processing=false`, `UseSTD3ASCIIRules=true`,
     `CheckHyphens=true`, `CheckBidi=true`, `CheckJoiners=true`, and
     `VerifyDnsLength=true`, and `IgnoreInvalidPunycode=false`. Apply `ToASCII`,
     lowercase the result, and reject an empty label or trailing root dot.
     Percent encoding in a host is invalid.
   - An IPv4 address MUST contain exactly four ASCII decimal octets separated by
     dots. Each octet is `0` or starts with `1` through `9`, contains no sign or
     leading zero, and has value 0 through 255. Emit those decimal octets.
     Before registered-name processing, an ASCII host matching the
     case-insensitive regular expression
     `^(?:0x[0-9a-f]+|[0-9]+)(?:\.(?:0x[0-9a-f]+|[0-9]+))*$` is IPv4-like and
     MUST be rejected unless it satisfies this strict form. This excludes
     single-integer, hexadecimal, octal-looking, and shortened IPv4 spellings
     accepted by some URL libraries.
   - A bracketed IPv6 literal MUST parse under RFC 4291 section 2.2 and MUST be
     emitted in brackets using RFC 5952 sections 4.1 through 4.3. Always emit
     all 128 bits in hexadecimal form; an accepted IPv4-embedded input such as
     `::ffff:192.0.2.1` is emitted as `::ffff:c000:201`, never with dotted
     decimal. IPvFuture literals are invalid. Zone identifiers, including
     RFC 6874 `%25zone` syntax, are invalid.
5. A port, when present, MUST contain only ASCII decimal digits, begin with
   `1` through `9`, and have value 1 through 65535. Remove port 443 for `https`
   and port 80 for `http`; emit every other port as its shortest decimal form.
   An empty port, sign, leading zero, or out-of-range value is invalid.
6. The path MUST be empty or begin with `/`. Every source character in it MUST
   be ASCII and be `/`, an RFC 3986 `pchar`, or part of a valid `%HH` triplet.
   Raw non-ASCII path characters and malformed percent triplets are invalid.
   Uppercase every percent-triplet hex pair, then decode triplets for RFC 3986
   unreserved ASCII characters (`ALPHA`, `DIGIT`, `-`, `.`, `_`, `~`). Reject
   percent-encoded non-ASCII octets, C0 controls, DEL, `/`, and backslash. Other
   percent-encoded ASCII octets remain encoded with uppercase hex.
7. After the percent step, remove dot segments with the RFC 3986 section 5.2.4
   algorithm. An encoded dot decoded in step 6 participates in this algorithm;
   an encoded reserved character does not. Preserve other repeated slashes and
   empty path segments.
8. Normalize an empty path to `/`. Preserve `/` as the one root representation.
   For a non-root path, remove all trailing `/` characters; if that would make
   the path empty, emit `/`. Concatenate the lowercase scheme, `://`, canonical
   host, optional non-default port, and canonical path.
9. `http` is valid only when the canonical host is exactly `localhost`, an IPv4
   address in `127.0.0.0/8`, or IPv6 `::1`. All other hosts require `https`.

The UTS #46 revision, Unicode version, and option values above are part of v1.
A runtime whose native IDNA behavior differs MUST use compatible data or reject
an input it cannot process according to revision 31 and Unicode 15.1.0. RFC
3986, RFC 4291, RFC 5952, and UTS #46 are used only in the explicitly cited
roles; WHATWG URL coercions and operating-system hostname shortcuts are not
part of this profile.

Canonical endpoint vectors:

| input | canonical endpoint |
|---|---|
| `https://EXAMPLE.com` | `https://example.com/` |
| `HTTPS://bücher.example:443/a/./b/%7euser/` | `https://xn--bcher-kva.example/a/b/~user` |
| `https://faß.example` | `https://xn--fa-hia.example/` |
| `https://example.com:8443/a//b/` | `https://example.com:8443/a//b` |
| `https://example.com/a/%2E%2E/b/%3a` | `https://example.com/b/%3A` |
| `http://127.0.0.1:80` | `http://127.0.0.1/` |
| `http://[0:0:0:0:0:0:0:1]:8080/a/..` | `http://[::1]:8080/` |
| `https://[::ffff:192.0.2.1]` | `https://[::ffff:c000:201]/` |

The following inputs are invalid: `example.com` (relative),
`ftp://example.com/` (scheme), `https://user@example.com/` (user-info),
`https://example.com/?x=1` (query), `https://example.com/#x` (fragment),
`https://example.com./` (root dot), `https://127.1/` (short IPv4),
`https://0177.0.0.1/` (leading-zero IPv4), `https://0x7f000001/` (hexadecimal
IPv4), `http://example.com/` (non-loopback HTTP),
`http://[fe80::1%25en0]/` (IPv6 zone), `https://[v1.example]/` (IPvFuture),
`https://example.com:0443/` (leading-zero port),
`https://example.com/%2f` (encoded slash), and
`https://example.com/café` (raw non-ASCII path).

Redirect policy, certificate exceptions, proxies, and transport retries belong
to the future protocol/client contract, not this configuration contract.

## Products, resources, and routing

A product name and each resource path segment MUST match
`^[a-z][a-z0-9-]*$`. A resource is the product name followed by zero or more
`/`-separated resource segments, such as `state/instances` or
`ledger/accounts`. The product-only route (`state`) is its product default.

Each `routes` map key is a product or resource. A selected context supplies
context routes. Top-level `defaults.routes` supplies product/resource defaults
when the selected context has no matching route. For request resource `R`, only
the exact `R` key and its product-only key are candidates, in that order.
Intermediate resource prefixes do not match. This document defines no wildcard
routes.

Every future remote request MUST resolve to one named connection before it is
created. Credentials are resolved at delivery time so they can rotate. The
later durable host-owned route-binding contract MUST retain a request's resolved
connection name, canonical endpoint, product/resource, and configuration
revision with its outbox work; endpoint changes MUST NOT silently retarget
already-created work. That record and its transaction semantics are deferred
from this v1 document.

## Resolution precedence

For a request for product/resource `R`, connection resolution is exactly:

1. An explicit per-request connection override.
2. An environment override.
3. A route in the explicitly selected context.
4. A route in `defaults.routes`.
5. A route in the global `default_context`.

At each route level, an exact resource route wins over its product route. An
absent value proceeds to the next level. An explicit override and an environment
override MUST be connection names present in `connections`. An explicitly
selected context MUST be present in `contexts`; if no context is explicitly
selected, step 3 contributes no route. Any present but invalid value is an
error and MUST NOT fall through. If `default_context` is absent, step 5
contributes no route. If no connection resolves, the request fails locally
before transport.

Future implementations use these environment override names, from most to
least specific within step 2:

```text
DETERMA_<ENCODED_PRODUCT>__<ENCODED_RESOURCE_SEGMENT>..._CONNECTION
DETERMA_<ENCODED_PRODUCT>_CONNECTION
DETERMA_CONNECTION
```

Encoding is injective for every valid product and resource segment:

1. Encode each segment independently. Uppercase ASCII letters, preserve digits,
   and replace each `-` with `_H`. Because `_` is not valid in an input segment,
   this segment encoding is reversible and never contains `__`.
2. Join the encoded product and resource segments with the two-character
   separator `__`.
3. Prefix `DETERMA_` and suffix `_CONNECTION`.

The product-only variable omits the separator and resource portion. These
vectors prove the segment boundary is not flattened:

| product/resource | environment variable |
|---|---|
| `state` | `DETERMA_STATE_CONNECTION` |
| `state/instances` | `DETERMA_STATE__INSTANCES_CONNECTION` |
| `state/foo-bar` | `DETERMA_STATE__FOO_HBAR_CONNECTION` |
| `state/foo/bar` | `DETERMA_STATE__FOO__BAR_CONNECTION` |
| `state/foo--bar` | `DETERMA_STATE__FOO_H_HBAR_CONNECTION` |

Therefore `state/foo-bar`, `state/foo/bar`, and `state/foo--bar` cannot select
the same environment variable. Only the exact names generated by this algorithm
participate in step 2; legacy single-underscore flattening is not recognized.
The environment value MUST be a configured connection name, not a URL, context
name, credential reference, or secret. A present empty value or absent
connection name is an error and MUST NOT fall through. An explicit context
selection is an input to step 3; v1 deliberately does not reserve an environment
variable for selecting a context.

## Command namespace reservation

The family-level command names `config`, `context`, and `auth` are reserved.
No present or future product may claim those names, and each Python, Rust, and
Node launcher implementation MUST recognize them before product dispatch. Their
subcommands, flags, output, and persistence behavior are not implemented or
specified here.

Until command syntax is specified, invoking `determa config`, `determa context`,
or `determa auth` MUST fail locally before product dispatch with exit status
`2`, empty stdout, and stderr exactly:

```text
determa: family command '<command>' is reserved but not implemented yet.
```

## Local implementation selection and State storage

`DETERMA_<PRODUCT>_IMPL` remains exclusively a local executable-selection
mechanism. For example, `DETERMA_STATE_IMPL=python` selects
`determa-state-python`; it MUST NOT select a remote endpoint, connection, or
credential.

Likewise, a Determa State `store_uri` identifies a language-local State storage
adapter and its implementation-specific options. It MUST NOT be interpreted as
a family connection endpoint, and connection endpoints MUST NOT be passed into
State storage selection. This separation lets State storage adapters remain
pluggable without privileging any storage scheme or accidentally treating a
database URI as a cloud route.

## Execution boundary

An embedded `ExecutionHost` runs a Determa State aggregate in the host process.
It owns persistence, transactions, inbox/outbox handling, and local adapter
selection. It does not require a family connection.

A future `DetermaClient` is a separate boundary for remote product operations.
It will resolve a connection using this document, acquire credentials through a
credential provider, and speak a separately versioned protocol. It MUST NOT
move networking, endpoint identity, credentials, tenant identity, or deployment
configuration into the portable State engine, machine format, or checkpoint.

Applications MAY combine embedded and remote use in one process by using
separate explicitly named connections and contexts for each remote operation.
There is no implicit global remote endpoint.

## Normative references

- [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) and
  [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174) define requirement words.
- [RFC 3986](https://www.rfc-editor.org/rfc/rfc3986) defines URI syntax,
  percent-encoding normalization, and dot-segment removal.
- [RFC 4291](https://www.rfc-editor.org/rfc/rfc4291) defines accepted IPv6
  address syntax.
- [RFC 5952](https://www.rfc-editor.org/rfc/rfc5952) sections 4.1 through 4.3
  define hexadecimal IPv6 canonicalization. This profile deliberately chooses
  pure hexadecimal for the special addresses discussed in its section 5.
- [RFC 6874](https://www.rfc-editor.org/rfc/rfc6874) defines the IPv6 zone syntax
  that this endpoint profile deliberately rejects.
- [UTS #46 revision 31](https://www.unicode.org/reports/tr46/tr46-31.html) and
  its Unicode 15.1.0 data define registered-name processing.

## Deferred work

The following work is intentionally excluded from v1 and requires separate
issues and review before implementation:

- Configuration-file discovery, editing, and credential-provider behavior.
- Launcher parsing and behavior for the reserved family commands.
- A versioned managed/self-hosted protocol, capability discovery, closed error
  envelopes, resource identity, authentication rules, idempotency, concurrency,
  pagination, TLS, and redirect rules.
- Language-specific `DetermaClient` packages and transport implementations.
- Shared routing conformance vectors and protocol conformance.
- Durable host-owned route-binding/outbox schemas and SaaS control-plane work.
- State specification, engine, checkpoint, store, socket, MCP, or example
  changes.
