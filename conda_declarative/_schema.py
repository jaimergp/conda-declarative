"""
Pydantic models to generate the JSON schema behind the `conda.toml` format.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Annotated, Literal

from conda.base.constants import (
    PLATFORMS,
    ChannelPriority,
    SatSolverChoice,
)
from pydantic import BaseModel, ConfigDict, EmailStr, Field

HERE = Path(__file__).parent
SCHEMA_PATH = HERE / "data" / "conda-manifest.schema.json"
NAME_REGEX = VERSION_REGEX = r"^[a-zA-Z0-9_]([a-zA-Z0-9._-]*[a-zA-Z0-9_])?$"
ENV_NAME_REGEX = r"^[^/:# ]+$"
NonEmptyStr = Annotated[str, Field(min_length=1)]
_base_config_dict = ConfigDict(
    extra="forbid",
    use_attribute_docstrings=True,
)

ValidPlatforms = Literal[PLATFORMS]


class Author(BaseModel):
    """
    Metadata to describe a single author or maintainer.
    """

    model_config: ConfigDict = _base_config_dict

    name: NonEmptyStr
    """
    Name of the author or team.
    """
    email: EmailStr
    """
    E-mail address for the author or team.
    """


class Project(BaseModel):
    """
    Metadata about for this manifest file. Mostly static.
    """

    model_config: ConfigDict = _base_config_dict

    name: NonEmptyStr = ...
    """
    Name for this project.
    """
    revision: NonEmptyStr = ...
    """
    A version-like string that allows maintainers to apply versioning schemes to this manifest file.
    """
    description: NonEmptyStr | None = None
    """
    An optional free-form text field for maintainers to document this manifest file.
    Supports Markdown.
    """
    authors: list[Author] = []
    """
    People or teams involved in the creation and maintenance of this file.
    """
    license: NonEmptyStr
    """
    SPDX expression describing the license of this work.
    """
    license_files: list[NonEmptyStr] = Field([], alias="license-files")
    """
    List of paths to the license files governing this work.
    """
    urls: dict[NonEmptyStr, NonEmptyStr] = {}
    """
    Mapping of website names to their URL addresses.
    """


class SystemRequirements(BaseModel):
    """
    Properties of system features.

    These will be exposed to the solver for the appropriate
    selection of package variants, usually as lower bounds.
    """

    model_config: ConfigDict = _base_config_dict

    libc: NonEmptyStr | None = None
    "Version of the system libc (Linux only). Equivalent to setting `CONDA_OVERRIDE_GLIBC`."
    cuda: NonEmptyStr | None = None
    "Version of CUDA. Equivalent to setting `CONDA_OVERRIDE_CUDA`."
    osx: NonEmptyStr | None = None
    "Version of macOS. Equivalent to setting `CONDA_OVERRIDE_OSX`."
    linux: NonEmptyStr | None = None
    "Version of the Linux kernel. Equivalent to setting `CONDA_OVERRIDE_LINUX`."
    win: NonEmptyStr | None = None
    "Version of Windows in use. Equivalent to setting `CONDA_OVERRIDE_WIN`."
    archspec: NonEmptyStr | None = None
    "System architecture name. Equivalent to setting `CONDA_OVERRIDE_ARCHSPEC`."


class CondaPackageConstraints(BaseModel):
    """
    Constraints for conda packages.
    """

    model_config: ConfigDict = _base_config_dict

    version: NonEmptyStr = "*"
    build: NonEmptyStr = "*"
    channel: NonEmptyStr | None = None


class CondaConfig(BaseModel):
    """
    Conda configuration for this project.

    Only a subset of the full `.condarc` settings is allowed. Additional keys can be added
    but will be ignored in `conda`.
    """

    model_config: ConfigDict = ConfigDict(
        extra="ignore",
        use_attribute_docstrings=True,
    )

    aggressive_update_packages: list[NonEmptyStr] = Field(
        [],
        alias="aggressive-update-packages",
    )
    """
    List of package names to always include in update requests.
    """
    channel_priority: ChannelPriority | None = Field(None, alias="channel-priority")
    """
    What priority scheme to follow when solving with more than one channel.
    """
    channels: list[NonEmptyStr] = []
    """
    List of channels to obtain packages from.
    """
    channel_settings: list[dict[NonEmptyStr, NonEmptyStr]] = Field(
        [],
        alias="channel-settings",
    )
    """
    Per-channel configuration. The keys must be names mentioned in `channels`.
    """
    platforms: list[ValidPlatforms] = []  # type: ignore
    """
    Which platforms should be solved for this project. Defaults to the platform
    `conda` is running on, but can be extended to additional ones to, for example,
    generate lockfiles on each update.
    """
    pinned_packages: dict[NonEmptyStr, NonEmptyStr | CondaPackageConstraints] = Field(
        {},
        alias="pinned-packages",
    )
    """
    Additional constraints to impose on the solver for conda dependencies.

    These are not requirements, but will condition which packages are available for selection.
    """
    repodata_fns: list[NonEmptyStr] = Field([], alias="repodata-fns")
    """
    Repodata filenames to query in each channel. Usually, `repodata.json`.
    """
    sat_solver: SatSolverChoice | None = Field(None, alias="sat-solver")
    """
    Which SAT backend to use for the `classic` solver plugin.
    """
    solver: NonEmptyStr | None = None
    """
    Which solver plugin to use.
    """
    use_only_tar_bz2: bool | None = Field(None, alias="use-only-tar-bz2")
    """
    Ignore .conda artifacts and solve only with .tar.bz2. Legacy option, discouraged.
    """


class PlatformSpecificFields(BaseModel):
    """
    Platform-specific overrides.
    """

    model_config: ConfigDict = _base_config_dict

    config: CondaConfig | None = None
    """
    Configuration details for the install tool.
    """
    system_requirements: SystemRequirements | None = Field(
        None,
        alias="system-requirements",
        help=SystemRequirements.__doc__,
    )
    dependencies: dict[NonEmptyStr, NonEmptyStr | CondaPackageConstraints] = {}
    """
    conda packages to install. It must be a mapping of package names to package versions.
    Use `*` for the version if any version works. The value can also be an object that
    specifies version, build and/or channel.
    """
    pypi_dependencies: dict[NonEmptyStr, NonEmptyStr] = Field(
        {}, alias="pypi-dependencies"
    )
    """
    PyPI packages to install. It must be a mapping of package names to package versions.
    Use `*` for the version if any version works.
    """


class CondaManifest(PlatformSpecificFields):
    """
    Schema for `conda.toml` manifest files.
    """

    model_config: ConfigDict = _base_config_dict

    schema_: Annotated[str, Field(min_length=1, alias="$schema")] = (
        "https://schemas.conda.org/conda/v0/conda-manifest.schema.json"
    )
    """
    JSON Schema URL or path used to validate this input file.
    """
    version: Annotated[int, Field(ge=0)] = 0
    """
    Version of the conda.toml file format.
    """
    about: Project = Field(help=Project.__doc__)
    platform: dict[ValidPlatforms, PlatformSpecificFields] = {}
    """
    Platform-specific details. Allows extending most top-level keys
    with items exclusively used when that platform is selected.
    """


def fix_descriptions(obj: dict) -> dict:
    for key, value in obj.items():
        if isinstance(value, dict):
            obj[key] = fix_descriptions(value)
        if key == "description" and isinstance(value, str):
            codeblocks = re.findall(r"```.*```", value, flags=re.MULTILINE | re.DOTALL)
            for i, codeblock in enumerate(codeblocks):
                value = value.replace(codeblock, f"__CODEBLOCK_{i}__")
            value = (
                value.replace("\n\n", "__NEWLINE__")
                .replace("\n-", "__NEWLINE__-")
                .replace("\n", " ")
                .replace("  ", " ")
                .replace("__NEWLINE__", "\n")
            )
            for i, codeblock in enumerate(codeblocks):
                value = value.replace(f"__CODEBLOCK_{i}__", codeblock)
            obj[key] = value

    return obj


def dump_schema() -> None:
    obj = CondaManifest.model_json_schema()
    obj = fix_descriptions(obj)
    obj["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    SCHEMA_PATH.write_text(json.dumps(obj, sort_keys=True, indent=2) + "\n")
    print(json.dumps(obj, sort_keys=True, indent=2))


if __name__ == "__main__":
    dump_schema()
