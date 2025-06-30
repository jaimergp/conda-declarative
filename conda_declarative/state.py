"""Code for managing the declarative input state in an environment."""

import pathlib
from collections.abc import Iterable
from dataclasses import asdict

try:
    from tomllib import loads
except ImportError:
    from tomli import loads

from conda.base.constants import (
    DEFAULT_SOLVER,
    ChannelPriority,
    DepsModifier,
    SatSolverChoice,
    UpdateModifier,
)
from conda.base.context import context, env_name
from conda.history import History
from conda.models.environment import Environment, EnvironmentConfig
from conda.models.match_spec import MatchSpec
from tomli_w import dump

from .constants import CONDA_MANIFEST_FILE


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

    packages, config = None, None

    current_env = from_env_file(prefix)
    if current_env is not None:
        config = current_env.config
        packages = {pkg.name: pkg for pkg in current_env.requested_packages}

    if packages is None:
        packages = {}
        for pkg in History(prefix=str(prefix)).get_requested_specs_map().values():
            packages[pkg.name] = pkg

    packages.update({pkg.name: pkg for pkg in update_specs})
    for pkg in remove_specs:
        if pkg.name in packages:
            del packages[pkg.name]

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

    to_env_file(
        Environment(
            prefix=str(prefix),
            platform=context.subdir,
            config=config,
            name=env_name(str(prefix)),
            requested_packages=list(packages.values()),
        ),
    )


def get_env_path(prefix: str | pathlib.Path) -> pathlib.Path:
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


def from_env_file(prefix: str | pathlib.Path) -> Environment | None:
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
        The Environment model, if the env file exists; None otherwise
    """
    env_path = get_env_path(prefix)
    if env_path.exists():
        with open(env_path) as f:
            return dict_to_env(loads(f.read()))

    return None


def to_env_file(environment: Environment):
    """Write the Environment to the appropriate path in the environment directory.

    Note that not all fields of the `Environment` model are supported. Fields that are
    either primitive types or dataclasses, or primitive containers of primitive types
    or dataclasses are handled automatically. Other fields are not, with the exception
    of the `requested_packages`, which is the only non-primitive field used here.

    Parameters
    ----------
    environment : Environment
        Environment model to serialize and write to disk
    """
    with open(get_env_path(environment.prefix), "wb") as f:
        dump(env_to_dict(environment), f)


def dict_to_env(env_dict: dict) -> Environment:
    """Convert a serialized dict of an environment to an Environment.

    Parameters
    ----------
    env_dict : dict
        Serialized dict of an conda.models.environment.Environment containing only
        primitive types

    Returns
    -------
    Environment
        Instance of the Environment
    """
    # Coerce any non-primitive types to primitive types so they
    # can be (de)serialized
    env_dict["requested_packages"] = list(
        map(MatchSpec, env_dict.get("requested_packages", []))
    )

    # NoneType can't be serialized to TOML
    if env_dict.get("name") is None:
        env_dict["name"] = ""

    if "config" in env_dict:
        config = env_dict["config"]

        if "aggressive_update_packages" in config:
            if isinstance(config["aggressive_update_packages"], tuple | list):
                config["aggressive_update_packages"] = tuple(
                    map(MatchSpec, config["aggressive_update_packages"])
                )
            elif config["aggressive_update_packages"] is None:
                config["aggressive_update_packages"] = ()

        # Convert the string values to their enum type counterparts
        config["channel_priority"] = ChannelPriority(
            config.get("channel_priority", ChannelPriority.FLEXIBLE)
        )
        config["deps_modifier"] = DepsModifier(
            config.get("deps_modifier", DepsModifier.NOT_SET)
        )
        config["sat_solver"] = SatSolverChoice(
            config.get("sat_solver", SatSolverChoice.PYCOSAT)
        )
        config["update_modifier"] = UpdateModifier(
            config.get("update_modifier", UpdateModifier.UPDATE_SPECS)
        )

        # `NoneType` can't be serialized to TOML, so we just use the "default"
        # value of use_only_tar_bz2 here. By default this is `None`, but it is
        # treated everywhere in `conda` as a boolean, so we just coerce to False
        # here.
        config["use_only_tar_bz2"] = (
            False
            if config.get("use_only_tar_bz2") is None
            else config["use_only_tar_bz2"]
        )

        env_dict["config"] = EnvironmentConfig(**config)
    else:
        env_dict["config"] = None

    return Environment(**env_dict)


def env_to_dict(environment: Environment) -> dict:
    """Handle conversion of an Environment into a dict that can be dumped to a file.

    Parameters
    ----------
    environment : Environment
        Environment to serialize into a dict

    Returns
    -------
    dict
        Dictionary containing all the fields of the Environment as primitive types
    """
    env_dict = asdict(environment)

    # Coerce any non-primitive types to primitive types so they
    # can be (de)serialized
    env_dict["requested_packages"] = list(
        map(str, env_dict.get("requested_packages", []))
    )

    # NoneType can't be serialized to TOML
    if env_dict.get("name") is None:
        env_dict["name"] = ""

    config = env_dict["config"]

    # aggressive_update_packages can either be a bool or a tuple[MatchSpec]
    if "aggressive_update_packages" in config:
        if isinstance(config["aggressive_update_packages"], tuple | list):
            config["aggressive_update_packages"] = tuple(
                map(str, config.get("aggressive_update_packages", ()))
            )
        elif config["aggressive_update_packages"] is None:
            config["aggressive_update_packages"] = ()

    # Convert the enum types to their string values
    config["channel_priority"] = config.get(
        "channel_priority", ChannelPriority.FLEXIBLE
    ).value
    config["deps_modifier"] = config.get("deps_modifier", DepsModifier.NOT_SET).value
    config["sat_solver"] = config.get("sat_solver", SatSolverChoice.PYCOSAT).value
    config["update_modifier"] = config.get(
        "update_modifier", UpdateModifier.UPDATE_SPECS
    ).value
    config["solver"] = config.get("solver", DEFAULT_SOLVER)

    # `NoneType` can't be serialized to TOML, so we just use the "default"
    # value of use_only_tar_bz2 here. By default this is `None`, but it is
    # treated everywhere in `conda` as a boolean, so we just coerce to False
    # here.
    config["use_only_tar_bz2"] = (
        False if config.get("use_only_tar_bz2") is None else config["use_only_tar_bz2"]
    )

    return env_dict
