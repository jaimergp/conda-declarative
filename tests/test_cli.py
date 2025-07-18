import sys

try:
    from tomllib import loads
except ImportError:
    from tomli import loads

import pytest

from conda_declarative import state


@pytest.mark.parametrize(
    "command",
    [
        "apply",
        "edit",
    ],
)
def test_cli(monkeypatch, conda_cli, command):
    """Test that the new subcommands work."""
    monkeypatch.setattr(sys, "argv", ["conda", *sys.argv[1:]])
    out, err, _ = conda_cli(command, "-h", raises=SystemExit)
    assert not err
    assert f"conda {command}" in out


def test_update_env(python_prefix, conda_cli):
    """Test that updating the env correctly writes to the declarative env file."""
    # Add flask to the environment; then check that it has been added
    # correctly to the declarative env file.
    conda_cli("install", f"--prefix={str(python_prefix)}", "flask", "--yes")
    with open(state.get_manifest_path(python_prefix)) as f:
        requested = loads(f.read())["dependencies"]

    assert sorted(requested) == sorted(["flask", "python"])
