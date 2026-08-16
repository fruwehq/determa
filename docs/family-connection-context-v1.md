# Determa Family Connection and Context Configuration v1

## Status and scope

This document defines the **public, language-neutral configuration contract** for
future Determa family clients. It reserves stable names and resolution semantics
before Determa Cloud, customer-hosted endpoints, or remote product clients are
implemented.

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHOULD**, **SHOULD NOT**,
and **MAY** are to be interpreted as described in RFC 2119 and RFC 8174.

This is a design contract only. Current Python, Rust, and Node `determa`
launchers do not read this configuration and retain their existing behavior.
It does not define a configuration-file location, credential store, network
protocol, server, client, or State machine/checkpoint format.

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

A future configuration source represents the following logical model. Its
storage format and discovery rules are intentionally unspecified in v1.

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

`connections` and `contexts` are maps keyed by unique names. A name MUST match
`^[a-z][a-z0-9-]*$`. A route target MUST name a configured connection. A
configuration is invalid if `default_context` is present but does not name a
configured context, or if a route refers to an absent connection.

`credential_ref` is optional. When present, it is a structured opaque locator:
`provider` uses the connection-name grammar and `name` is a non-empty,
provider-specific opaque locator. It MAY identify an operating-system keychain,
environment variable, workload identity, secret manager, or another credential
provider. `name` is not normalized by the family contract. Neither field MUST
contain a token, private key, password, certificate body, authorization header,
or other secret material. The provider resolves a credential only at the point
a future client performs authenticated transport; the resolved value is never
part of this logical configuration or a portable State value.

## Canonical endpoints

Each connection has exactly one `endpoint`. Its canonical value MUST be an
absolute HTTP(S) URL with these properties:

- The scheme is lowercase `https` or `http`. `https` is REQUIRED except for a
  loopback host (`localhost`, `127.0.0.0/8`, or `::1`) used for local development.
- It has no user-info, query, or fragment component.
- A DNS host is lowercased and converted to its ASCII IDNA form. An IP literal
  is represented in its canonical textual form.
- A default port (`443` for HTTPS or `80` for HTTP) is omitted; another port is
  retained.
- Its path is absolute, has dot segments removed, and has no trailing slash
  unless it is the root path `/`.

A configuration reader MUST normalize an input endpoint to this value before
comparison, route binding, or persistence. Inputs that cannot be normalized
unambiguously are invalid. Redirect policy, certificate exceptions, proxies,
and transport retries belong to the future protocol/client contract, not this
configuration contract.

## Products, resources, and routing

A product name and each resource path segment MUST match
`^[a-z][a-z0-9-]*$`. A resource is the product name followed by zero or more
`/`-separated resource segments, such as `state/instances` or
`ledger/accounts`. The product-only route (`state`) is its product default.

Each `routes` map key is a product or resource. A selected context supplies
context routes. Top-level `defaults.routes` supplies product/resource defaults
when the selected context has no matching route. A more-specific resource route
matches before its product route. This document defines no wildcard routes.

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
absent value proceeds to the next level. A present but invalid value is an
error; it MUST NOT fall through. If no connection resolves, the request fails
locally before transport.

Future implementations use these environment override names, from most to
least specific within step 2:

```text
DETERMA_<PRODUCT>_<RESOURCE>_CONNECTION
DETERMA_<PRODUCT>_CONNECTION
DETERMA_CONNECTION
```

`<PRODUCT>` and every `<RESOURCE>` segment are uppercased, with `-` replaced by
`_`, and are joined with `_`. For example, `state/instances` uses
`DETERMA_STATE_INSTANCES_CONNECTION`. The value is a configured connection
name, not a URL or secret. An explicit context selection is an input to step 3;
this version deliberately does not reserve an environment variable for it.

## Command namespace reservation

The family-level command names `config`, `context`, and `auth` are reserved.
No present or future product may claim those names, and each future Python,
Rust, and Node launcher implementation MUST recognize them before product
dispatch. Their commands, flags, output, and persistence behavior are not
implemented or specified here.

This reservation does not change current launcher behavior. In particular,
this document does not add a parser, help entry, executable command, or
compatibility promise for `determa config`, `determa context`, or `determa auth`
until a later implementation release changes all three launchers together.

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
