import pytest
from conda.models.environment import Environment

from conda_declarative import spec


def test_parse_single_environment(single_environment_dict):
    """Test that a single environment file can be parsed."""
    env = spec.TomlSingleEnvironment.model_validate(single_environment_dict)
    assert isinstance(env, spec.TomlSingleEnvironment)
    assert env.version == 1
    assert env.system_requirements


@pytest.mark.skip(reason="Multi-environments are not yet supported.")
def test_parse_multi_environment(multi_environment_dict):
    """Test that multi-environment files can be parsed."""
    env = spec.TomlMultiEnvironment.model_validate(multi_environment_dict)
    assert isinstance(env, spec.TomlMultiEnvironment)
    assert env.version == 1
    assert env.about == spec.About(
        name="workspace-name",
        revision="",
        description="Free text, supporting markdown",
        authors=[],
        license="",
        license_files=[],
        urls={},
    )

    assert env.config.channels == ["conda-forge"]
    assert set(("main", "gpu")) == set(env.groups)
    assert env.groups["gpu"].description == "This is for GPU enabled workflows"


@pytest.mark.skip(reason="Multi-environments are not yet supported.")
def test_parse_multi_environment2(multi_environment_dict2):
    """Test that multi-environment files can be parsed."""
    env = spec.TomlMultiEnvironment.model_validate(multi_environment_dict2)
    assert isinstance(env, spec.TomlMultiEnvironment)
    assert env.version == 1
    about = spec.About(
        name="conda",
        revision="2025-05-26",
        description="OS-agnostic, system-level binary package manager.",
        authors=[
            spec.Author(name="conda maintainers", email="conda-maintainers@conda.org")
        ],
        license="BSD-3-Clause",
        license_files=["LICENSE"],
        urls={
            "changelog": "https://github.com/conda/conda/blob/main/CHANGELOG.md",
            "documentation": "https://docs.conda.io/projects/conda/en/stable/",
            "repository": "https://github.com/conda/conda",
        },
    )

    assert env.about == about
    assert env.config.channels == []
    assert set(
        (
            "defaults",
            "run",
            "main",
            "test",
            "typing",
            "benchmark",
            "memray",
            "conda-forge",
        )
    ) == set(env.groups)
    assert env.groups["benchmark"].dependencies[0].name == "pytest-codspeed"
    assert set(env.environments) == set(("default", "test"))


@pytest.mark.parametrize(
    ("fixture", "expected_class"),
    [
        ("single_environment_dict", spec.TomlSingleEnvironment),
        ("multi_environment_dict", spec.TomlMultiEnvironment),
        ("multi_environment_dict2", spec.TomlMultiEnvironment),
    ],
)
@pytest.mark.skip(reason="Multi-environments are not yet supported.")
def test_parse_toml_environment(request, fixture, expected_class):
    """Ensure that TomlEnvironment can parse both single and multi environments."""
    env = spec.TomlEnvironment.model_validate(request.getfixturevalue(fixture))
    assert isinstance(env, expected_class)


def test_toml_spec(single_environment_path):
    """Test that a TOML file can be used to generate an Environment."""
    toml_spec = spec.TomlSpec(single_environment_path)

    assert toml_spec.can_handle()
    assert isinstance(toml_spec.env, Environment)
