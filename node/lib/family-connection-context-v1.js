"use strict";

const tr46 = require("tr46");

const NAME_RE = /^[a-z][a-z0-9-]*$/;
const IPV4_RE = /^(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*)){3}$/;
const IPV4_LIKE_RE = /^(?:0x[0-9a-f]+|[0-9]+)(?:\.(?:0x[0-9a-f]+|[0-9]+))*$/i;
const ENDPOINT_RE = /^([A-Za-z][A-Za-z0-9+.-]*):\/\/([^/?#]*)([^?#]*)$/u;
const PCHAR = new Set(
  "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~!$&'()*+,;=:@"
);
const UNRESERVED = new Set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~");
const RESERVED_FAMILY_COMMANDS = new Set(["auth", "config", "context"]);

class FamilyConnectionError extends Error {
  constructor(code) {
    super(code);
    this.code = code;
  }
}

class IntegerToken {
  constructor(source) {
    this.source = source;
  }
}

class NumberToken {
  constructor(source) {
    this.source = source;
  }
}

const VALIDATED_CONFIGURATION_TOKEN = Symbol("validated-configuration");
const validatedModels = new WeakMap();

class ValidatedConfiguration {
  constructor(model, token) {
    if (token !== VALIDATED_CONFIGURATION_TOKEN) fail("invalid_type");
    validatedModels.set(this, model);
    Object.freeze(this);
  }

  toValue() {
    const model = validatedModels.get(this);
    if (!model) fail("invalid_type");
    return cloneJsonValue(model);
  }
}

function fail(code) {
  throw new FamilyConnectionError(code);
}

class JsonParser {
  constructor(source) {
    this.source = source;
    this.index = 0;
  }

  parse() {
    const value = this.parseValue();
    this.skipWhitespace();
    if (this.index !== this.source.length) fail("invalid_source");
    return value;
  }

  skipWhitespace() {
    while (/[\t\n\r ]/.test(this.source[this.index] || "")) this.index++;
  }

  parseValue() {
    this.skipWhitespace();
    const character = this.source[this.index];
    if (character === "{") return this.parseObject();
    if (character === "[") return this.parseArray();
    if (character === '"') return this.parseString();
    if (character === "t") return this.parseLiteral("true", true);
    if (character === "f") return this.parseLiteral("false", false);
    if (character === "n") return this.parseLiteral("null", null);
    if (character === "-" || (character >= "0" && character <= "9")) return this.parseNumber();
    fail("invalid_source");
  }

  parseLiteral(source, value) {
    if (this.source.slice(this.index, this.index + source.length) !== source) fail("invalid_source");
    this.index += source.length;
    return value;
  }

  parseObject() {
    this.index++;
    const result = Object.create(null);
    const seen = new Set();
    this.skipWhitespace();
    if (this.source[this.index] === "}") {
      this.index++;
      return result;
    }
    while (true) {
      this.skipWhitespace();
      if (this.source[this.index] !== '"') fail("invalid_source");
      const key = this.parseString();
      if (seen.has(key)) fail("duplicate_key");
      seen.add(key);
      this.skipWhitespace();
      if (this.source[this.index] !== ":") fail("invalid_source");
      this.index++;
      result[key] = this.parseValue();
      this.skipWhitespace();
      if (this.source[this.index] === "}") {
        this.index++;
        return result;
      }
      if (this.source[this.index] !== ",") fail("invalid_source");
      this.index++;
    }
  }

  parseArray() {
    this.index++;
    const result = [];
    this.skipWhitespace();
    if (this.source[this.index] === "]") {
      this.index++;
      return result;
    }
    while (true) {
      result.push(this.parseValue());
      this.skipWhitespace();
      if (this.source[this.index] === "]") {
        this.index++;
        return result;
      }
      if (this.source[this.index] !== ",") fail("invalid_source");
      this.index++;
    }
  }

  parseString() {
    this.index++;
    let result = "";
    while (this.index < this.source.length) {
      const character = this.source[this.index++];
      if (character === '"') return result;
      if (character === "\\") {
        result += this.parseEscape();
        continue;
      }
      if (character.charCodeAt(0) <= 0x1f) fail("invalid_source");
      const code = character.charCodeAt(0);
      if (code >= 0xd800 && code <= 0xdbff) {
        const next = this.source.charCodeAt(this.index);
        if (!(next >= 0xdc00 && next <= 0xdfff)) fail("invalid_source");
        result += String.fromCodePoint(0x10000 + ((code - 0xd800) << 10) + (next - 0xdc00));
        this.index++;
        continue;
      }
      if (code >= 0xdc00 && code <= 0xdfff) fail("invalid_source");
      result += character;
    }
    fail("invalid_source");
  }

  parseEscape() {
    const escape = this.source[this.index++];
    switch (escape) {
      case '"':
      case "\\":
      case "/":
        return escape;
      case "b":
        return "\b";
      case "f":
        return "\f";
      case "n":
        return "\n";
      case "r":
        return "\r";
      case "t":
        return "\t";
      case "u":
        return this.parseUnicodeEscape();
      default:
        fail("invalid_source");
    }
  }

  parseHexCodeUnit() {
    const hex = this.source.slice(this.index, this.index + 4);
    if (!/^[0-9a-fA-F]{4}$/.test(hex)) fail("invalid_source");
    this.index += 4;
    return parseInt(hex, 16);
  }

  parseUnicodeEscape() {
    const first = this.parseHexCodeUnit();
    if (first >= 0xd800 && first <= 0xdbff) {
      if (this.source[this.index] !== "\\" || this.source[this.index + 1] !== "u") {
        fail("invalid_source");
      }
      this.index += 2;
      const second = this.parseHexCodeUnit();
      if (second < 0xdc00 || second > 0xdfff) fail("invalid_source");
      return String.fromCodePoint(0x10000 + ((first - 0xd800) << 10) + (second - 0xdc00));
    }
    if (first >= 0xdc00 && first <= 0xdfff) fail("invalid_source");
    return String.fromCharCode(first);
  }

  parseNumber() {
    const start = this.index;
    if (this.source[this.index] === "-") this.index++;
    if (this.source[this.index] === "0") {
      this.index++;
    } else if (this.source[this.index] >= "1" && this.source[this.index] <= "9") {
      while (this.source[this.index] >= "0" && this.source[this.index] <= "9") this.index++;
    } else {
      fail("invalid_source");
    }
    let integer = true;
    if (this.source[this.index] === ".") {
      integer = false;
      this.index++;
      if (!(this.source[this.index] >= "0" && this.source[this.index] <= "9")) fail("invalid_source");
      while (this.source[this.index] >= "0" && this.source[this.index] <= "9") this.index++;
    }
    if (this.source[this.index] === "e" || this.source[this.index] === "E") {
      integer = false;
      this.index++;
      if (this.source[this.index] === "+" || this.source[this.index] === "-") this.index++;
      if (!(this.source[this.index] >= "0" && this.source[this.index] <= "9")) fail("invalid_source");
      while (this.source[this.index] >= "0" && this.source[this.index] <= "9") this.index++;
    }
    const source = this.source.slice(start, this.index);
    return integer ? new IntegerToken(source) : new NumberToken(source);
  }
}

function parseConfigurationSource(source) {
  if (typeof source !== "string") fail("invalid_source");
  return validateConfigurationValue(new JsonParser(source).parse(), true);
}

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function requireClosedObject(value, required, optional) {
  if (!isObject(value) || value instanceof IntegerToken || value instanceof NumberToken) {
    fail("invalid_type");
  }
  for (const field of required) {
    if (!Object.prototype.hasOwnProperty.call(value, field)) fail("missing_field");
  }
  for (const field of Object.keys(value)) {
    if (!required.has(field) && !optional.has(field)) fail("unknown_field");
  }
  return value;
}

function requireName(value) {
  if (typeof value !== "string") fail("invalid_type");
  if (!NAME_RE.test(value)) fail("invalid_name");
  return value;
}

function requireNonemptyString(value) {
  if (typeof value !== "string") fail("invalid_type");
  if (!value) fail("invalid_name");
  return value;
}

function validateResource(value) {
  if (typeof value !== "string") fail("invalid_type");
  const segments = value.split("/");
  if (segments.length === 0 || segments.some(segment => !NAME_RE.test(segment))) {
    fail("invalid_name");
  }
  return segments;
}

function validateRoutes(value, connectionNames) {
  if (!isObject(value) || value instanceof IntegerToken || value instanceof NumberToken) {
    fail("invalid_type");
  }
  const result = Object.create(null);
  for (const [resource, connection] of Object.entries(value)) {
    validateResource(resource);
    if (typeof connection !== "string") fail("invalid_type");
    if (!connectionNames.has(connection)) fail("invalid_reference");
    result[resource] = connection;
  }
  return result;
}

function validateConfiguration(value) {
  assertJsonUnicodeScalars(value);
  return validateConfigurationValue(value, false);
}

function assertJsonUnicodeScalars(value) {
  if (typeof value === "string") {
    for (let index = 0; index < value.length; index++) {
      const code = value.charCodeAt(index);
      if (code >= 0xd800 && code <= 0xdbff) {
        const next = value.charCodeAt(index + 1);
        if (!(next >= 0xdc00 && next <= 0xdfff)) fail("invalid_source");
        index++;
      } else if (code >= 0xdc00 && code <= 0xdfff) {
        fail("invalid_source");
      }
    }
  } else if (Array.isArray(value)) {
    for (const item of value) assertJsonUnicodeScalars(item);
  } else if (isObject(value)) {
    for (const [key, item] of Object.entries(value)) {
      assertJsonUnicodeScalars(key);
      assertJsonUnicodeScalars(item);
    }
  }
}

function validateConfigurationValue(value, sourceTokens) {
  const root = requireClosedObject(
    value,
    new Set(["version", "connections", "contexts"]),
    new Set(["default_context", "defaults"])
  );
  const validVersion = sourceTokens
    ? root.version instanceof IntegerToken && root.version.source === "1"
    : typeof root.version === "number" && Number.isInteger(root.version) && root.version === 1;
  if (!validVersion) {
    fail("invalid_version");
  }

  if (!isObject(root.connections)) fail("invalid_type");
  const connections = Object.create(null);
  for (const [rawName, rawConnection] of Object.entries(root.connections)) {
    const name = requireName(rawName);
    const connection = requireClosedObject(
      rawConnection,
      new Set(["endpoint"]),
      new Set(["credential_ref"])
    );
    const normalized = Object.create(null);
    normalized.endpoint = canonicalizeEndpoint(connection.endpoint);
    if (Object.prototype.hasOwnProperty.call(connection, "credential_ref")) {
      const credential = requireClosedObject(
        connection.credential_ref,
        new Set(["provider", "name"]),
        new Set()
      );
      normalized.credential_ref = Object.assign(Object.create(null), {
        provider: requireName(credential.provider),
        name: requireNonemptyString(credential.name),
      });
    }
    connections[name] = normalized;
  }

  const connectionNames = new Set(Object.keys(connections));
  if (!isObject(root.contexts)) fail("invalid_type");
  const contexts = Object.create(null);
  for (const [rawName, rawContext] of Object.entries(root.contexts)) {
    const name = requireName(rawName);
    const context = requireClosedObject(rawContext, new Set(["routes"]), new Set());
    contexts[name] = Object.assign(Object.create(null), {
      routes: validateRoutes(context.routes, connectionNames),
    });
  }

  const result = Object.assign(Object.create(null), { version: 1, connections, contexts });
  if (Object.prototype.hasOwnProperty.call(root, "default_context")) {
    const defaultContext = requireName(root.default_context);
    if (!Object.prototype.hasOwnProperty.call(contexts, defaultContext)) fail("invalid_reference");
    result.default_context = defaultContext;
  }
  if (Object.prototype.hasOwnProperty.call(root, "defaults")) {
    const defaults = requireClosedObject(root.defaults, new Set(["routes"]), new Set());
    result.defaults = Object.assign(Object.create(null), {
      routes: validateRoutes(defaults.routes, connectionNames),
    });
  }
  freezeJsonValue(result);
  return new ValidatedConfiguration(result, VALIDATED_CONFIGURATION_TOKEN);
}

function cloneJsonValue(value) {
  if (Array.isArray(value)) return value.map(cloneJsonValue);
  if (!isObject(value)) return value;
  const result = Object.create(null);
  for (const [key, item] of Object.entries(value)) result[key] = cloneJsonValue(item);
  return result;
}

function freezeJsonValue(value) {
  if (!isObject(value) && !Array.isArray(value)) return value;
  for (const item of Object.values(value)) freezeJsonValue(item);
  return Object.freeze(value);
}

function assertValidEndpointScalars(value) {
  for (let index = 0; index < value.length; index++) {
    const code = value.charCodeAt(index);
    if (code >= 0xd800 && code <= 0xdbff) {
      const next = value.charCodeAt(index + 1);
      if (!(next >= 0xdc00 && next <= 0xdfff)) fail("invalid_endpoint_characters");
      index++;
      continue;
    }
    if (code >= 0xdc00 && code <= 0xdfff) fail("invalid_endpoint_characters");
    if (value[index] === "\\" || value[index] === " " || code <= 0x1f || code === 0x7f) {
      fail("invalid_endpoint_characters");
    }
  }
}

function parseStrictIpv4(rawHost) {
  if (!IPV4_RE.test(rawHost)) return null;
  const octets = rawHost.split(".").map(value => Number(value));
  if (octets.some(octet => octet > 255)) fail("invalid_endpoint_host");
  return octets;
}

function parseIpv6Part(part) {
  if (!/^[0-9a-fA-F]{1,4}$/.test(part)) fail("invalid_endpoint_host");
  return parseInt(part, 16);
}

function parseIpv6(rawHost) {
  if (!rawHost || rawHost.includes("%")) fail("invalid_endpoint_host");
  if ((rawHost.match(/::/g) || []).length > 1) fail("invalid_endpoint_host");
  if (rawHost.includes(".") && !/(?:^|:)(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*)){3}$/.test(rawHost)) {
    fail("invalid_endpoint_host");
  }

  const hasCompression = rawHost.includes("::");
  const [leftText, rightText = ""] = rawHost.split("::");
  const parseSide = side => {
    if (!side) return [];
    return side.split(":").flatMap((part, index, parts) => {
      if (!part) fail("invalid_endpoint_host");
      if (part.includes(".")) {
        if (index !== parts.length - 1) fail("invalid_endpoint_host");
        const ipv4 = parseStrictIpv4(part);
        if (!ipv4) fail("invalid_endpoint_host");
        return [(ipv4[0] << 8) | ipv4[1], (ipv4[2] << 8) | ipv4[3]];
      }
      return [parseIpv6Part(part)];
    });
  };

  const left = parseSide(leftText);
  const right = parseSide(rightText);
  if (hasCompression) {
    const missing = 8 - left.length - right.length;
    if (missing < 1) fail("invalid_endpoint_host");
    return [...left, ...Array(missing).fill(0), ...right];
  }
  if (left.length !== 8) fail("invalid_endpoint_host");
  return left;
}

function canonicalizeIpv6(groups) {
  let bestStart = -1;
  let bestLength = 0;
  let index = 0;
  while (index < groups.length) {
    if (groups[index] !== 0) {
      index++;
      continue;
    }
    let end = index;
    while (end < groups.length && groups[end] === 0) end++;
    const length = end - index;
    if (length >= 2 && length > bestLength) {
      bestStart = index;
      bestLength = length;
    }
    index = end;
  }
  const rendered = groups.map(group => group.toString(16));
  if (bestStart < 0) return rendered.join(":");
  const left = rendered.slice(0, bestStart).join(":");
  const right = rendered.slice(bestStart + bestLength).join(":");
  if (left && right) return `${left}::${right}`;
  if (left) return `${left}::`;
  if (right) return `::${right}`;
  return "::";
}

function ipv6IsLoopback(groups) {
  return groups.slice(0, 7).every(group => group === 0) && groups[7] === 1;
}

function domainToAscii(host) {
  const value = tr46.toASCII(host, {
    checkBidi: true,
    checkHyphens: true,
    checkJoiners: true,
    ignoreInvalidPunycode: false,
    transitionalProcessing: false,
    useSTD3ASCIIRules: true,
    verifyDNSLength: true,
  });
  return value || "";
}

function canonicalizeHost(rawHost, bracketed) {
  if (!rawHost || rawHost.includes("%")) fail("invalid_endpoint_host");
  if (bracketed) {
    const groups = parseIpv6(rawHost);
    return {
      canonical: `[${canonicalizeIpv6(groups)}]`,
      kind: "ipv6",
      value: groups,
    };
  }

  const ipv4 = parseStrictIpv4(rawHost);
  if (ipv4) {
    return { canonical: ipv4.join("."), kind: "ipv4", value: ipv4 };
  }
  if (IPV4_LIKE_RE.test(rawHost)) fail("invalid_endpoint_host");

  const asciiHost = domainToAscii(rawHost);
  if (!asciiHost || asciiHost.endsWith(".")) fail("invalid_endpoint_host");
  const labels = asciiHost.toLowerCase().split(".");
  if (
    labels.some(
      label =>
        !label ||
        label.length > 63 ||
        !/^[a-z0-9-]+$/.test(label) ||
        label.startsWith("-") ||
        label.endsWith("-")
    )
  ) {
    fail("invalid_endpoint_host");
  }
  const canonical = labels.join(".");
  if (canonical.length > 253) fail("invalid_endpoint_host");
  return { canonical, kind: "registered", value: canonical };
}

function normalizePath(rawPath) {
  const output = [];
  for (let index = 0; index < rawPath.length; ) {
    const code = rawPath.codePointAt(index);
    const character = String.fromCodePoint(code);
    if (code > 0x7f) fail("invalid_endpoint_path");
    if (character === "%") {
      const hex = rawPath.slice(index + 1, index + 3);
      if (!/^[0-9a-fA-F]{2}$/.test(hex)) fail("invalid_endpoint_path");
      const octet = parseInt(hex, 16);
      if (octet >= 0x80 || octet <= 0x1f || octet === 0x7f || octet === 0x2f || octet === 0x5c) {
        fail("invalid_endpoint_path");
      }
      const decoded = String.fromCharCode(octet);
      output.push(UNRESERVED.has(decoded) ? decoded : `%${octet.toString(16).toUpperCase().padStart(2, "0")}`);
      index += 3;
      continue;
    }
    if (character !== "/" && !PCHAR.has(character)) fail("invalid_endpoint_path");
    output.push(character);
    index += character.length;
  }
  return removeDotSegments(output.join(""));
}

function removeLastSegment(path) {
  const slash = path.lastIndexOf("/");
  return slash < 0 ? "" : path.slice(0, slash);
}

function removeDotSegments(path) {
  let source = path;
  let output = "";
  while (source) {
    if (source.startsWith("../")) source = source.slice(3);
    else if (source.startsWith("./")) source = source.slice(2);
    else if (source.startsWith("/./")) source = "/" + source.slice(3);
    else if (source === "/.") source = "/";
    else if (source.startsWith("/../")) {
      source = "/" + source.slice(4);
      output = removeLastSegment(output);
    } else if (source === "/..") {
      source = "/";
      output = removeLastSegment(output);
    } else if (source === "." || source === "..") source = "";
    else {
      const start = source.startsWith("/") ? 1 : 0;
      const slash = source.indexOf("/", start);
      if (slash < 0) {
        output += source;
        source = "";
      } else {
        output += source.slice(0, slash);
        source = source.slice(slash);
      }
    }
  }
  return output;
}

function canonicalizeEndpoint(value) {
  if (typeof value !== "string") fail("invalid_endpoint_type");
  if (!value) fail("invalid_endpoint_syntax");
  assertValidEndpointScalars(value);
  const match = ENDPOINT_RE.exec(value);
  if (!match) fail("invalid_endpoint_syntax");
  let [, scheme, authority, rawPath] = match;
  scheme = scheme.toLowerCase();
  if (scheme !== "http" && scheme !== "https") fail("unsupported_endpoint_scheme");
  if (!authority || authority.includes("@")) fail("invalid_endpoint_authority");

  const bracketed = authority.startsWith("[");
  let rawHost;
  let rawPort = null;
  if (bracketed) {
    const close = authority.indexOf("]");
    if (close < 0) fail("invalid_endpoint_authority");
    rawHost = authority.slice(1, close);
    const remainder = authority.slice(close + 1);
    if (remainder) {
      if (!remainder.startsWith(":")) fail("invalid_endpoint_authority");
      rawPort = remainder.slice(1);
    }
  } else {
    if (authority.includes("[") || authority.includes("]") || (authority.match(/:/g) || []).length > 1) {
      fail("invalid_endpoint_authority");
    }
    if (authority.includes(":")) {
      const split = authority.lastIndexOf(":");
      rawHost = authority.slice(0, split);
      rawPort = authority.slice(split + 1);
    } else {
      rawHost = authority;
    }
  }

  const host = canonicalizeHost(rawHost, bracketed);
  let canonicalPort = "";
  if (rawPort !== null) {
    if (!/^[1-9][0-9]*$/.test(rawPort)) fail("invalid_endpoint_port");
    const port = Number(rawPort);
    if (port > 65535) fail("invalid_endpoint_port");
    if (!((scheme === "https" && port === 443) || (scheme === "http" && port === 80))) {
      canonicalPort = `:${port}`;
    }
  }

  let path = normalizePath(rawPath);
  if (!path) path = "/";
  else if (path !== "/") path = path.replace(/\/+$/u, "") || "/";

  if (scheme === "http") {
    const loopback =
      (host.kind === "registered" && host.value === "localhost") ||
      (host.kind === "ipv4" && host.value[0] === 127) ||
      (host.kind === "ipv6" && ipv6IsLoopback(host.value));
    if (!loopback) fail("insecure_endpoint");
  }
  return `${scheme}://${host.canonical}${canonicalPort}${path}`;
}

function environmentName(resource) {
  const segments = validateResource(resource);
  const encode = segment =>
    [...segment].map(character => (character === "-" ? "_H" : character.toUpperCase())).join("");
  return `DETERMA_${segments.map(encode).join("__")}_CONNECTION`;
}

function routeKeys(resource) {
  const product = resource.split("/", 1)[0];
  return product === resource ? [resource] : [resource, product];
}

function firstRoute(routes, resource) {
  for (const key of routeKeys(resource)) {
    if (Object.prototype.hasOwnProperty.call(routes, key)) return routes[key];
  }
  return null;
}

function resolveConnection(configuration, request) {
  const model = validatedModels.get(configuration);
  if (!model) fail("invalid_type");
  request = requireClosedObject(
    request,
    new Set(["resource"]),
    new Set(["explicit_connection", "environment", "selected_context"])
  );
  const resource = request.resource;
  validateResource(resource);
  const connections = model.connections;

  if (Object.prototype.hasOwnProperty.call(request, "explicit_connection")) {
    const explicit = request.explicit_connection;
    if (typeof explicit !== "string" || !Object.prototype.hasOwnProperty.call(connections, explicit)) {
      fail("invalid_connection");
    }
    return explicit;
  }

  const environment = Object.prototype.hasOwnProperty.call(request, "environment") ? request.environment : {};
  if (
    !isObject(environment) ||
    Object.entries(environment).some(([key, value]) => typeof key !== "string" || typeof value !== "string")
  ) {
    fail("invalid_environment");
  }
  const environmentKeys = [environmentName(resource)];
  const productKey = environmentName(resource.split("/", 1)[0]);
  if (!environmentKeys.includes(productKey)) environmentKeys.push(productKey);
  environmentKeys.push("DETERMA_CONNECTION");
  for (const key of environmentKeys) {
    if (Object.prototype.hasOwnProperty.call(environment, key)) {
      const connection = environment[key];
      if (!connection || !Object.prototype.hasOwnProperty.call(connections, connection)) fail("invalid_connection");
      return connection;
    }
  }

  if (Object.prototype.hasOwnProperty.call(request, "selected_context")) {
    const selected = request.selected_context;
    if (typeof selected !== "string" || !Object.prototype.hasOwnProperty.call(model.contexts, selected)) {
      fail("invalid_context");
    }
    const connection = firstRoute(model.contexts[selected].routes, resource);
    if (connection !== null) return connection;
  }

  const defaults = model.defaults || { routes: {} };
  const defaultConnection = firstRoute(defaults.routes, resource);
  if (defaultConnection !== null) return defaultConnection;

  const defaultContext = model.default_context;
  if (defaultContext !== undefined) {
    const connection = firstRoute(model.contexts[defaultContext].routes, resource);
    if (connection !== null) return connection;
  }
  fail("unresolved_connection");
}

module.exports = {
  FamilyConnectionError,
  RESERVED_FAMILY_COMMANDS,
  ValidatedConfiguration,
  canonicalizeEndpoint,
  environmentName,
  parseConfigurationSource,
  resolveConnection,
  validateConfiguration,
  validateResource,
};
