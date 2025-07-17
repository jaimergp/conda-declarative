from __future__ import annotations

import string
from abc import ABC, abstractmethod
from copy import copy
from dataclasses import fields
from pathlib import Path
from pprint import pformat
from textwrap import indent
from typing import Annotated, Any
from warnings import warn

try:
    from tomllib import loads
except ImportError:
    from tomli import loads

from conda.base.context import context
from conda.models.environment import Environment, EnvironmentConfig
from conda.models.match_spec import MatchSpec
from conda.plugins.types import EnvironmentSpecBase
from pydantic import (
    AnyHttpUrl,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    EmailStr,
    PlainSerializer,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)


def handle_pypi_dependencies(
    value: dict[str, str | dict[str, str]],
) -> list[str | EditablePackage]:
    """Preprocess a set of raw pypi dependencies.

    Parameters
    ----------
    value : dict[str, str | dict[str, str]]
        A mapping between package names and either a version specifier, or
        a dict of that indicates it is a local editable package, e.g.

            conda-declarative = { path  = ".", editable = true }

    Returns
    -------
    list[str | EditablePackage]
        A list of processed pypi dependencies
    """
    items = []
    for name, item in value.items():
        if isinstance(item, str):
            if item == "*":
                # Install any version
                #
                #   example = "*"  # noqa: ERA001
                items.append(name)
            elif item[0] in string.digits:
                # Install a specific version
                #
                #   example = "12.0"  # noqa: ERA001
                items.append(f"{name}=={item}")
            else:
                # Some version constraint is specified
                #
                #   example = ">=2.28.0,<3"  # noqa: ERA001
                items.append(f"{name}{item}")
        elif isinstance(item, dict):
            # This is an editable local package
            items.append(EditablePackage(name=name, **item))
        else:
            raise ValueError

    return items


def handle_match_specs(
    value: dict[str, MatchSpec | str | dict[str, str]],
) -> list[MatchSpec | EditablePackage]:
    """Preprocess a set of raw conda dependencies.

    Dependencies can either be strings, or dicts which can be parsed to MatchSpec, or
    dicts which can be parsed as EditablePackage.

    Parameters
    ----------
    value : dict[str, MatchSpec | str | dict[str, str]]
        A string match spec, or a dict containing match spec key/values

    Returns
    -------
    list[MatchSpec | EditablePackage]
        A list of dependencies
    """
    items = []
    for name, item in value.items():
        if isinstance(item, MatchSpec):
            items.append(item)
        elif isinstance(item, str):
            items.append(MatchSpec(name=name, version=item))
        elif isinstance(item, dict):
            # This is a dict representation of a MatchSpec
            # or an editable file
            try:
                items.append(EditablePackage(name=name, **item))
            except ValidationError:
                items.append(MatchSpec(name=name, **item))
        else:
            raise ValueError

    return items


class TomlSpec(EnvironmentSpecBase):
    """Implementation of conda's EnvironmentSpec which can handle toml files.

    Acts as a converter to translate to and from TOML files, dicts, Environments, and
    TomlSingleEnvironment objects.


    ┌───────────┐    ┌────────────┐      ┌───────────────────────┐     ┌─────────────┐
    │ TOML file │◄───│ dictionary │◄─────┤ TomlSingleEnvironment │◄────┤ Environment │
    │           ├───►│            ├─────►│    pydantic model     │────►│  instance   │
    └───────────┘    └────────────┘      └───────────────────────┘     └─────────────┘

    """

    def __init__(self, obj: str | Path | TomlSingleEnvironment | Environment | dict):
        self._obj: str | Path | TomlSingleEnvironment | Environment | dict = obj

        self._filename: Path | None = None
        self._model: TomlSingleEnvironment | None = None
        self._environment: Environment | None = None

    def can_handle(self) -> bool:
        """Return whether the object passed to this class can be parsed.

        - If a file path was passed, try to open it and parse it.
        - If a dict was passed, try to parse it
        - If a

        Returns
        -------
        bool
            True if the file can be parsed (it exists and is a toml file), False
            otherwise
        """
        try:
            self._load()
            return True
        except Exception:
            return False

    def _load(self) -> None:
        if isinstance(self.obj, str | Path):
            self._filename = Path(self.obj)

            if self._filename.exists() and self._filename.suffix == ".toml":
                with open(self._filename) as f:
                    text = f.read()

                self._model = TomlSingleEnvironment.model_validate(loads(text))
                self._environment = self._model_to_environment(self._model)
            else:
                raise ValueError(f"No file exists at {self._filename}")

        elif isinstance(self.obj, TomlSingleEnvironment):
            self._model = self.obj
            self._environment = self._model_to_environment(self._model)

        elif isinstance(self.obj, dict):
            self._model = TomlSingleEnvironment.model_validate(self.obj)
            self._environment = self._model_to_environment(self._model)

        elif isinstance(self.obj, Environment):
            self._environment = self.obj
            self._model = self._environment_to_model(self._environment)

        else:
            raise ValueError(f"Invalid parameter for TomlSpec: {self._obj}")

    @staticmethod
    def _model_to_environment(model: TomlSingleEnvironment) -> Environment:
        return Environment(
            prefix=context.target_prefix,
            platform=context.subdir,
            config=combine(
                EnvironmentConfig.from_context(), model.config.get_environment_config()
            ),
            external_packages=model.get_external_packages(),
            name=model.about.name,
            requested_packages=model.get_requested_packages(),
            variables=model.config.variables,
        )

    @staticmethod
    def _environment_to_model(env: Environment) -> TomlSingleEnvironment:
        return TomlSingleEnvironment.model_validate(
            {
                "about": {
                    "name": env.name if env.name else "",
                    "revision": "1",
                    "description": "",
                },
                "config": {
                    "channels": env.config.channels,
                    "platforms": {env.platform: {}},
                    "variables": env.variables,
                },
                "platform": env.platform,
                "system_requirements": [],
                "version": 1,
                "dependencies": env.requested_packages,
                "pypi_dependencies": env.external_packages.get("pip", []),
            }
        )

    @classmethod
    def from_dict(cls, obj: dict[str, Any]) -> TomlSpec:
        """Ingest a dict (e.g. read from a TOML spec file) to build a TomlSpec.

        Parameters
        ----------
        obj : dict[str, Any]
            A dict which can be validated with TomlSingleEnvironment

        Returns
        -------
        Environment
            Environment object which can be used to update a conda environment
        """
        raise NotImplementedError

    @property
    def model(self) -> TomlSingleEnvironment:
        """Generate a pydantic model from the TomlSpec.

        Returns
        -------
        TomlSingleEnvironment
            Model of the environment
        """
        if self._model is None or self._environment is None:
            self._load()
        return self._model

    @property
    def env(self) -> Environment:
        """Generate an Environment from the TomlSpec.

        Returns
        -------
        Environment
            An Environment instance populated by the TomlSpec
        """
        if self._model is None or self._environment is None:
            self._load()
        return self._environment

    @property
    def environment(self) -> Environment:
        """Alias for `self.env`.

        Returns
        -------
        Environment
            An Environment instance populated from the TOML file
        """
        return self.env


class Author(BaseModel):
    """A model which holds author information."""

    name: str
    email: EmailStr | None = None


class About(BaseModel):
    """A model which stores metadata about an environment.

    `license` is an SPDX license expression: https://spdx.dev/learn/handling-license-info/
    `license_files` is a PEP639-compliant expression: https://peps.python.org/pep-0639/#term-license-expression
    """

    model_config = ConfigDict(
        alias_generator=lambda name: name.replace("_", "-"),
        validate_by_name=True,
        validate_by_alias=True,
    )

    name: str
    revision: str
    description: str
    authors: list[Author] = []
    license: str = ""
    license_files: list[str] = []
    urls: dict[str, AnyHttpUrl] = {}


class Config(BaseModel):
    """A model which stores configuration options for an environment."""

    channels: list[str] = []
    platforms: list[str] = []
    variables: dict[str, str] = {}

    def get_environment_config(self) -> EnvironmentConfig:
        """Populate an EnvironmentConfig with settings from this Config.

        See `conda.models.environment.EnvironmentConfig`.

        Returns
        -------
        EnvironmentConfig
            Configuration for an environment. Only the fields present in Config
            which are also in EnvironmentConfig are populated.
        """
        return EnvironmentConfig(channels=self.channels)


class EditablePackage(BaseModel):
    """A model which store info about an editable package."""

    name: str
    path: str
    editable: bool


MatchSpecList = Annotated[
    list[MatchSpec | EditablePackage], BeforeValidator(handle_match_specs)
]
PyPIDependencies = Annotated[
    list[str | EditablePackage], BeforeValidator(handle_pypi_dependencies)
    # list[PackageRecord | str | EditablePackage], BeforeValidator(handle_pypi_dependencies)
]


class Platform(BaseModel):
    """A model which stores a list of dependencies for a platform."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    dependencies: MatchSpecList = []


class TomlEnvironment(BaseModel, ABC):
    """A base class for (de)serialization of a TOML environment file.

    This shouldn't/won't be instantiated directly. Instead, calling model_validate will
    instantiate one of the child classes, depending on whichever the environment file
    successfully validates.
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        alias_generator=lambda name: name.replace("_", "-"),
        validate_by_name=True,
        validate_by_alias=True,
    )

    about: About
    config: Config | None = Config()
    system_requirements: MatchSpecList = []
    version: int = 1

    @classmethod
    def model_validate(cls, *args, **kwargs) -> TomlEnvironment:
        """Automatically determine which environment type to use."""
        if cls not in [TomlSingleEnvironment, TomlMultiEnvironment]:
            try:
                return TomlSingleEnvironment.model_validate(*args, **kwargs)
            except ValidationError:
                return TomlMultiEnvironment.model_validate(*args, **kwargs)

            raise ValidationError

        # If one of the subclasses is trying to validate, pass validation onto
        # the parent.
        return super().model_validate(*args, **kwargs)

    @abstractmethod
    def get_requested_packages(self, *args, **kwargs) -> list[MatchSpec]:
        """Get the requested conda packages.

        For a single environment, this is just the dependencies requested.
        For a multi-environment, an `environment` parameter will be used
        to determine which conda dependencies are returned here.

        Returns
        -------
        list[MatchSpec]
            A list of MatchSpec requested by the user
        """
        raise NotImplementedError

    @abstractmethod
    def get_external_packages(self, *args, **kwargs) -> list[MatchSpec]:
        """Get the requested pypi packages.

        For a single environment, this is just the dependencies requested.
        For a multi-environment, an `environment` parameter will be used
        to determine which conda dependencies are returned here.

        Returns
        -------
        list[MatchSpec]
            A list of MatchSpec requested by the user
        """
        raise NotImplementedError


class TomlSingleEnvironment(TomlEnvironment):
    """A model which handles single environment files."""

    model_config = ConfigDict(
        alias_generator=lambda name: name.replace("_", "-"),
        validate_by_name=True,
        validate_by_alias=True,
    )

    dependencies: MatchSpecList = []
    platform: dict[str, Platform] = {}
    pypi_dependencies: PyPIDependencies = []

    @model_validator(mode="before")
    @classmethod
    def _validate_urls(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Check that either `dependencies` or `pypi_dependencies` is not empty.

        If both are empty, this may instead be a TomlMultiEnvironment.

        Parameters
        ----------
        data : Any
            A dict of {field names: field values}

        Returns
        -------
        dict[str, Any]
            Validated data
        """
        if not (data.get("dependencies") or data.get("pypi_dependencies")):
            raise ValueError
        return data

    def get_requested_packages(self, *args, **kwargs) -> list[MatchSpec]:  # noqa: ARG002
        """Get the requested packages for the environment.

        Parameters
        ----------
        *args
            Unused
        **kwargs
            Unused

        Returns
        -------
        list[MatchSpec]
            A list of packages requested by the user. Does not include
            any editable packages
        """
        return self.dependencies

    def get_external_packages(self, *args, **kwargs) -> dict[str, list[str]]:  # noqa: ARG002
        """Get the external packages for the environment.

        Editable packages are ignored.

        Returns
        -------
        dict[str, list[str]]
            A mapping between installer names and packages to be installed
            by each installer. For PyPI dependencies, this will be

            {'pip': [<some package names>, ...]}
        """
        non_editable = []
        for dep in self.pypi_dependencies:
            if isinstance(dep, EditablePackage):
                warn(
                    "Editable packages are not supported PyPI dependencies. "
                    f"Ignoring: {dep}",
                    stacklevel=2,
                )
            else:
                non_editable.append(dep)

        return {"pip": non_editable}


class Group(BaseModel):
    """A model which stores configuration for a group of dependencies."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        alias_generator=lambda name: name.replace("_", "-"),
        validate_by_name=True,
        validate_by_alias=True,
    )

    config: Config | None = Config()
    dependencies: MatchSpecList = []
    description: str | None = None
    platform: dict[str, Platform] = {}
    pypi_dependencies: PyPIDependencies = []
    system_requirements: MatchSpecList = []


class TomlMultiEnvironment(TomlEnvironment):
    """A model which handles multi environment files."""

    groups: dict[str, Group] = {}
    environments: dict[str, list[str]] = {}

    @field_validator("groups", mode="after")
    @classmethod
    def _validate_groups(cls, groups: dict[str, Group]) -> dict[str, Group]:
        """Verify that at least one group is specified."""
        if not groups:
            raise ValueError(
                "At least one group is required in a multi-environment specification."
            )
        return groups

    @field_validator("environments", mode="after")
    @classmethod
    def _validate_environments(
        cls,
        envs: dict[str, list[str]],
        info: ValidationInfo,
    ) -> dict[str, list[str]]:
        """Verify that >1 env is specified, and that envs refer to specified groups.

        Warn the user if the spec contains a group which is not used by any environment.

        Parameters
        ----------
        envs : dict[str, list[str]]
            Unvalidated environments
        info : ValidationInfo
            Validated information; contains the validated groups

        Returns
        -------
        dict[str, list[str]]
            The validated environments
        """
        if not envs:
            raise ValueError(
                "Multi-environment specifications must contain at least one "
                "environment."
            )

        groups = set(info.data.get("groups", {}))
        extra_groups: set[str] = copy(groups)

        missing_groups = {}
        for env, env_groups in envs.items():
            # If an environment contains an unspecified group, keep track of it
            missing = set(env_groups) - groups
            if missing:
                missing_groups[env] = missing

            # Keep track of which groups are being used by environments, so we can warn
            # about unused ones later on
            extra_groups -= set(env_groups)

        if missing_groups:
            # Let the user know what groups are missing for each problematic environment
            msg = ""
            for key, values in missing_groups.items():
                msg += key
                msg += indent(pformat(values), prefix="  ")
            raise ValueError(
                "Multi-environment specification has environments with undefined "
                f"dependency groups:\n{indent(pformat(msg), prefix='  ')}"
            )

        if extra_groups:
            warn(
                "Some dependency groups were specified which were never used in any"
                "environment. Consider removing these:\n"
                f"{indent(pformat(extra_groups), prefix='  ')}",
                stacklevel=2,
            )

        return envs


def combine(*configs) -> EnvironmentConfig:
    """Combine EnvironmentConfig objects into a single object.

    Like `conda.models.environment.EnvironmentConfig.merge`, except fields
    of configs on the right always clobber fields in configs on the left.

    Parameters
    ----------
    *configs
        Configuration objects to combine

    Returns
    -------
    EnvironmentConfig
        The combined EnvironmentConfig object
    """
    assert all(isinstance(config, EnvironmentConfig) for config in configs)

    env_config = configs[0]
    for config in configs[1:]:
        for field in fields(config):
            value = getattr(config, field.name)
            if value is None:
                value = getattr(env_config, field.name)

            setattr(env_config, field.name, value)

    return env_config
