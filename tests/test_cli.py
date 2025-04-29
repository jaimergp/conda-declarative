import sys

import pytest


@pytest.mark.parametrize("command", ("apply", "edit"))
def test_cli(monkeypatch, conda_cli, command):
    monkeypatch.setattr(sys, "argv", ["conda", *sys.argv[1:]])
    out, err, _ = conda_cli(command, "-h", raises=SystemExit)
    assert not err
    assert f"conda {command}" in out
