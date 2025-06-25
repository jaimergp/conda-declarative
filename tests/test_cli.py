import sys

import pytest
from conda.common.serialize import yaml_safe_load

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
    with open(state.get_env_path(python_prefix)) as f:
        requested = yaml_safe_load(f.read())["requested_packages"]
    assert requested == ["python"]

    # Add flask to the environment; then check that it has been added
    # correctly to the declarative env file
    conda_cli("install", f"--prefix={str(python_prefix)}", "flask", "--yes")
    with open(state.get_env_path(python_prefix)) as f:
        requested = yaml_safe_load(f.read())["requested_packages"]

    assert sorted(requested) == sorted(["flask", "python"])
