"""Code for managing the declarative input state in an environment."""

import pathlib
from collections.abc import Iterable

try:
    from tomllib import loads
except ImportError:
    from tomli import loads  # noqa: F401

from conda.base.context import context
from conda.history import History
from conda.models.match_spec import MatchSpec
from tomli_w import dump

from .constants import CONDA_MANIFEST_FILE
from .spec import TomlSingleEnvironment, TomlSpec


def update_state(
    prefix: str | pathlib.Path | None,
    remove_specs: Iterable[MatchSpec] | None = None,
    update_specs: Iterable[MatchSpec] | None = None,
) -> None:
    """Update `conda-meta/env.yml` with the current packages in the environment.

    Both the environment config and the requested packages for the environment
    are read from the existing env file. If no env file exists, the requested
    packages are read from the history file and the environment config is generated
    from the context.

    Parameters
    ----------
    prefix : str | None
        Prefix for which is being modified by a user command
    remove_specs : Iterable[MatchSpec] | None
        Packages the user has requested to remove
    update_specs : Iterable[MatchSpec] | None
        Packages the user has either requested to add or update
    """
    if prefix is None:
        prefix = pathlib.Path(context.target_prefix)

    if remove_specs is None:
        remove_specs = []
    else:
        remove_specs = list(map(MatchSpec, remove_specs))

    if update_specs is None:
        update_specs = []
    else:
        update_specs = list(map(MatchSpec, update_specs))

    env_path = get_manifest_path(prefix)

    if env_path.exists():
        current_env = TomlSpec(env_path).model
        packages = {pkg.name: pkg for pkg in current_env.get_requested_packages()}
        pypi_dependencies = current_env.pypi_dependencies
    else:
        current_env = None
        packages = {}
        for pkg in History(prefix=str(prefix)).get_requested_specs_map().values():
            packages[pkg.name] = pkg
        pypi_dependencies = {}

    # Explicitly remove any requested packages that are being removed
    packages.update({pkg.name: pkg for pkg in update_specs})
    for pkg in remove_specs:
        if pkg.name in packages:
            del packages[pkg.name]

    model = TomlSingleEnvironment.model_validate(
        {
            "about": {
                "name": "",
                "revision": "1",
                "description": "",
            },
            "dependencies": packages,
            "pypi_dependencies": pypi_dependencies,
        }
    )

    to_env_file(prefix, model)


def get_manifest_path(prefix: str | pathlib.Path) -> pathlib.Path:
    """Get the path to the declarative environment file for the prefix.

    Parameters
    ----------
    prefix : str | pathlib.Path
        Prefix to use for the environment file

    Returns
    -------
    pathlib.Path
        Path to the environment file
    """
    return pathlib.Path(prefix) / CONDA_MANIFEST_FILE


def from_env_file(prefix: str | pathlib.Path) -> TomlSingleEnvironment:
    """Load a declarative env file into an Environment model.

    Note that not all fields of the `Environment` model are supported
    here.

    Parameters
    ----------
    prefix : str | pathlib.Path
        Prefix of the environment

    Returns
    -------
    Environment | None
        The Environment model, if the env file exists; an exception is raised if not
    """
    return TomlSpec(get_manifest_path(prefix)).model


def to_env_file(prefix: str | pathlib.Path, model: TomlSingleEnvironment):
    """Write the environment model to the appropriate path in the environment directory.

    Parameters
    ----------
    prefix : str | pathlib.Path
        Prefix of the environment where the manifest should be dumped
    model : TomlSingleEnvironment
        Model to serialize and write to disk


    """
    with open(get_manifest_path(prefix), "wb") as f:
        dump(model.model_dump(), f)
