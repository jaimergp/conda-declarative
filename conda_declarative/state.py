"""Code for managing the state of env.yml."""

import pathlib
from collections.abc import Iterable
from dataclasses import asdict

from conda.base.context import context, env_name
from conda.common.serialize import yaml_safe_dump, yaml_safe_load
from conda.history import History
from conda.models.enums import Arch, Platform
from conda.models.environment import Environment, EnvironmentConfig
from conda.models.match_spec import MatchSpec


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


def update_state(
    prefix: str | None,
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
    packages, config = None, None

    current_env = from_env_file(prefix)
    if current_env is not None:
        packages = {}
        for pkg in current_env.requested_packages:
            if pkg not in remove_specs:
                packages[pkg.name] = pkg

        config = current_env.config

    if packages is None:
        packages = {}
        for pkg in History(prefix=prefix).get_requested_specs_map().values():
            if pkg not in remove_specs:
                packages[pkg.name] = pkg

    if config is None:
        config = EnvironmentConfig(
            aggressive_update_packages=context.aggressive_update_packages,
            channel_priority=context.channel_priority,
            channels=context.channels,
            channel_settings=context.channel_settings,
            deps_modifier=context.deps_modifier,
            disallowed_packages=context.disallowed_packages,
            pinned_packages=context.pinned_packages,
            repodata_fns=context.repodata_fns,
            sat_solver=context.sat_solver,
            solver=context.solver,
            track_features=context.track_features,
            update_modifier=context.update_modifier,
            use_only_tar_bz2=context.use_only_tar_bz2,
        )

    packages.update({pkg.name: pkg for pkg in update_specs})
    to_env_file(
        get_env_path(prefix),
        Environment(
            prefix=str(prefix),
            platform=get_platform(),
            config=config,
            name=env_name(str(prefix)),
            requested_packages=list(packages.values()),
        ),
    )


def get_env_path(prefix: pathlib.Path) -> pathlib.Path:
    """Get the path to the declarative environment file for the prefix.

    Parameters
    ----------
    prefix : pathlib.Path
        Prefix to use for the environment file

    Returns
    -------
    pathlib.Path
        Path to the environment file
    """
    return pathlib.Path(prefix) / "conda-meta" / "env.yml"


def from_env_file(prefix: str) -> Environment | None:
    """Load a declarative env file into an Environment model.

    Note that not all fields of the `Environment` model are supported
    here.

    Parameters
    ----------
    prefix : str
        Prefix of the environment

    Returns
    -------
    Environment | None
        The Environment model, if the env file exists; None otherwise
    """
    if get_env_path(prefix).exists():
        with open(get_env_path(prefix)) as f:
            env_dict = yaml_safe_load(f.read())

        # Handle the config and requested_packages separately. They not primitive types
        # and thus not automatically instantiated with the appropriate dataclasses
        if "config" in env_dict:
            env_dict["config"] = EnvironmentConfig(**env_dict["config"])
        else:
            env_dict["config"] = None

        pkg_specs = []
        for pkg in env_dict.get("requested_packages", []):
            pkg_specs.append(MatchSpec(pkg))
        env_dict["requested_packages"] = pkg_specs

        return Environment(**env_dict)

    return None


def to_env_file(path: pathlib.Path, environment: Environment):
    """Write the Environment to the given path.

    Note that not all fields of the `Environment` model are supported. Fields that are
    either primitive types or datacalsses, or primitive containers of primitive types
    or dataclasses are handled automatically. Other fields are not, with the exception
    of the `requested_packages`, which is the only non-primitive field used here.

    Parameters
    ----------
    path : pathlib.Path
        Path to write the environment to
    environment : Environment
        Environment model to serialize and write to disk
    """
    env_dict = asdict(environment)

    # Replace all the requested packages, which are of type `MatchSpec`,
    # with their string equivalents.
    env_dict["requested_packages"] = [
        str(spec) for spec in env_dict["requested_packages"]
    ]
    with open(get_env_path(environment.prefix), "w") as f:
        yaml_safe_dump(env_dict, f)
