# conda-declarative

Declarative workflows for conda environment handling.

> [!IMPORTANT]
> This project is still in early stages of development. Don't use it in production (yet).
> We do welcome feedback on what the expected behaviour should have been if something doesn't work!

## What is this?

`conda declarative` proposes an alternative workflow for the lifecycle of `conda` environments. It is based around the idea of having a "manifest file" where all the user input for the environment is declared and stored. This is exposed via two new subcommands:

- `conda edit`: opens an editor to perform modifications on the active environment manifest file.
- `conda apply`: renders the manifest file as a history checkpoint and links the solved packages to disk.

## Installation

This is a `conda` plugin and goes in the `base` environment:

```bash
conda install -n base conda-forge::conda-declarative
```

More information is available on our [documentation](https://conda-incubator.github.io/conda-declarative).

## Contributing

Please refer to [`CONTRIBUTING.md`](/CONTRIBUTING.md).
