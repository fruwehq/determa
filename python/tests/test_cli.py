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
