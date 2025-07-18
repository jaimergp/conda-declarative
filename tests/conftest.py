from pathlib import Path
from typing import Any
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

        with open(state.get_manifest_path(prefix)) as f:
            requested = loads(f.read())["dependencies"]
        assert requested == {"python": "*"}
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

        with open(state.get_manifest_path(prefix)) as f:
            requested = loads(f.read())["dependencies"]

        assert set(requested) == set(["python", "flask"])
        yield prefix


@pytest.fixture
def single_environment_path() -> Path:
    """Return the path to a single environment toml file.

    Returns
    -------
    Path
        The toml environment file path
    """
    return Path(__file__).parent / "assets" / "single_environment.toml"


@pytest.fixture
def multi_environment_path() -> Path:
    """Return the path to a multi environment toml file.

    Returns
    -------
    Path
        The toml environment file path
    """
    return Path(__file__).parent / "assets" / "multi_environment.toml"


@pytest.fixture
def multi_environment_path2() -> Path:
    """Return the path to a multi environment toml file.

    Returns
    -------
    Path
        The toml environment file path
    """
    return Path(__file__).parent / "assets" / "multi_environment2.toml"


@pytest.fixture
def single_environment_dict(single_environment_path) -> dict[str, Any]:
    """Return a single environment toml file, parsed into a dict.

    Returns
    -------
    dict[str, Any]
        The toml environment file, parsed into a dict
    """
    with open(single_environment_path) as f:
        return loads(f.read())


@pytest.fixture
def multi_environment_dict(multi_environment_path) -> dict[str, Any]:
    """Return a multi environment toml file, parsed into a dict.

    Returns
    -------
    dict[str, Any]
        The toml environment file, parsed into a dict
    """
    with open(multi_environment_path) as f:
        return loads(f.read())


@pytest.fixture
def multi_environment_dict2(multi_environment_path2) -> dict[str, Any]:
    """Return another multi environment toml file, parsed into a dict.

    Returns
    -------
    dict[str, Any]
        The toml environment file, parsed into a dict
    """
    with open(multi_environment_path2) as f:
        return loads(f.read())
