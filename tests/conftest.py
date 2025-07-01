from unittest import mock

import pytest

try:
    from tomllib import loads
except ImportError:
    from tomli import loads

from conda_declarative import state

pytest_plugins = ("conda.testing.fixtures",)


@pytest.fixture
def python_prefix(tmp_env):
    """Create a temp environment with python.

    The context target prefix is also mocked to point to the temp prefix rather than
    whatever conda environment prefix the test is being run in.

    Additionally, check that the declarative env file contains python as well.
    """
    with (
        tmp_env("python") as prefix,
        mock.patch("conda.base.context.determine_target_prefix") as mock_target_prefix,
    ):
        mock_target_prefix.return_value = str(prefix)

        with open(state.get_env_path(prefix)) as f:
            requested = loads(f.read())["requested_packages"]
        assert requested == ["python"]
        yield prefix


@pytest.fixture
def python_flask_prefix(tmp_env):
    """Create a temp environment with python and flask.

    The context target prefix is also mocked to point to the temp prefix rather than
    whatever conda environment prefix the test is being run in.

    Additionally, check that the declarative env file contains python and flask as well.
    """
    with (
        tmp_env("python", "flask") as prefix,
        mock.patch("conda.base.context.determine_target_prefix") as mock_target_prefix,
    ):
        mock_target_prefix.return_value = str(prefix)

        with open(state.get_env_path(prefix)) as f:
            requested = loads(f.read())["requested_packages"]

        assert set(requested) == set(["python", "flask"])
        yield prefix
