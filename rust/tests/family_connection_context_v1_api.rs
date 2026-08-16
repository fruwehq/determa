use determa::family_connection_context_v1 as family;
use serde_json::{json, Value};

#[test]
fn decoded_configuration_is_opaque_and_isolated_from_mutation() {
    let mut source = json!({
        "version": 1,
        "connections": {"cloud": {"endpoint": "https://example.com"}},
        "contexts": {},
    });
    let configuration = family::validate_configuration(&source).unwrap();
    source["connections"]["cloud"]["endpoint"] =
        Value::String("https://changed.example".to_string());
    let mut exported = configuration.to_value();
    exported["connections"] = json!({});

    assert_eq!(
        family::resolve_connection(
            &configuration,
            &json!({"resource": "state", "explicit_connection": "cloud"}),
        )
        .unwrap(),
        "cloud"
    );
}

#[test]
fn malformed_requests_return_family_errors() {
    let configuration = family::validate_configuration(&json!({
        "version": 1,
        "connections": {},
        "contexts": {},
    }))
    .unwrap();
    for request in [
        Value::Null,
        Value::Array(Vec::new()),
        Value::String("state".to_string()),
        Value::Number(1.into()),
    ] {
        assert_eq!(
            family::resolve_connection(&configuration, &request)
                .unwrap_err()
                .code,
            "invalid_type"
        );
    }
}

#[test]
fn malformed_decoded_configuration_returns_family_error() {
    assert_eq!(
        family::validate_configuration(&Value::Null)
            .unwrap_err()
            .code,
        "invalid_type"
    );
}
