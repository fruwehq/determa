//! determa — umbrella launcher for the Determa family.
//!
//! A thin, git-style dispatcher: `determa <product> [args…]` runs the
//! `determa-<product>` executable found on `PATH` (e.g. `determa state run m.yaml`
//! → `determa-state run m.yaml`). It is language-agnostic: it dispatches to whichever
//! `determa-state` is installed, be it the Rust or the Python build.

use std::collections::BTreeSet;
use std::env;
use std::fs;
use std::process::{exit, Command};

const PREFIX: &str = "determa-";

fn version() -> &'static str {
    env!("CARGO_PKG_VERSION")
}

/// Product subcommands available as `determa-<name>` executables on `PATH`.
fn discover() -> Vec<String> {
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
    found.into_iter().collect()
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
    let products = discover();
    if products.is_empty() {
        println!("no products found on PATH. install one, e.g.:");
        println!("  cargo install determa-state");
    } else {
        println!("installed products:");
        for product in products {
            println!("  {product}");
        }
    }
}

fn main() {
    let args: Vec<String> = env::args().skip(1).collect();
    match args.first().map(String::as_str) {
        None | Some("-h") | Some("--help") | Some("help") => print_help(),
        Some("-V") | Some("--version") | Some("version") => println!("determa {}", version()),
        Some("list") => {
            for product in discover() {
                println!("{product}");
            }
        }
        Some(sub) => {
            let exe = format!("{PREFIX}{sub}");
            match Command::new(&exe).args(&args[1..]).status() {
                Ok(status) => exit(status.code().unwrap_or(1)),
                Err(_) => {
                    eprintln!("determa: unknown product '{sub}' — '{exe}' not found on PATH.");
                    eprintln!("try 'determa list', or install it (e.g. 'cargo install {exe}').");
                    exit(127);
                }
            }
        }
    }
}
