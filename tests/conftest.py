from unittest import mock

import pytest
from conda.common.serialize import yaml_safe_load

from conda_declarative import state

pytest_plugins = ("conda.testing.fixtures",)


@pytest.fixture
def python_prefix(tmp_env, conda_cli):
    with (
        tmp_env("python") as prefix,
        mock.patch("conda.base.context.determine_target_prefix") as mock_target_prefix,
    ):
        mock_target_prefix.return_value = str(prefix)

        with open(state.get_env_path(prefix)) as f:
            requested = yaml_safe_load(f.read())["requested_packages"]
        assert requested == ["python"]
        yield prefix


@pytest.fixture
def python_flask_prefix(tmp_env, conda_cli):
    with (
        tmp_env("python", "flask") as prefix,
        mock.patch("conda.base.context.determine_target_prefix") as mock_target_prefix,
    ):
        mock_target_prefix.return_value = str(prefix)

        with open(state.get_env_path(prefix)) as f:
            requested = yaml_safe_load(f.read())["requested_packages"]

        assert set(requested) == set(["python", "flask"])
        yield prefix
