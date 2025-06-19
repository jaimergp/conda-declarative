"""Code for managing the state of env.yml."""

import pathlib
from dataclasses import asdict

from conda.base.context import context, env_name
from conda.common.serialize import yaml_safe_dump
from conda.history import History
from conda.models.enums import Arch, Platform
from conda.models.environment import Environment


def get_platform() -> str:
    """Get the current platform.

    Right now there's no way to get the current platform, so we roll our own function
    to do this here. Yes, you can use `conda.models.enums.Platform.from_sys`, but the
    values of this enum are not valid to pass to `conda.models.environment.Environment`,
    which must be one of `conda.base.constants.PLATFORMS`.

    Returns
    -------
    str
        Currently running platform; one of conda.base.constants.PLATFORMS
    """
    arch_enum = Arch.from_sys()
    match arch_enum:
        case Arch.x86:
            arch = "32"
        case Arch.x86_64:
            arch = "64"
        case _:
            arch = arch_enum.value

    platform_enum = Platform.from_sys()
    match platform_enum:
        case Platform.osx:
            platform = "osx"
        case Platform.win:
            platform = "win"
        case _:
            platform = platform_enum.value

    return f"{platform}-{arch}"


def update_state(_command: str) -> None:
    """Update `conda-meta/env.yml` with the current packages in the environment.

    Parameters
    ----------
    _command : str
        Conda subcommand invoked by the user that triggered this call
    """
    prefix = context.target_prefix
    packages = History(prefix=prefix).get_requested_specs_map()

    env_dict = asdict(
        Environment(
            prefix=str(prefix),
            platform=get_platform(),
            name=env_name(str(prefix)),
            requested_packages=list(packages.values()),
        )
    )

    # Replace all the requested packages, which are of type `MatchSpec`,
    # with their string equivalents.
    env_dict["requested_packages"] = [
        str(spec) for spec in env_dict["requested_packages"]
    ]
    with open(get_env_file(prefix), "w") as f:
        yaml_safe_dump(env_dict, f)


def get_env_file(prefix: pathlib.Path) -> pathlib.Path:
    """Get the file containing the up-to-date declarative environment.

    Parameters
    ----------
    prefix : pathlib.Path
        Prefix to search for the environment file

    Returns
    -------
    pathlib.Path
        Path to the environment file
    """
    return pathlib.Path(prefix) / "conda-meta" / "env.yml"
