from unittest import mock

from conda.base.constants import PLATFORMS
from conda.base.context import context
from conda.common.serialize import yaml_safe_load

from conda_declarative import state


def test_get_platform():
    """Test that the current platform is one of the valid platforms."""
    assert state.get_platform() in PLATFORMS


def test_update_state(tmp_env, conda_cli):
    """Test that updating the env correctly writes to the declarative env file."""
    with (
        tmp_env("python") as prefix,
        mock.patch("conda.base.context.determine_target_prefix") as mock_target_prefix,
    ):
        mock_target_prefix.return_value = str(prefix)

        # Check that the temp environment has replaced the context's target_prefix,
        # rather than being the context in which the test is being run
        assert context.target_prefix == str(prefix)

        with open(state.get_env_path(prefix)) as f:
            requested = yaml_safe_load(f.read())["requested_packages"]
        assert requested == ["python"]

        # Add flask to the environment; then check that it has been added
        # correctly to the declarative env file
        conda_cli("install", f"--prefix={str(prefix)}", "flask", "--yes")
        with open(state.get_env_path(prefix)) as f:
            requested = yaml_safe_load(f.read())["requested_packages"]

        assert sorted(requested) == sorted(["flask", "python"])
