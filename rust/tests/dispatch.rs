//! Black-box dispatch tests: spawn the built `determa` launcher with a controlled
//! PATH of stub executables. Mirrors `python/tests/test_cli.py` and `node/test/dispatch.test.js`.

#![cfg(unix)]

use std::fs;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicUsize, Ordering};

const BIN: &str = env!("CARGO_BIN_EXE_determa");
static TEMP_SEQUENCE: AtomicUsize = AtomicUsize::new(0);

struct TempDir {
    path: PathBuf,
}

impl TempDir {
    fn new() -> Self {
        let sequence = TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "determa-dispatch-test-{}-{sequence}",
            std::process::id()
        ));
        let _ = fs::remove_dir_all(&path);
        fs::create_dir(&path).unwrap();
        Self { path }
    }

    fn path(&self) -> &Path {
        &self.path
    }
}

impl Drop for TempDir {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.path);
    }
}

/// A temp PATH populated with `determa-<name>` stubs that print `ran:<marker>: <args>`.
struct StubPath {
    dir: TempDir,
}

impl StubPath {
    fn new() -> Self {
        Self {
            dir: TempDir::new(),
        }
    }

    fn add(&self, name: &str, marker: &str) {
        let path = self.dir.path().join(name);
        fs::write(
            &path,
            format!("#!/bin/sh\necho \"ran:{marker}: $*\"\nexit 0\n"),
        )
        .unwrap();
        let mut perms = fs::metadata(&path).unwrap().permissions();
        perms.set_mode(0o755);
        fs::set_permissions(&path, perms).unwrap();
    }

    fn path_env(&self) -> String {
        let mut s = self.dir.path().to_string_lossy().into_owned();
        s.push(':');
        if let Ok(p) = std::env::var("PATH") {
            s.push_str(&p);
        }
        s
    }
}

fn run(args: &[&str], path_env: &str, env: &[(&str, &str)]) -> (i32, String, String) {
    let mut cmd = Command::new(BIN);
    cmd.args(args).env("PATH", path_env);
    for (k, v) in env {
        cmd.env(k, v);
    }
    let out = cmd.output().unwrap();
    (
        out.status.code().unwrap_or(1),
        String::from_utf8_lossy(&out.stdout).into_owned(),
        String::from_utf8_lossy(&out.stderr).into_owned(),
    )
}

fn make_state_stubs(sp: &StubPath) {
    sp.add("determa-state", "canonical");
    sp.add("determa-state-python", "python");
    sp.add("determa-state-rust", "rust");
}

#[test]
fn help_and_version() {
    let sp = StubPath::new();
    let path = sp.path_env();
    let (rc, out, _) = run(&["--help"], &path, &[]);
    assert_eq!(rc, 0);
    assert!(out.contains("umbrella launcher for the Determa family"));
    let (rc, out, _) = run(&["--version"], &path, &[]);
    assert_eq!(rc, 0);
    assert!(out.starts_with("determa "));
}

#[test]
fn unknown_product_exits_127() {
    let sp = StubPath::new();
    let (rc, _, err) = run(&["definitely-not-real"], &sp.path_env(), &[]);
    assert_eq!(rc, 127);
    assert!(err.contains("not found on PATH"));
}

#[test]
fn reserved_family_commands_exit_2_before_dispatch() {
    for command in ["auth", "config", "context"] {
        let sp = StubPath::new();
        sp.add(&format!("determa-{command}"), "must-not-run");
        let (rc, out, err) = run(&[command], &sp.path_env(), &[]);
        assert_eq!(rc, 2);
        assert_eq!(out, "");
        assert_eq!(
            err,
            format!("determa: family command '{command}' is reserved but not implemented yet.\n")
        );
    }
}

#[test]
fn dispatches_to_canonical_and_propagates_exit() {
    let sp = StubPath::new();
    sp.add("determa-echo", "echo-product");
    let (rc, out, _) = run(&["echo", "hi", "there"], &sp.path_env(), &[]);
    assert_eq!(rc, 0);
    assert!(out.contains("ran:echo-product: hi there"));

    sp.add("determa-boom", "boom");
    fs::write(sp.dir.path().join("determa-boom"), "#!/bin/sh\nexit 3\n").unwrap();
    let mut perms = fs::metadata(sp.dir.path().join("determa-boom"))
        .unwrap()
        .permissions();
    perms.set_mode(0o755);
    fs::set_permissions(sp.dir.path().join("determa-boom"), perms).unwrap();
    let (rc, _, _) = run(&["boom"], &sp.path_env(), &[]);
    assert_eq!(rc, 3);
}

#[test]
fn dispatch_prefers_impl_env_var() {
    let sp = StubPath::new();
    make_state_stubs(&sp);
    let (rc, out, _) = run(
        &["state", "--version"],
        &sp.path_env(),
        &[("DETERMA_STATE_IMPL", "rust")],
    );
    assert_eq!(rc, 0);
    assert!(out.contains("ran:rust: --version"), "{out}");
}

#[test]
fn dispatch_env_var_unset_uses_canonical() {
    let sp = StubPath::new();
    make_state_stubs(&sp);
    let (rc, out, _) = run(&["state", "info"], &sp.path_env(), &[]);
    assert_eq!(rc, 0);
    assert!(out.contains("ran:canonical: info"), "{out}");
}

#[test]
fn dispatch_impl_missing_falls_back_to_canonical() {
    let sp = StubPath::new();
    sp.add("determa-state", "canonical"); // no suffixed stubs present
    let (rc, out, _) = run(
        &["state", "ping"],
        &sp.path_env(),
        &[("DETERMA_STATE_IMPL", "rust")],
    );
    assert_eq!(rc, 0);
    assert!(out.contains("ran:canonical: ping"), "{out}");
}

#[test]
fn list_shows_impl_variants() {
    let sp = StubPath::new();
    make_state_stubs(&sp);
    // isolate PATH to the stub dir only
    let isolated = format!("{}", sp.dir.path().to_string_lossy());
    let (rc, out, _) = run(&["list"], &isolated, &[]);
    assert_eq!(rc, 0);
    assert!(out.contains("state (python, rust)"), "{out}");
    assert!(!out.contains("state-python"));
    assert!(!out.contains("state-rust"));
}

#[test]
fn help_shows_impl_variants() {
    let sp = StubPath::new();
    make_state_stubs(&sp);
    let isolated = format!("{}", sp.dir.path().to_string_lossy());
    let (rc, out, _) = run(&["--help"], &isolated, &[]);
    assert_eq!(rc, 0);
    assert!(out.contains("state (python, rust)"), "{out}");
    assert!(out.contains("DETERMA_<PRODUCT>_IMPL"));
}

#[test]
fn reserved_family_commands_are_hidden_from_discovery() {
    let sp = StubPath::new();
    for name in [
        "determa-alpha",
        "determa-auth",
        "determa-config",
        "determa-config-rust",
        "determa-context",
    ] {
        sp.add(name, "unused");
    }
    let isolated = format!("{}", sp.dir.path().to_string_lossy());
    let (rc, out, _) = run(&["list"], &isolated, &[]);
    assert_eq!(rc, 0);
    assert_eq!(out, "alpha\n");

    let (rc, out, _) = run(&["--help"], &isolated, &[]);
    assert_eq!(rc, 0);
    assert!(out.contains("  alpha"));
    assert!(!out.contains("  auth"));
    assert!(!out.contains("  config"));
    assert!(!out.contains("  context"));
}
