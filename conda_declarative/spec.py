from __future__ import annotations

import string
from abc import ABC, abstractmethod
from collections.abc import Iterable
from copy import copy
from dataclasses import fields
from functools import total_ordering
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
from conda.models.records import PrefixRecord
from conda.plugins.types import EnvironmentSpecBase
from pydantic import (
    AnyHttpUrl,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    EmailStr,
    PlainSerializer,
    RootModel,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_serializer,
    model_validator,
)


def validate_match_spec(
    value: Iterable[MatchSpec | EditablePackage]
    | dict[str, MatchSpec | str | dict[str, str]],
) -> list[MatchSpec | EditablePackage]:
    """Preprocess a set of raw conda dependencies.

    Dependencies can either be strings, or dicts which can be parsed to MatchSpec, or
    dicts which can be parsed as EditablePackage.

    Parameters
    ----------
    value : list[MatchSpec | EditablePackage] | dict[str, MatchSpec | str | dict[str, str]]
        A list of dependencies, or a dict which maps package names to string, MatchSpec, or
        editable package objects

    Returns
    -------
    list[MatchSpec | EditablePackage]
        A list of dependencies
    """
    items = []
    if isinstance(value, list):
        items = value
    else:
        for name, item in value.items():
            if isinstance(item, MatchSpec):
                items.append(item)
            elif isinstance(item, str):
                items.append(MatchSpec(name=name, version=item))
            elif isinstance(item, dict):
                # This is a dict representation of a MatchSpec
                # or an editable package
                try:
                    items.append(EditablePackage(name=name, **item))
                except ValidationError:
                    items.append(MatchSpec(name=name, **item))
            else:
                raise ValueError(
                    f"Unsupported type ({type(item)}) encountered while validating "
                    f"a match spec: {str(item)}"
                )
    return sorted(items, key=lambda x: x.name)


def serialize_match_spec(specs: list[MatchSpec | EditablePackage]) -> dict[str, str]:
    """Serialize a list of MatchSpec to a dict.

    Parameters
    ----------
    specs : list[MatchSpec | EditablePackage]
        List of specs to serialize

    Returns
    -------
    dict[str, str]
        Dict representation of the input
    """
    items = {}
    for spec in specs:
        if isinstance(spec, MatchSpec):
            items[str(spec.name)] = "*" if spec.version is None else str(spec.version)
        elif isinstance(spec, EditablePackage):
            items[spec.name] = {"path": spec.path, "editable": spec.editable}
        else:
            raise ValueError(
                f"Unsupported type ({type(spec)}) encountered while serializing "
                f"a match spec: {str(spec)}"
            )
    return items


class TomlSpec(EnvironmentSpecBase):
    """Implementation of conda's EnvironmentSpec which can handle toml files.

    Acts as a converter to translate TomlSingleEnvironment instances to and from
    conda.models.environment.Environment objects. This class holds the filename of
    a TOML spec file (if a filename is provided upon instantiation), a
    TomlSingleEnvironment model instance, and an Environment instance. Since the
    TomlSingleEnvironment and Environment classes don't hold exactly the same
    information, the 95% use case is kept in mind when instantiating one object
    from the other.

                ┌───────────────────────┐     ┌────────────┐     ┌─────────────┐
                │ TomlSingleEnvironment │◄────┤  TomlSpec  │◄────┤ Environment │
                │    pydantic model     │────►│  instance  ├────►│             │
                └────────────┬──────────┘     └────────────┘     └─────────────┘
                         ▲   │                       ▲
                         │   ▼                       │
    ┌───────────┐    ┌───┴────────┐                  │
    │ TOML file │◄───│ dictionary │             ┌────┴────┐
    │           ├───►│            │             │ context │
    └───────────┘    └────────────┘             └─────────┘

    This class can instantiate using several different object types to facilitate
    translating between TOML files/TomlSingleEnvironment models/Environment objects:

    If the object passed to __init__ is a...

        - A str or Path, it is treated as a path to a TOML environment spec on disk.
          A new TomlSingleEnvironment model will be created as `self._model`, and an
          Environment object as `self._environment`. Fields of `self._environment` are
          instantiated from the context before being overwritten by any corresponding
          fields in `self._model`.
        - A dict, it is treated as a serialized TomlSingleEnvironment. A new model
          instance will be created from this dict. Fields of `self._environment` are
          instantiated from the context before being overwritten by any corresponding
          fields in `self._model`.
        - A TomlSingleEnvironment will just be stored as `self._model`. Fields of
          `self._environment` are instantiated from the context before being
          overwritten by any corresponding fields in `self._model`.
        - An Environment, which will be used to generate a TomlSingleEnvironment. A
          number of which appear in TomlSingleEnvironment but not Environment will be
          uninitialized, including `platforms`, `system_requirements`, and
          `pypi_dependencies`; see `TomlSpec._environment_to_model` for more info.
    """

    def __init__(self, obj: str | Path | TomlSingleEnvironment | Environment | dict):
        self._obj: str | Path | TomlSingleEnvironment | Environment | dict = obj

        self._filename: Path | None = None
        self._model: TomlSingleEnvironment | None = None
        self._environment: Environment | None = None

    def can_handle(self) -> bool:
        """Return whether the object passed to this class can be parsed.

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
        """Attempt to load the object which was passed to `TomlSpec.__init__`.

        If `self._obj` is a...

        - str or Path, it is treated as the path to a TOML environment spec file.
          A model will be created and Environment generated from it, together with
          the context
        - TomlSingleEnvironment, the model is just stored; a model will be created
          and Environment generated from it, together with the context.
          `self._filename` will be unpopulated.
        - dict, it is treated as a serialized TomlSingleEnvironment; a new model
          is created and Environment generated from it, together with the context.
          `self._filename` will be unpopulated.
        - Environment, a new model is created from it. `self._filename` will be
          unpopulated.
        """
        if isinstance(self._obj, str | Path):
            self._filename = Path(self._obj)

            if self._filename.exists() and self._filename.suffix == ".toml":
                with open(self._filename) as f:
                    text = f.read()

                self._model = TomlSingleEnvironment.model_validate(loads(text))
                self._environment = self._model_to_environment(self._model)
            else:
                raise ValueError(f"No file exists at {self._filename}")

        elif isinstance(self._obj, TomlSingleEnvironment):
            self._model = self._obj
            self._environment = self._model_to_environment(self._model)

        elif isinstance(self._obj, dict):
            try:
                self._model = TomlSingleEnvironment.model_validate(self._obj)
            except ValidationError as e:
                if "prefix" in self._obj:
                    raise ValueError(
                        "It looks like you are trying to pass a serialized "
                        "conda.models.environment.Environment to instantiate a "
                        "TomlSpec, but only serialized TomlSingleEnvironment "
                        "dictionaries are supported."
                    ) from e
                raise

            self._environment = self._model_to_environment(self._model)

        elif isinstance(self._obj, Environment):
            self._environment = self._obj
            self._model = self._environment_to_model(self._environment)

        else:
            raise ValueError(f"Invalid parameter for TomlSpec: {self._obj}")

    def _model_to_environment(self, model: TomlSingleEnvironment) -> Environment:
        """Generate an Environment instance from the model.

        Parameters
        ----------
        model : TomlSingleEnvironment
            Model containing info to use to populate an Environment. The conda context
            is used to populate any required fields of the Environment that don't have
            corresponding fields in the model; any fields in the model will take
            precedence over the corresponding fields from the conda context.

        Returns
        -------
        Environment
            Conda environment generated from the model
        """
        return Environment(
            prefix=context.target_prefix,
            platform=context.subdir,
            config=self._combine(
                EnvironmentConfig.from_context(), model.config.get_environment_config()
            ),
            external_packages=model.get_external_packages(),
            name=model.about.name,
            requested_packages=model.get_requested_packages(),
            variables=model.config.variables,
        )

    @staticmethod
    def _combine(*configs) -> EnvironmentConfig:
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

    @staticmethod
    def _environment_to_model(env: Environment) -> TomlSingleEnvironment:
        """Generate an TomlSingleEnvironment from an Environment.

        Parameters
        ----------
        env : Environment
            Environment to use to populate the model

        Returns
        -------
        TomlSingleEnvironment
            Model containing data from the Environment. Not all fields in the
            model will be populated because there are no fields for e.g.
            description, system_requirements, pypi_dependencies, etc
        """
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


@total_ordering
class EditablePackage(BaseModel):
    """A model which store info about an editable package."""

    name: str
    path: str
    editable: bool

    # Define comparison methods to allow sorting
    def __gt__(self, other: Any) -> bool:  # noqa: ANN401
        if isinstance(other, EditablePackage):
            return self.root.name > other.name
        return self.name > other

    def __eq__(self, other: Any) -> bool:  # noqa: ANN401
        if isinstance(other, EditablePackage):
            return self.name == other.name
        return self.name == other


MatchSpecList = Annotated[
    list[MatchSpec | EditablePackage],
    BeforeValidator(validate_match_spec),
    PlainSerializer(serialize_match_spec),
]


class PyPIDependencies(RootModel):
    """A model which stores a list of PyPI dependencies."""

    root: list[PyPIDependency]

    @model_validator(mode="before")
    @classmethod
    def _validate_model(
        cls,
        value: PyPIDependencies | list[PrefixRecord] | dict[str, str | dict[str, str]],
    ) -> PyPIDependencies:
        """Preprocess a set of raw pypi dependencies.

        Parameters
        ----------
        value : PyPIDependencies | dict[str, str | dict[str, str]]
            A mapping between package names and either a version specifier, or
            a dict of that indicates it is a local editable package, e.g.

                conda-declarative = { path  = ".", editable = true }

            Can also be a list of PyPI dependencies, in which case the list is
            just passed through.

        Returns
        -------
        PyPIDependencies
            A list of processed pypi dependencies
        """
        items = []
        if isinstance(value, list):
            for item in value:
                if isinstance(item, PyPIDependency):
                    items.append(value)
                else:
                    items.append(PyPIDependency.model_validate(item))

        else:
            for name, item in value.items():
                items.append(PyPIDependency.model_validate((name, item)))

        return sorted(items)

    @model_serializer
    def _serialize_model(self) -> dict[str, Any]:
        """Serialize a list of pypi dependencies into a dict.

        Returns
        -------
        dict[str, str | dict[str, str]]
            Serialized model
        """
        items = {}
        for dep in sorted(self):
            items.update(dep.model_dump(exclude_unset=True))
        return items

    def __iter__(self) -> Iterable[PyPIDependency]:
        yield from self.root

    def to_pip(self) -> list[str]:
        """Convert the dependencies to a pip-compatible format.

        Returns
        -------
        list[str]
            Format which can be passed to pip to install
        """
        return [dep.to_pip() for dep in self]


@total_ordering
class PyPIDependency(BaseModel):
    """A model which stores a single PyPI dependency."""

    name: str
    version: str | None = None
    path: str | None = None
    editable: bool | None = None

    @model_serializer
    def _serialize_model(self) -> dict[str, str | dict[str, str]]:
        if self.editable:
            return {self.name: {"path": self.path, "editable": self.editable}}
        return {self.name: self.version}

    @model_validator(mode="before")
    @classmethod
    def _validate_model(
        cls, value: PrefixRecord | tuple[str, str | dict[str, str]]
    ) -> dict[str, str]:
        if isinstance(value, PrefixRecord):
            name, obj = value.name, value.version
        else:
            name, obj = value

        if isinstance(obj, str):
            # The object is a MatchSpec-like string
            return {"name": name, "version": obj}

        if isinstance(obj, dict):
            return {"name": name, **obj}

        raise ValueError(
            f"Unsupported type ({type(obj)}) encountered while "
            f"validating a pypi dependency: {str(obj)}"
        )

    # Define comparison methods to allow sorting
    def __gt__(self, other: Any) -> bool:  # noqa: ANN401
        if isinstance(other, PyPIDependency):
            return self.name > other.name
        return self.name > other

    def __eq__(self, other: Any) -> bool:  # noqa: ANN401
        if isinstance(other, PyPIDependency):
            return self.name == other.name
        return self.name == other

    def to_pip(self) -> str:
        """Convert the dependency to a pip-compatible format.

        Returns
        -------
        str
            Format which can be passed to pip to install
        """
        if self.editable:
            # e.g. the name _is a path_: ./path/to/directory
            return f"{self.name}"

        if self.version is None or self.version in ["*", ""]:
            return f"{self.name}"

        if self.version[0] in string.digits:
            return f"{self.name}=={self.version}"

        if self.version[0] in ["<", ">"]:
            return f"{self.name}{self.version}"

        raise ValueError(
            f"Cannot convert PyPI dependency to pip format: {str(self.model_dump())}"
        )


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
        return {"pip": self.pypi_dependencies.to_pip()}


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
