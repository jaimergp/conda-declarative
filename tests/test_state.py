import pathlib
from unittest import mock

import pytest
from conda.base.constants import PLATFORMS

from conda_declarative import state


def test_get_platform():
    """Test that the current platform is one of the valid platforms."""
    assert state.get_platform() in PLATFORMS


@pytest.mark.parametrize(
    "prefix_type",
    [
        str,
        pathlib.Path,
        lambda _: None,
    ],
)
@pytest.mark.parametrize("update_specs", [["python=3.10"], ["bar", "baz"], [], None])
@pytest.mark.parametrize(
    "remove_specs",
    [
        ["flask"],
        [],
    ],
)
def test_update_state(
    python_flask_prefix, conda_cli, prefix_type, update_specs, remove_specs
):
    """Test that all types of inputs are handled correctly by update_state."""
    with mock.patch("conda.common.serialize.yaml_safe_dump") as mock_dump:
        state.update_state(
            prefix_type(python_flask_prefix),
            remove_specs=remove_specs,
            update_specs=update_specs,
        )

    mock_dump.assert_called_once()

    env_dict = mock_dump.call_args_list[0]
    breakpoint()

    print("foo")
