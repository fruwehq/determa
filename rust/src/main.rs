//! determa — umbrella launcher for the Determa family.
//!
//! A thin, git-style dispatcher: `determa <product> [args…]` runs the
//! `determa-<product>` executable found on `PATH` (e.g. `determa state run m.yaml`
//! → `determa-state run m.yaml`). It is language-agnostic: it dispatches to whichever
//! `determa-state` is installed, be it the Rust or the Python build.
//!
//! When multiple language builds are installed side by side, set
//! `DETERMA_<PRODUCT>_IMPL` (e.g. `DETERMA_STATE_IMPL=rust`) to pick the
//! `determa-<product>-<impl>` variant; otherwise the canonical `determa-<product>`
//! command is used.

use std::collections::{BTreeMap, BTreeSet};
use std::env;
use std::fs;
use std::process::{exit, Command};

const PREFIX: &str = "determa-";

fn version() -> &'static str {
    env!("CARGO_PKG_VERSION")
}

/// Every `determa-<stem>` executable stem on `PATH` (extension-stripped).
fn stems() -> BTreeSet<String> {
    let mut found = BTreeSet::new();
    if let Some(path) = env::var_os("PATH") {
        for dir in env::split_paths(&path) {
            let entries = match fs::read_dir(&dir) {
                Ok(entries) => entries,
                Err(_) => continue,
            };
            for entry in entries.flatten() {
                if let Some(name) = entry.file_name().to_str() {
                    if let Some(sub) = name.strip_prefix(PREFIX) {
                        let sub = sub.strip_suffix(".exe").unwrap_or(sub);
                        if !sub.is_empty() {
                            found.insert(sub.to_string());
                        }
                    }
                }
            }
        }
    }
    found
}

/// Split a stem into `(product, Some(impl))` for a variant, or `(stem, None)` for a
/// canonical product. A stem `<product>-<impl>` is a variant when `<product>` is itself
/// present on `PATH`; the longest such product prefix wins.
fn split_variant(stem: &str, all: &BTreeSet<String>) -> (String, Option<String>) {
    let parts: Vec<&str> = stem.split('-').collect();
    for i in (1..parts.len()).rev() {
        let prefix = parts[..i].join("-");
        if all.contains(&prefix) {
            return (prefix, Some(parts[i..].join("-")));
        }
    }
    (stem.to_string(), None)
}

/// Products → sorted implementation variants on `PATH` (canonical products map to empty).
fn discover() -> Vec<(String, Vec<String>)> {
    let all = stems();
    let mut products: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    for stem in &all {
        let (product, impl_) = split_variant(stem, &all);
        let entry = products.entry(product).or_default();
        if let Some(impl_) = impl_ {
            entry.insert(impl_);
        }
    }
    products
        .into_iter()
        .map(|(p, impls)| (p, impls.into_iter().collect()))
        .collect()
}

/// Resolve the executable for `product`, honoring `DETERMA_<PRODUCT>_IMPL`.
fn exe_for(product: &str) -> Option<String> {
    let env_var = format!("DETERMA_{}_IMPL", product.replace('-', "_").to_uppercase());
    if let Ok(impl_) = env::var(&env_var) {
        let suffixed = format!("{PREFIX}{product}-{impl_}");
        if which(&suffixed).is_some() {
            return Some(suffixed);
        }
    }
    let canonical = format!("{PREFIX}{product}");
    which(&canonical).map(|_| canonical)
}

/// Locate an executable on `PATH` (like `shutil.which`). Returns the resolved path.
fn which(name: &str) -> Option<std::path::PathBuf> {
    let path = env::var_os("PATH")?;
    for dir in env::split_paths(&path) {
        let candidate = dir.join(name);
        if candidate.is_file() {
            return Some(candidate);
        }
    }
    None
}

fn format_product(product: &str, impls: &[String]) -> String {
    if impls.is_empty() {
        product.to_string()
    } else {
        format!("{product} ({})", impls.join(", "))
    }
}

fn print_help() {
    println!(
        "determa {} — umbrella launcher for the Determa family\n",
        version()
    );
    println!("usage: determa <product> [args…]");
    println!("       determa list        list installed products");
    println!("       determa --version   show this launcher's version\n");
    println!("'determa <product> …' runs the 'determa-<product>' command on PATH,");
    println!("e.g. 'determa state run m.yaml' → 'determa-state run m.yaml'.\n");
    println!("set DETERMA_<PRODUCT>_IMPL (e.g. DETERMA_STATE_IMPL=python|rust) to pick a");
    println!("specific language build when both 'determa-state-python' and 'determa-state-rust'");
    println!("are installed; otherwise the canonical 'determa-state' is used.\n");
    let products = discover();
    if products.is_empty() {
        println!("no products found on PATH. install one, e.g.:");
        println!("  cargo install determa-state");
    } else {
        println!("installed products:");
        for (product, impls) in &products {
            println!("  {}", format_product(product, impls));
        }
    }
}

fn main() {
    let args: Vec<String> = env::args().skip(1).collect();
    match args.first().map(String::as_str) {
        None | Some("-h") | Some("--help") | Some("help") => print_help(),
        Some("-V") | Some("--version") | Some("version") => println!("determa {}", version()),
        Some("list") => {
            for (product, impls) in discover() {
                println!("{}", format_product(&product, &impls));
            }
        }
        Some(sub) => match exe_for(sub) {
            Some(exe) => match Command::new(&exe).args(&args[1..]).status() {
                Ok(status) => exit(status.code().unwrap_or(1)),
                Err(_) => {
                    eprintln!("determa: failed to run {exe}.");
                    exit(126);
                }
            },
            None => {
                let exe = format!("{PREFIX}{sub}");
                eprintln!("determa: unknown product '{sub}' — '{exe}' not found on PATH.");
                eprintln!("try 'determa list', or install it (e.g. 'cargo install {exe}').");
                exit(127);
            }
        },
    }
}
