import pathlib
from unittest import mock

import pytest
from conda.models.match_spec import MatchSpec

from conda_declarative import state


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
        None,
    ],
)
@pytest.mark.parametrize("remove_initial_declarative_env_file", [True, False])
def test_update_state(
    python_flask_prefix,
    prefix_type,
    update_specs,
    remove_specs,
    remove_initial_declarative_env_file,
):
    """Test that all types of inputs are handled correctly by update_state.

    Also test that starting from an environment that _doesn't_ have a declarative env
    file also works.
    """
    if remove_initial_declarative_env_file:
        state.get_manifest_path(python_flask_prefix).unlink()

    with (
        mock.patch("conda_declarative.state.dump") as mock_dump,
        mock.patch(
            "conda_declarative.state.to_env_file", wraps=state.to_env_file
        ) as mock_to_env_file,
    ):
        state.update_state(
            prefix_type(python_flask_prefix),
            remove_specs=remove_specs,
            update_specs=update_specs,
        )

    mock_dump.assert_called_once()
    env_dict = mock_dump.call_args.args[0]

    # Generate the expected list of packages
    pkgs = {
        "python": MatchSpec("python"),
        "flask": MatchSpec("flask"),
    }
    if update_specs is not None:
        for spec in map(MatchSpec, update_specs):
            pkgs[spec.name] = spec
    if remove_specs is not None:
        for spec in map(MatchSpec, remove_specs):
            if spec.name in pkgs:
                del pkgs[spec.name]

    # The environment file should have the expected packages. Need to construct MatchSpec
    # objects from the set of dumped dependencies because MatchSpec can basically only match against
    # PackageRecord objects, or other MatchSpec objects.
    for expected_name, expected_spec in pkgs.items():
        assert expected_spec.match(
            MatchSpec(
                name=expected_name, version=env_dict["dependencies"][expected_name]
            )
        )

    # Internally the prefix should match where flask is installed
    assert str(mock_to_env_file.call_args.args[0]) == str(python_flask_prefix)
