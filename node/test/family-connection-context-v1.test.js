"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");

const family = require("determa/family-connection-context-v1");

const ROOT = path.resolve(__dirname, "..", "..");
const VECTOR_ROOT = path.join(ROOT, "conformance", "family-connection-v1");

function loadFixture(name) {
  return JSON.parse(fs.readFileSync(path.join(VECTOR_ROOT, name), "utf8"));
}

function assertCase(case_, operation) {
  if (Object.prototype.hasOwnProperty.call(case_.expect, "error")) {
    assert.throws(
      operation,
      error => error instanceof family.FamilyConnectionError && error.code === case_.expect.error,
      case_.id
    );
  } else {
    let value = operation();
    if (value instanceof family.ValidatedConfiguration) value = value.toValue();
    assert.deepStrictEqual(JSON.parse(JSON.stringify(value)), case_.expect.value, case_.id);
  }
}

for (const case_ of loadFixture("configuration.json").cases) {
  assertCase(case_, () => family.parseConfigurationSource(case_.source));
}

for (const case_ of loadFixture("endpoints.json").cases) {
  assertCase(case_, () => family.canonicalizeEndpoint(case_.input));
}

for (const endpoint of [
  "https://[192.0.2.1::5.6.7.8]/",
  "https://[::192.0.2.1:5.6.7.8]/",
  "https://[1:2:3:4:192.0.2.1:5.6.7.8]/",
]) {
  assert.throws(
    () => family.canonicalizeEndpoint(endpoint),
    error =>
      error instanceof family.FamilyConnectionError &&
      error.code === "invalid_endpoint_host",
    endpoint
  );
}

const environmentFixture = loadFixture("environment.json");
const environmentResults = new Map();
for (const case_ of environmentFixture.cases) {
  assertCase(case_, () => family.environmentName(case_.resource));
  if (Object.prototype.hasOwnProperty.call(case_.expect, "value")) {
    environmentResults.set(case_.id, case_.expect.value);
  }
}
for (const distinctSet of environmentFixture.distinct_sets || []) {
  const values = distinctSet.map(caseId => environmentResults.get(caseId));
  assert.strictEqual(new Set(values).size, values.length, distinctSet.join(", "));
}

const routingFixture = loadFixture("routing.json");
const configurations = {};
for (const [name, source] of Object.entries(routingFixture.configurations)) {
  configurations[name] = family.parseConfigurationSource(source);
}
for (const case_ of routingFixture.cases) {
  const configuration = configurations[case_.configuration];
  assertCase(case_, () => family.resolveConnection(configuration, case_.request));
}

const decoded = {
  version: 1,
  connections: { cloud: { endpoint: "https://example.com" } },
  contexts: {},
};
const validated = family.validateConfiguration(decoded);
decoded.connections.cloud.endpoint = "https://changed.example";
const exported = validated.toValue();
delete exported.connections.cloud;
assert.strictEqual(
  family.resolveConnection(validated, {
    resource: "state",
    explicit_connection: "cloud",
  }),
  "cloud"
);

for (const malformed of [null, {}, [], "configuration"]) {
  assert.throws(
    () => family.resolveConnection(malformed, { resource: "state" }),
    error => error instanceof family.FamilyConnectionError && error.code === "invalid_type"
  );
}
for (const malformed of [null, [], "configuration", 1]) {
  assert.throws(
    () => family.validateConfiguration(malformed),
    error => error instanceof family.FamilyConnectionError && error.code === "invalid_type"
  );
}
for (const malformed of [null, [], "state", 1]) {
  assert.throws(
    () => family.resolveConnection(validated, malformed),
    error => error instanceof family.FamilyConnectionError && error.code === "invalid_type"
  );
}

const vectorCount =
  loadFixture("configuration.json").cases.length +
  loadFixture("endpoints.json").cases.length +
  environmentFixture.cases.length +
  routingFixture.cases.length;
console.log(`family connection/context v1 node vectors: ${vectorCount} passed`);
