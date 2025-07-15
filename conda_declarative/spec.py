from __future__ import annotations

from copy import copy
from pathlib import Path
from pprint import pformat
from textwrap import indent
from typing import Annotated, Any
from warnings import warn

from conda.models.environment import Environment
from conda.models.match_spec import MatchSpec
from conda.plugins.types import EnvironmentSpecBase
from pydantic import (
    AnyHttpUrl,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    EmailStr,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)


def as_dict(value: dict[str, str | dict[str, str]]) -> list[dict[str, str]]:
    """Coerce a raw dependency to a dict.

    Dependencies can either be strings, or dicts
    which can be parsed to MatchSpec.

    Parameters
    ----------
    value : Any
        A string match spec, or a dict containing match spec key/values

    Returns
    -------
    dict[str, str]
        A dict containing match spec key/values
    """
    items = []
    for name, item in value.items():
        if isinstance(item, str):
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
    """Implementation of conda's EnvironmentSpec which can handle toml files."""

    def __init__(self, filename: str):
        self.filename = filename

    def can_handle(self) -> bool:
        """Return whether the file passed to this class can be parsed.

        Returns
        -------
        bool
            True if the file can be parsed (it exists and is a toml file), False
            otherwise
        """
        if self.filename is None:
            return False

        file = Path(self.filename)
        return file.exists() and file.suffix == "toml"

    @property
    def env(self) -> Environment:
        """Generate an Environment from the provided TOML file."""
        return Environment()


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


class EditablePackage(BaseModel):
    """A model which store info about an editable package."""

    name: str
    path: str
    editable: bool


MatchSpecList = Annotated[list[MatchSpec | EditablePackage], BeforeValidator(as_dict)]


class Platform(BaseModel):
    """A model which stores a list of dependencies for a platform."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    dependencies: MatchSpecList = []


class TomlEnvironment(BaseModel):
    """A base class for (de)serialization of a TOML environment file.

    This shouldn't be instantiated directly; instead use one of the child classes, or
    TomlEnvironment.
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        alias_generator=lambda name: name.replace("_", "-"),
        validate_by_name=True,
        validate_by_alias=True,
    )

    about: About
    config: Config
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


class TomlSingleEnvironment(TomlEnvironment):
    """A model which handles single environment files."""

    model_config = ConfigDict(
        alias_generator=lambda name: name.replace("_", "-"),
        validate_by_name=True,
        validate_by_alias=True,
    )

    dependencies: MatchSpecList = []
    platform: dict[str, Platform] = {}
    pypi_dependencies: MatchSpecList = []

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
    pypi_dependencies: MatchSpecList = []
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
