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
    assert.deepStrictEqual(operation(), case_.expect.value, case_.id);
  }
}

for (const case_ of loadFixture("configuration.json").cases) {
  assertCase(case_, () => family.parseConfigurationSource(case_.source));
}

for (const case_ of loadFixture("endpoints.json").cases) {
  assertCase(case_, () => family.canonicalizeEndpoint(case_.input));
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

console.log("family connection/context v1 node vectors: 152 passed");
