use std::fs;
use std::path::PathBuf;

use determa::family_connection_context_v1 as family;
use serde_json::Value;

fn vector_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .join("conformance")
        .join("family-connection-v1")
}

fn load_fixture(name: &str) -> Value {
    let text = fs::read_to_string(vector_root().join(name)).unwrap();
    serde_json::from_str(&text).unwrap()
}

fn assert_case<F>(case: &Value, operation: F)
where
    F: FnOnce() -> Result<Value, family::FamilyConnectionError>,
{
    let expected = case.get("expect").unwrap();
    if let Some(error) = expected.get("error").and_then(Value::as_str) {
        let actual = operation().unwrap_err();
        assert_eq!(actual.code, error, "{}", case["id"]);
    } else {
        assert_eq!(operation().unwrap(), expected["value"], "{}", case["id"]);
    }
}

#[test]
fn configuration_vectors() {
    for case in load_fixture("configuration.json")["cases"]
        .as_array()
        .unwrap()
    {
        assert_case(case, || {
            let source = case["source"].as_str().unwrap();
            family::parse_configuration_source(source)
        });
    }
}

#[test]
fn endpoint_vectors() {
    for case in load_fixture("endpoints.json")["cases"].as_array().unwrap() {
        assert_case(case, || {
            family::canonicalize_endpoint_value(&case["input"]).map(Value::String)
        });
    }
}

#[test]
fn environment_vectors() {
    let fixture = load_fixture("environment.json");
    let mut results = std::collections::BTreeMap::new();
    for case in fixture["cases"].as_array().unwrap() {
        assert_case(case, || {
            family::environment_name_value(&case["resource"]).map(Value::String)
        });
        if case["expect"].get("value").is_some() {
            results.insert(
                case["id"].as_str().unwrap().to_string(),
                case["expect"]["value"].as_str().unwrap().to_string(),
            );
        }
    }
    for distinct_set in fixture["distinct_sets"].as_array().unwrap() {
        let values: Vec<&String> = distinct_set
            .as_array()
            .unwrap()
            .iter()
            .map(|case_id| results.get(case_id.as_str().unwrap()).unwrap())
            .collect();
        let unique: std::collections::BTreeSet<&String> = values.iter().copied().collect();
        assert_eq!(unique.len(), values.len());
    }
}

#[test]
fn routing_vectors() {
    let fixture = load_fixture("routing.json");
    let mut configurations = std::collections::BTreeMap::new();
    for (name, source) in fixture["configurations"].as_object().unwrap() {
        configurations.insert(
            name.clone(),
            family::parse_configuration_source(source.as_str().unwrap()).unwrap(),
        );
    }
    for case in fixture["cases"].as_array().unwrap() {
        let configuration = configurations
            .get(case["configuration"].as_str().unwrap())
            .unwrap();
        assert_case(case, || {
            family::resolve_connection(configuration, &case["request"]).map(Value::String)
        });
    }
}
