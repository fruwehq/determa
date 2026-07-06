"""Unit tests for the determa launcher (dispatch, discovery, help/version)."""

from __future__ import annotations

import os
import sys

import pytest

import determa._cli as cli


def test_help_shows_usage(capsys):
    assert cli.main(["--help"]) == 0
    out = capsys.readouterr().out
    assert "umbrella launcher for the Determa family" in out
    assert "determa <product>" in out


def test_no_args_is_help(capsys):
    assert cli.main([]) == 0
    assert "usage: determa" in capsys.readouterr().out


def test_version(capsys):
    assert cli.main(["--version"]) == 0
    assert capsys.readouterr().out.startswith("determa ")


def test_unknown_product_exits_127(capsys):
    assert cli.main(["definitely-not-real"]) == 127
    assert "not found on PATH" in capsys.readouterr().err


@pytest.mark.skipif(sys.platform == "win32", reason="uses a POSIX shell stub")
def test_dispatches_to_product_on_path(tmp_path, monkeypatch, capfd):
    exe = tmp_path / "determa-echo"
    exe.write_text('#!/bin/sh\necho "echo-product: $*"\nexit 0\n')
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ.get("PATH", ""))

    assert cli.main(["echo", "hello", "world"]) == 0
    assert "echo-product: hello world" in capfd.readouterr().out


@pytest.mark.skipif(sys.platform == "win32", reason="uses a POSIX shell stub")
def test_dispatch_propagates_exit_code(tmp_path, monkeypatch):
    exe = tmp_path / "determa-boom"
    exe.write_text("#!/bin/sh\nexit 3\n")
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ.get("PATH", ""))
    assert cli.main(["boom"]) == 3


@pytest.mark.skipif(sys.platform == "win32", reason="uses a POSIX shell stub")
def test_list_discovers_products(tmp_path, monkeypatch, capsys):
    (tmp_path / "determa-alpha").write_text("#!/bin/sh\n")
    (tmp_path / "determa-beta").write_text("#!/bin/sh\n")
    for f in ("determa-alpha", "determa-beta"):
        (tmp_path / f).chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))  # isolate PATH to the stub dir
    assert cli.main(["list"]) == 0
    assert capsys.readouterr().out.split() == ["alpha", "beta"]


# --- implementation selection (DETERMA_<PRODUCT>_IMPL) ---------------------

def _make_state_stubs(tmp_path):
    """Create determa-state, determa-state-python, determa-state-rust stubs that
    each print a distinct marker so tests can tell which one ran."""
    for name, marker in (
        ("determa-state", "canonical"),
        ("determa-state-python", "python"),
        ("determa-state-rust", "rust"),
    ):
        exe = tmp_path / name
        exe.write_text(f'#!/bin/sh\necho "ran:{marker}: $*"\nexit 0\n')
        exe.chmod(0o755)


@pytest.mark.skipif(sys.platform == "win32", reason="uses a POSIX shell stub")
def test_dispatch_prefers_impl_env_var(tmp_path, monkeypatch, capfd):
    _make_state_stubs(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setenv("DETERMA_STATE_IMPL", "rust")
    assert cli.main(["state", "--version"]) == 0
    assert "ran:rust: --version" in capfd.readouterr().out


@pytest.mark.skipif(sys.platform == "win32", reason="uses a POSIX shell stub")
def test_dispatch_env_var_unset_uses_canonical(tmp_path, monkeypatch, capfd):
    _make_state_stubs(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.delenv("DETERMA_STATE_IMPL", raising=False)
    assert cli.main(["state", "info"]) == 0
    assert "ran:canonical: info" in capfd.readouterr().out


@pytest.mark.skipif(sys.platform == "win32", reason="uses a POSIX shell stub")
def test_dispatch_impl_missing_falls_back_to_canonical(tmp_path, monkeypatch, capfd):
    # Only the canonical binary exists; the requested impl is absent -> fall back.
    exe = tmp_path / "determa-state"
    exe.write_text('#!/bin/sh\necho "ran:canonical: $*"\nexit 0\n')
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setenv("DETERMA_STATE_IMPL", "rust")
    assert cli.main(["state", "ping"]) == 0
    assert "ran:canonical: ping" in capfd.readouterr().out


@pytest.mark.skipif(sys.platform == "win32", reason="uses a POSIX shell stub")
def test_list_shows_impl_variants(tmp_path, monkeypatch, capsys):
    _make_state_stubs(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path))  # isolate PATH
    assert cli.main(["list"]) == 0
    out = capsys.readouterr().out
    assert "state (python, rust)" in out
    # the bare canonical-only stems are not double-listed
    assert "state-python" not in out
    assert "state-rust" not in out


@pytest.mark.skipif(sys.platform == "win32", reason="uses a POSIX shell stub")
def test_help_shows_impl_variants(tmp_path, monkeypatch, capsys):
    _make_state_stubs(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path))
    assert cli.main(["--help"]) == 0
    out = capsys.readouterr().out
    assert "state (python, rust)" in out
    assert "DETERMA_<PRODUCT>_IMPL" in out
