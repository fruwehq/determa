use std::collections::{BTreeMap, BTreeSet};
use std::fmt;
use std::net::{Ipv4Addr, Ipv6Addr};
use std::str::FromStr;

use idna::uts46::{AsciiDenyList, DnsLength, Hyphens, Uts46};
use serde::de::{self, MapAccess, SeqAccess, Visitor};
use serde::Deserialize;
use serde_json::{json, Map, Value};

pub const RESERVED_FAMILY_COMMANDS: &[&str] = &["auth", "config", "context"];

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FamilyConnectionError {
    pub code: &'static str,
}

impl FamilyConnectionError {
    fn new(code: &'static str) -> Self {
        Self { code }
    }
}

impl fmt::Display for FamilyConnectionError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.code)
    }
}

impl std::error::Error for FamilyConnectionError {}

type Result<T> = std::result::Result<T, FamilyConnectionError>;

#[derive(Debug, Clone)]
enum JsonValue {
    Null,
    Bool,
    Integer(String),
    Number,
    String(String),
    Array,
    Object(BTreeMap<String, JsonValue>),
}

struct JsonValueVisitor;

impl<'de> Visitor<'de> for JsonValueVisitor {
    type Value = JsonValue;

    fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("a JSON value")
    }

    fn visit_bool<E>(self, _value: bool) -> std::result::Result<Self::Value, E> {
        Ok(JsonValue::Bool)
    }

    fn visit_i64<E>(self, value: i64) -> std::result::Result<Self::Value, E> {
        Ok(JsonValue::Integer(value.to_string()))
    }

    fn visit_u64<E>(self, value: u64) -> std::result::Result<Self::Value, E> {
        Ok(JsonValue::Integer(value.to_string()))
    }

    fn visit_f64<E>(self, _value: f64) -> std::result::Result<Self::Value, E> {
        Ok(JsonValue::Number)
    }

    fn visit_str<E>(self, value: &str) -> std::result::Result<Self::Value, E>
    where
        E: de::Error,
    {
        Ok(JsonValue::String(value.to_string()))
    }

    fn visit_string<E>(self, value: String) -> std::result::Result<Self::Value, E> {
        Ok(JsonValue::String(value))
    }

    fn visit_none<E>(self) -> std::result::Result<Self::Value, E> {
        Ok(JsonValue::Null)
    }

    fn visit_unit<E>(self) -> std::result::Result<Self::Value, E> {
        Ok(JsonValue::Null)
    }

    fn visit_seq<A>(self, mut sequence: A) -> std::result::Result<Self::Value, A::Error>
    where
        A: SeqAccess<'de>,
    {
        while sequence.next_element::<JsonValue>()?.is_some() {}
        Ok(JsonValue::Array)
    }

    fn visit_map<A>(self, mut map: A) -> std::result::Result<Self::Value, A::Error>
    where
        A: MapAccess<'de>,
    {
        let mut result = BTreeMap::new();
        while let Some(key) = map.next_key::<String>()? {
            if result.contains_key(&key) {
                return Err(de::Error::custom("duplicate_key"));
            }
            let value = map.next_value::<JsonValue>()?;
            result.insert(key, value);
        }
        Ok(JsonValue::Object(result))
    }
}

impl<'de> Deserialize<'de> for JsonValue {
    fn deserialize<D>(deserializer: D) -> std::result::Result<Self, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        deserializer.deserialize_any(JsonValueVisitor)
    }
}

pub fn parse_configuration_source(source: &str) -> Result<Value> {
    let parsed = serde_json::from_str::<JsonValue>(source).map_err(|error| {
        if error.to_string().contains("duplicate_key") {
            FamilyConnectionError::new("duplicate_key")
        } else {
            FamilyConnectionError::new("invalid_source")
        }
    })?;
    validate_configuration(&parsed)
}

fn object<'a>(
    value: &'a JsonValue,
    required: &[&str],
    optional: &[&str],
) -> Result<&'a BTreeMap<String, JsonValue>> {
    let JsonValue::Object(map) = value else {
        return Err(FamilyConnectionError::new("invalid_type"));
    };
    for field in required {
        if !map.contains_key(*field) {
            return Err(FamilyConnectionError::new("missing_field"));
        }
    }
    for field in map.keys() {
        if !required.contains(&field.as_str()) && !optional.contains(&field.as_str()) {
            return Err(FamilyConnectionError::new("unknown_field"));
        }
    }
    Ok(map)
}

fn name_from_json(value: &JsonValue) -> Result<String> {
    let JsonValue::String(value) = value else {
        return Err(FamilyConnectionError::new("invalid_type"));
    };
    require_name(value)
}

fn require_name(value: &str) -> Result<String> {
    if valid_name(value) {
        Ok(value.to_string())
    } else {
        Err(FamilyConnectionError::new("invalid_name"))
    }
}

fn require_nonempty_string(value: &JsonValue) -> Result<String> {
    let JsonValue::String(value) = value else {
        return Err(FamilyConnectionError::new("invalid_type"));
    };
    if value.is_empty() {
        Err(FamilyConnectionError::new("invalid_name"))
    } else {
        Ok(value.to_string())
    }
}

fn valid_name(value: &str) -> bool {
    let mut chars = value.chars();
    let Some(first) = chars.next() else {
        return false;
    };
    if !first.is_ascii_lowercase() {
        return false;
    }
    chars.all(|character| {
        character.is_ascii_lowercase() || character.is_ascii_digit() || character == '-'
    })
}

fn validate_routes(
    value: &JsonValue,
    connection_names: &BTreeSet<String>,
) -> Result<Map<String, Value>> {
    let JsonValue::Object(routes) = value else {
        return Err(FamilyConnectionError::new("invalid_type"));
    };
    let mut result = Map::new();
    for (resource, connection) in routes {
        validate_resource(resource)?;
        let JsonValue::String(connection) = connection else {
            return Err(FamilyConnectionError::new("invalid_type"));
        };
        if !connection_names.contains(connection) {
            return Err(FamilyConnectionError::new("invalid_reference"));
        }
        result.insert(resource.clone(), Value::String(connection.clone()));
    }
    Ok(result)
}

fn validate_configuration(value: &JsonValue) -> Result<Value> {
    let root = object(
        value,
        &["version", "connections", "contexts"],
        &["default_context", "defaults"],
    )?;
    match root.get("version") {
        Some(JsonValue::Integer(source)) if source == "1" => {}
        _ => return Err(FamilyConnectionError::new("invalid_version")),
    }

    let JsonValue::Object(raw_connections) = root.get("connections").expect("required") else {
        return Err(FamilyConnectionError::new("invalid_type"));
    };
    let mut connections = Map::new();
    for (raw_name, raw_connection) in raw_connections {
        let name = require_name(raw_name)?;
        let connection = object(raw_connection, &["endpoint"], &["credential_ref"])?;
        let endpoint = canonicalize_endpoint_json(connection.get("endpoint").expect("required"))?;
        let mut normalized = Map::new();
        normalized.insert("endpoint".to_string(), Value::String(endpoint));
        if let Some(credential) = connection.get("credential_ref") {
            let credential = object(credential, &["provider", "name"], &[])?;
            normalized.insert(
                "credential_ref".to_string(),
                json!({
                    "provider": name_from_json(credential.get("provider").expect("required"))?,
                    "name": require_nonempty_string(credential.get("name").expect("required"))?,
                }),
            );
        }
        connections.insert(name, Value::Object(normalized));
    }

    let connection_names: BTreeSet<String> = connections.keys().cloned().collect();
    let JsonValue::Object(raw_contexts) = root.get("contexts").expect("required") else {
        return Err(FamilyConnectionError::new("invalid_type"));
    };
    let mut contexts = Map::new();
    for (raw_name, raw_context) in raw_contexts {
        let name = require_name(raw_name)?;
        let context = object(raw_context, &["routes"], &[])?;
        contexts.insert(
            name,
            json!({ "routes": validate_routes(context.get("routes").expect("required"), &connection_names)? }),
        );
    }

    let mut normalized = Map::new();
    normalized.insert("version".to_string(), Value::Number(1.into()));
    normalized.insert("connections".to_string(), Value::Object(connections));
    normalized.insert("contexts".to_string(), Value::Object(contexts.clone()));
    if let Some(default_context) = root.get("default_context") {
        let default_context = name_from_json(default_context)?;
        if !contexts.contains_key(&default_context) {
            return Err(FamilyConnectionError::new("invalid_reference"));
        }
        normalized.insert(
            "default_context".to_string(),
            Value::String(default_context),
        );
    }
    if let Some(defaults) = root.get("defaults") {
        let defaults = object(defaults, &["routes"], &[])?;
        normalized.insert(
            "defaults".to_string(),
            json!({ "routes": validate_routes(defaults.get("routes").expect("required"), &connection_names)? }),
        );
    }
    Ok(Value::Object(normalized))
}

pub fn validate_resource(value: &str) -> Result<Vec<&str>> {
    let segments: Vec<&str> = value.split('/').collect();
    if segments.is_empty() || segments.iter().any(|segment| !valid_name(segment)) {
        return Err(FamilyConnectionError::new("invalid_name"));
    }
    Ok(segments)
}

pub fn canonicalize_endpoint_value(value: &Value) -> Result<String> {
    let Some(value) = value.as_str() else {
        return Err(FamilyConnectionError::new("invalid_endpoint_type"));
    };
    canonicalize_endpoint(value)
}

fn canonicalize_endpoint_json(value: &JsonValue) -> Result<String> {
    let JsonValue::String(value) = value else {
        return Err(FamilyConnectionError::new("invalid_endpoint_type"));
    };
    canonicalize_endpoint(value)
}

pub fn canonicalize_endpoint(value: &str) -> Result<String> {
    if value.is_empty() {
        return Err(FamilyConnectionError::new("invalid_endpoint_syntax"));
    }
    for character in value.chars() {
        if character == '\\' || character == ' ' || character <= '\u{1f}' || character == '\u{7f}' {
            return Err(FamilyConnectionError::new("invalid_endpoint_characters"));
        }
    }
    let scheme_end = value
        .find("://")
        .ok_or_else(|| FamilyConnectionError::new("invalid_endpoint_syntax"))?;
    let mut scheme = value[..scheme_end].to_ascii_lowercase();
    if !valid_scheme(&scheme) {
        return Err(FamilyConnectionError::new("invalid_endpoint_syntax"));
    }
    if scheme != "http" && scheme != "https" {
        return Err(FamilyConnectionError::new("unsupported_endpoint_scheme"));
    }
    let after_scheme = &value[scheme_end + 3..];
    if after_scheme.contains('?') || after_scheme.contains('#') {
        return Err(FamilyConnectionError::new("invalid_endpoint_syntax"));
    }
    let slash = after_scheme.find('/');
    let (authority, raw_path) = match slash {
        Some(index) => (&after_scheme[..index], &after_scheme[index..]),
        None => (after_scheme, ""),
    };
    if authority.is_empty() || authority.contains('@') {
        return Err(FamilyConnectionError::new("invalid_endpoint_authority"));
    }

    let (raw_host, raw_port, bracketed) = split_authority(authority)?;
    let (canonical_host, host_kind) = canonicalize_host(raw_host, bracketed)?;
    let canonical_port = match raw_port {
        Some(raw_port) => {
            if raw_port.is_empty()
                || raw_port.starts_with('0')
                || !raw_port.chars().all(|character| character.is_ascii_digit())
            {
                return Err(FamilyConnectionError::new("invalid_endpoint_port"));
            }
            let port: u32 = raw_port
                .parse()
                .map_err(|_| FamilyConnectionError::new("invalid_endpoint_port"))?;
            if port == 0 || port > 65535 {
                return Err(FamilyConnectionError::new("invalid_endpoint_port"));
            }
            if (scheme == "https" && port == 443) || (scheme == "http" && port == 80) {
                String::new()
            } else {
                format!(":{port}")
            }
        }
        None => String::new(),
    };

    let mut path = normalize_path(raw_path)?;
    if path.is_empty() {
        path = "/".to_string();
    } else if path != "/" {
        while path.ends_with('/') {
            path.pop();
        }
        if path.is_empty() {
            path = "/".to_string();
        }
    }

    if scheme == "http" && !host_kind.is_loopback() {
        return Err(FamilyConnectionError::new("insecure_endpoint"));
    }
    scheme.push_str("://");
    Ok(format!("{scheme}{canonical_host}{canonical_port}{path}"))
}

fn valid_scheme(value: &str) -> bool {
    let mut chars = value.chars();
    let Some(first) = chars.next() else {
        return false;
    };
    first.is_ascii_alphabetic()
        && chars.all(|character| {
            character.is_ascii_alphanumeric() || matches!(character, '+' | '.' | '-')
        })
}

fn split_authority(authority: &str) -> Result<(&str, Option<&str>, bool)> {
    if authority.starts_with('[') {
        let close = authority
            .find(']')
            .ok_or_else(|| FamilyConnectionError::new("invalid_endpoint_authority"))?;
        let raw_host = &authority[1..close];
        let remainder = &authority[close + 1..];
        if remainder.is_empty() {
            return Ok((raw_host, None, true));
        }
        if let Some(raw_port) = remainder.strip_prefix(':') {
            return Ok((raw_host, Some(raw_port), true));
        }
        return Err(FamilyConnectionError::new("invalid_endpoint_authority"));
    }
    if authority.contains('[') || authority.contains(']') || authority.matches(':').count() > 1 {
        return Err(FamilyConnectionError::new("invalid_endpoint_authority"));
    }
    if let Some(split) = authority.rfind(':') {
        Ok((&authority[..split], Some(&authority[split + 1..]), false))
    } else {
        Ok((authority, None, false))
    }
}

enum HostKind {
    Registered(String),
    Ipv4(Ipv4Addr),
    Ipv6(Ipv6Addr),
}

impl HostKind {
    fn is_loopback(&self) -> bool {
        match self {
            HostKind::Registered(host) => host == "localhost",
            HostKind::Ipv4(address) => address.is_loopback(),
            HostKind::Ipv6(address) => *address == Ipv6Addr::LOCALHOST,
        }
    }
}

fn canonicalize_host(raw_host: &str, bracketed: bool) -> Result<(String, HostKind)> {
    if raw_host.is_empty() || raw_host.contains('%') {
        return Err(FamilyConnectionError::new("invalid_endpoint_host"));
    }
    if bracketed {
        let address = Ipv6Addr::from_str(raw_host)
            .map_err(|_| FamilyConnectionError::new("invalid_endpoint_host"))?;
        return Ok((
            format!("[{}]", canonicalize_ipv6(address)),
            HostKind::Ipv6(address),
        ));
    }

    if is_strict_ipv4(raw_host) {
        let octets = parse_ipv4_octets(raw_host)?;
        let address = Ipv4Addr::new(octets[0], octets[1], octets[2], octets[3]);
        return Ok((address.to_string(), HostKind::Ipv4(address)));
    }
    if is_ipv4_like(raw_host) {
        return Err(FamilyConnectionError::new("invalid_endpoint_host"));
    }

    let ascii_host = domain_to_ascii(raw_host)?;
    if ascii_host.is_empty() || ascii_host.ends_with('.') {
        return Err(FamilyConnectionError::new("invalid_endpoint_host"));
    }
    let labels: Vec<String> = ascii_host
        .split('.')
        .map(|label| label.to_ascii_lowercase())
        .collect();
    if labels.iter().any(|label| {
        label.is_empty()
            || label.len() > 63
            || label.starts_with('-')
            || label.ends_with('-')
            || !label.chars().all(|character| {
                character.is_ascii_lowercase() || character.is_ascii_digit() || character == '-'
            })
    }) {
        return Err(FamilyConnectionError::new("invalid_endpoint_host"));
    }
    let canonical = labels.join(".");
    if canonical.len() > 253 {
        return Err(FamilyConnectionError::new("invalid_endpoint_host"));
    }
    Ok((canonical.clone(), HostKind::Registered(canonical)))
}

fn domain_to_ascii(host: &str) -> Result<String> {
    let ascii = Uts46::new()
        .to_ascii(
            host.as_bytes(),
            AsciiDenyList::STD3,
            Hyphens::Check,
            DnsLength::Verify,
        )
        .map_err(|_| FamilyConnectionError::new("invalid_endpoint_host"))?;
    Ok(ascii.into_owned())
}

fn is_strict_ipv4(raw_host: &str) -> bool {
    let parts: Vec<&str> = raw_host.split('.').collect();
    parts.len() == 4
        && parts.iter().all(|part| {
            let mut chars = part.chars();
            let Some(first) = chars.next() else {
                return false;
            };
            *part == "0"
                || (('1'..='9').contains(&first)
                    && chars.all(|character| character.is_ascii_digit()))
        })
}

fn parse_ipv4_octets(raw_host: &str) -> Result<[u8; 4]> {
    let mut octets = [0_u8; 4];
    for (index, part) in raw_host.split('.').enumerate() {
        octets[index] = part
            .parse::<u8>()
            .map_err(|_| FamilyConnectionError::new("invalid_endpoint_host"))?;
    }
    Ok(octets)
}

fn is_ipv4_like(raw_host: &str) -> bool {
    let parts: Vec<&str> = raw_host.split('.').collect();
    !parts.is_empty()
        && parts.iter().all(|part| {
            if part.is_empty() {
                return false;
            }
            let lower = part.to_ascii_lowercase();
            if let Some(hex) = lower.strip_prefix("0x") {
                !hex.is_empty() && hex.chars().all(|character| character.is_ascii_hexdigit())
            } else {
                part.chars().all(|character| character.is_ascii_digit())
            }
        })
}

fn canonicalize_ipv6(address: Ipv6Addr) -> String {
    let groups = address.segments();
    let mut best_start = None;
    let mut best_length = 0_usize;
    let mut index = 0_usize;
    while index < groups.len() {
        if groups[index] != 0 {
            index += 1;
            continue;
        }
        let start = index;
        while index < groups.len() && groups[index] == 0 {
            index += 1;
        }
        let length = index - start;
        if length >= 2 && length > best_length {
            best_start = Some(start);
            best_length = length;
        }
    }
    let rendered: Vec<String> = groups.iter().map(|group| format!("{group:x}")).collect();
    let Some(start) = best_start else {
        return rendered.join(":");
    };
    let left = rendered[..start].join(":");
    let right = rendered[start + best_length..].join(":");
    match (left.is_empty(), right.is_empty()) {
        (false, false) => format!("{left}::{right}"),
        (false, true) => format!("{left}::"),
        (true, false) => format!("::{right}"),
        (true, true) => "::".to_string(),
    }
}

fn normalize_path(raw_path: &str) -> Result<String> {
    let mut output = String::new();
    let mut index = 0_usize;
    let bytes = raw_path.as_bytes();
    while index < bytes.len() {
        let byte = bytes[index];
        if byte > 0x7f {
            return Err(FamilyConnectionError::new("invalid_endpoint_path"));
        }
        if byte == b'%' {
            if index + 2 >= bytes.len() || !is_hex(bytes[index + 1]) || !is_hex(bytes[index + 2]) {
                return Err(FamilyConnectionError::new("invalid_endpoint_path"));
            }
            let octet = hex_value(bytes[index + 1]) * 16 + hex_value(bytes[index + 2]);
            if octet >= 0x80 || octet <= 0x1f || matches!(octet, 0x7f | b'/' | b'\\') {
                return Err(FamilyConnectionError::new("invalid_endpoint_path"));
            }
            let decoded = char::from(octet);
            if is_unreserved(decoded) {
                output.push(decoded);
            } else {
                output.push_str(&format!("%{octet:02X}"));
            }
            index += 3;
            continue;
        }
        let character = char::from(byte);
        if character != '/' && !is_pchar(character) {
            return Err(FamilyConnectionError::new("invalid_endpoint_path"));
        }
        output.push(character);
        index += 1;
    }
    Ok(remove_dot_segments(&output))
}

fn is_hex(byte: u8) -> bool {
    byte.is_ascii_hexdigit()
}

fn hex_value(byte: u8) -> u8 {
    match byte {
        b'0'..=b'9' => byte - b'0',
        b'a'..=b'f' => byte - b'a' + 10,
        b'A'..=b'F' => byte - b'A' + 10,
        _ => unreachable!(),
    }
}

fn is_unreserved(character: char) -> bool {
    character.is_ascii_alphanumeric() || matches!(character, '-' | '.' | '_' | '~')
}

fn is_pchar(character: char) -> bool {
    is_unreserved(character)
        || matches!(
            character,
            '!' | '$' | '&' | '\'' | '(' | ')' | '*' | '+' | ',' | ';' | '=' | ':' | '@'
        )
}

fn remove_last_segment(path: &str) -> String {
    path.rfind('/')
        .map_or_else(String::new, |slash| path[..slash].to_string())
}

fn remove_dot_segments(path: &str) -> String {
    let mut source = path.to_string();
    let mut output = String::new();
    while !source.is_empty() {
        if source.starts_with("../") {
            source = source[3..].to_string();
        } else if source.starts_with("./") {
            source = source[2..].to_string();
        } else if source.starts_with("/./") {
            source = format!("/{}", &source[3..]);
        } else if source == "/." {
            source = "/".to_string();
        } else if source.starts_with("/../") {
            source = format!("/{}", &source[4..]);
            output = remove_last_segment(&output);
        } else if source == "/.." {
            source = "/".to_string();
            output = remove_last_segment(&output);
        } else if source == "." || source == ".." {
            source.clear();
        } else {
            let start = usize::from(source.starts_with('/'));
            if let Some(relative_slash) = source[start..].find('/') {
                let slash = start + relative_slash;
                output.push_str(&source[..slash]);
                source = source[slash..].to_string();
            } else {
                output.push_str(&source);
                source.clear();
            }
        }
    }
    output
}

pub fn environment_name(resource: &str) -> Result<String> {
    let segments = validate_resource(resource)?;
    let encoded: Vec<String> = segments
        .iter()
        .map(|segment| {
            segment
                .chars()
                .map(|character| {
                    if character == '-' {
                        "_H".to_string()
                    } else {
                        character.to_ascii_uppercase().to_string()
                    }
                })
                .collect()
        })
        .collect();
    Ok(format!("DETERMA_{}_CONNECTION", encoded.join("__")))
}

pub fn environment_name_value(resource: &Value) -> Result<String> {
    let Some(resource) = resource.as_str() else {
        return Err(FamilyConnectionError::new("invalid_type"));
    };
    environment_name(resource)
}

fn route_keys(resource: &str) -> Vec<&str> {
    let product = resource
        .split_once('/')
        .map_or(resource, |(product, _)| product);
    if product == resource {
        vec![resource]
    } else {
        vec![resource, product]
    }
}

fn first_route(routes: &Map<String, Value>, resource: &str) -> Option<String> {
    route_keys(resource)
        .into_iter()
        .find_map(|key| routes.get(key).and_then(Value::as_str).map(str::to_string))
}

pub fn resolve_connection(configuration: &Value, request: &Value) -> Result<String> {
    let request = request
        .as_object()
        .ok_or_else(|| FamilyConnectionError::new("invalid_type"))?;
    let resource = request
        .get("resource")
        .and_then(Value::as_str)
        .ok_or_else(|| FamilyConnectionError::new("invalid_type"))?;
    validate_resource(resource)?;
    let connections = configuration
        .get("connections")
        .and_then(Value::as_object)
        .ok_or_else(|| FamilyConnectionError::new("invalid_type"))?;

    if let Some(explicit) = request.get("explicit_connection") {
        let Some(explicit) = explicit.as_str() else {
            return Err(FamilyConnectionError::new("invalid_connection"));
        };
        if !connections.contains_key(explicit) {
            return Err(FamilyConnectionError::new("invalid_connection"));
        }
        return Ok(explicit.to_string());
    }

    let empty_environment = Map::new();
    let environment = match request.get("environment") {
        Some(Value::Object(environment)) => environment,
        Some(_) => return Err(FamilyConnectionError::new("invalid_environment")),
        None => &empty_environment,
    };
    if environment.values().any(|value| !value.is_string()) {
        return Err(FamilyConnectionError::new("invalid_environment"));
    }
    let mut environment_keys = vec![environment_name(resource)?];
    let product = resource
        .split_once('/')
        .map_or(resource, |(product, _)| product);
    let product_key = environment_name(product)?;
    if !environment_keys.contains(&product_key) {
        environment_keys.push(product_key);
    }
    environment_keys.push("DETERMA_CONNECTION".to_string());
    for key in environment_keys {
        if let Some(connection) = environment.get(&key) {
            let connection = connection.as_str().expect("checked");
            if connection.is_empty() || !connections.contains_key(connection) {
                return Err(FamilyConnectionError::new("invalid_connection"));
            }
            return Ok(connection.to_string());
        }
    }

    let contexts = configuration
        .get("contexts")
        .and_then(Value::as_object)
        .ok_or_else(|| FamilyConnectionError::new("invalid_type"))?;
    if let Some(selected) = request.get("selected_context") {
        let Some(selected) = selected.as_str() else {
            return Err(FamilyConnectionError::new("invalid_context"));
        };
        let Some(context) = contexts.get(selected).and_then(Value::as_object) else {
            return Err(FamilyConnectionError::new("invalid_context"));
        };
        if let Some(connection) = first_route(
            context
                .get("routes")
                .and_then(Value::as_object)
                .expect("normalized"),
            resource,
        ) {
            return Ok(connection);
        }
    }

    if let Some(connection) = configuration
        .get("defaults")
        .and_then(|defaults| defaults.get("routes"))
        .and_then(Value::as_object)
        .and_then(|routes| first_route(routes, resource))
    {
        return Ok(connection);
    }

    if let Some(default_context) = configuration.get("default_context").and_then(Value::as_str) {
        if let Some(connection) = contexts
            .get(default_context)
            .and_then(|context| context.get("routes"))
            .and_then(Value::as_object)
            .and_then(|routes| first_route(routes, resource))
        {
            return Ok(connection);
        }
    }
    Err(FamilyConnectionError::new("unresolved_connection"))
}
